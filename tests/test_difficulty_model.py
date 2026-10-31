"""Gün 15: sual çətinliyi modeli - əlamətlər, JSON inferensi, dataset ixracı, server, PyTorch öyrətməsi."""

import csv
import json
import math
import os

import pytest
from fastapi.testclient import TestClient

from ml.data import Row, read_csv, synthetic, write_csv
from pipeline.difficulty_features import FEATURES, extract
from pipeline.difficulty_model import DifficultyModel, ModelFileError, load_cached
from pipeline.models import MCQQuestion
from server.app import app, get_difficulty_model, get_question_set_store, get_token_secret, get_user_store
from server.auth import create_token
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

Q = MCQQuestion(question="Hansı orqan qanunvericilik hakimiyyətinə aid deyil?",
                options=["Milli Məclis", "Prezident", "1995", "2002", "Ali Məhkəmə"],
                correct_index=1, explanation="Prezident icra hakimiyyətidir.", difficulty="çətin")


def linear_model(weights, bias=0.0, **extra):
    """Bir neyronlu «şəbəkə»: əlamətlərin xətti cəmi → sigmoid (əl ilə yoxlanır)."""
    n = len(FEATURES)
    return {"features": FEATURES, "mean": [0.0] * n, "std": [1.0] * n,
            "layers": [{"w": [weights], "b": [bias]}], **extra}


# ---- əlamətlər --------------------------------------------------------------

def test_features_shape_and_meaning():
    f = dict(zip(FEATURES, extract(Q)))
    assert len(extract(Q)) == len(FEATURES)
    assert f["negation"] == 1.0                # «aid deyil»
    assert f["numeric_options"] == pytest.approx(0.4)   # 1995, 2002
    assert f["ai_cetin"] == 1.0 and f["ai_asan"] == 0.0
    assert f["stem_has_number"] == 0.0


def test_giveaway_length_raises_correct_ratio():
    long = MCQQuestion(question="Sual?", options=["a1", "b2", "uzun və izahlı düzgün cavab", "c3", "d4"],
                       correct_index=2, explanation="")
    assert dict(zip(FEATURES, extract(long)))["correct_len_ratio"] > 5


# ---- JSON inferensi -----------------------------------------------------------

def test_pure_python_inference_matches_hand_computation():
    weights = [0.0] * len(FEATURES)
    weights[FEATURES.index("negation")] = -2.0
    model = DifficultyModel.from_dict(linear_model(weights, bias=0.5))
    assert model.predict(Q) == pytest.approx(1 / (1 + math.exp(-(0.5 - 2.0))))
    assert model.level(0.8) == "asan" and model.level(0.5) == "orta" and model.level(0.2) == "çətin"


def test_hidden_layer_relu():
    n = len(FEATURES)
    data = {"features": FEATURES, "mean": [0.0] * n, "std": [1.0] * n,
            "layers": [{"w": [[1.0] + [0.0] * (n - 1), [-1.0] + [0.0] * (n - 1)], "b": [0.0, 0.0]},
                       {"w": [[1.0, 1.0]], "b": [0.0]}]}
    model = DifficultyModel.from_dict(data)
    x = [3.0] + [0.0] * (n - 1)
    assert model.predict_features(x) == pytest.approx(1 / (1 + math.exp(-3.0)))  # relu(-3) = 0


def test_bad_model_files_rejected():
    with pytest.raises(ModelFileError):
        DifficultyModel.from_dict({**linear_model([0.0] * len(FEATURES)), "features": FEATURES[:-1]})
    with pytest.raises(ModelFileError):
        DifficultyModel.from_dict(linear_model([0.0] * 3))


def test_load_cached_missing_corrupt_and_reload(tmp_path):
    path = tmp_path / "m.json"
    assert load_cached(str(path)) is None
    path.write_text("{pozuq", encoding="utf-8")
    assert load_cached(str(path)) is None
    path.write_text(json.dumps(linear_model([0.0] * len(FEATURES), bias=2.0)), encoding="utf-8")
    os.utime(path, (1, 1))
    assert load_cached(str(path)).predict(Q) == pytest.approx(1 / (1 + math.exp(-2.0)))


# ---- server -----------------------------------------------------------------

@pytest.fixture
def client():
    users, banks = UserStore(":memory:"), QuestionSetStore(":memory:")
    teacher = users.create("t@x.az", "h", "Müəllim")
    users.set_teacher(teacher["id"], True)
    bank = banks.create(subject="qanunvericilik", title="B", material_kind="text", material_location="x",
                        created_by=teacher["id"])
    banks.add_question(bank["id"], Q)
    for dep, value in {get_user_store: users, get_question_set_store: banks,
                       get_token_secret: "test-secret-key-32-chars-minimum!!"}.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    headers = {"Authorization": f"Bearer {create_token(teacher['id'], secret='test-secret-key-32-chars-minimum!!')}"}
    yield lambda: TestClient(app).get(f"/live/question-sets/{bank['id']}/questions", headers=headers).json()
    app.dependency_overrides.clear()


def test_questions_have_no_prediction_without_model(client):
    app.dependency_overrides[get_difficulty_model] = lambda: None
    row = client()[0]
    assert row["predicted_correct"] is None and row["predicted_difficulty"] is None


def test_questions_carry_model_prediction(client):
    model = DifficultyModel.from_dict(linear_model([0.0] * len(FEATURES), bias=-1.0))
    app.dependency_overrides[get_difficulty_model] = lambda: model
    row = client()[0]
    assert row["predicted_correct"] == pytest.approx(0.269, abs=1e-3)
    assert row["predicted_difficulty"] == "çətin" and row["difficulty"] == "çətin"


def test_synthetic_model_is_never_shown(tmp_path, monkeypatch):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(linear_model([0.0] * len(FEATURES), synthetic=True)), encoding="utf-8")
    monkeypatch.setenv("DIFFICULTY_MODEL_PATH", str(path))
    assert get_difficulty_model() is None
    path.write_text(json.dumps(linear_model([0.0] * len(FEATURES), synthetic=False)), encoding="utf-8")
    os.utime(path, (5, 5))
    assert get_difficulty_model() is not None


# ---- dataset ixracı -----------------------------------------------------------

def test_export_counts_live_and_homework_answers_without_student_data(tmp_path):
    from deploy.export_difficulty_data import build_rows, main
    from server.homework_store import HomeworkStore
    from server.live_session_store import LiveSessionStore

    banks = QuestionSetStore(str(tmp_path / "question_sets.db"))
    bank = banks.create(subject="qanunvericilik", title="B", material_kind="text", material_location="x",
                        created_by=1)
    banks.add_question(bank["id"], Q)
    banks.add_question(bank["id"], MCQQuestion(question="İkinci?", options=list("ABCDE"), correct_index=0,
                                               explanation="", difficulty="asan"))
    live = LiveSessionStore(str(tmp_path / "live_sessions.db"))
    session = live.create_session(bank["id"])
    for user_id, ok in [(1, True), (2, False), (3, False), (4, True)]:
        participant = live.add_participant(session["id"], f"T{user_id}", user_id=user_id)
        live.record_answer(session["id"], participant["id"], 0, 1 if ok else 0, ok)
    homework = HomeworkStore(str(tmp_path / "homework.db"))
    assignment = homework.create_assignment(chat_id=1, question_set_id=bank["id"], due_date="2026-12-01",
                                            created_by=1)
    attempt = homework.get_or_create_attempt(assignment["id"], student_id=9)
    homework.answer(attempt["id"], 0, 0, False, total_questions=2)

    rows, extra = build_rows(str(tmp_path), min_answers=5)
    assert len(rows) == 1  # ikinci sualın cavabı yoxdur
    assert rows[0].answers == 5 and rows[0].accuracy == pytest.approx(0.4)
    assert rows[0].ai_level == "çətin" and extra[0]["subject"] == "qanunvericilik"

    out = tmp_path / "out.csv"
    assert main(["--data-dir", str(tmp_path), "--out", str(out)]) == 0
    header = next(csv.reader(open(out, encoding="utf-8")))
    assert not {"student_id", "user_id", "display_name", "email", "question"} & set(header)
    assert read_csv(str(out))[0].answers == 5


def test_csv_roundtrip_and_missing_column(tmp_path):
    rows = synthetic(30, seed=1)
    path = tmp_path / "d.csv"
    write_csv(str(path), rows)
    back = read_csv(str(path))
    assert len(back) == 30 and back[0].answers == rows[0].answers
    path.write_text("accuracy,answers\n0.5,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sütun yoxdur"):
        read_csv(str(path))


def test_synthetic_dataset_is_deterministic():
    assert [r.accuracy for r in synthetic(10, seed=3)] == [r.accuracy for r in synthetic(10, seed=3)]
    assert all(0 <= r.accuracy <= 1 and r.answers >= 5 for r in synthetic(50))


# ---- PyTorch öyrətməsi (torch yalnız ml mühitində; CI-da keçilir) ---------------

def test_training_beats_baselines_and_json_matches_torch(tmp_path):
    torch = pytest.importorskip("torch")
    from ml.train_difficulty import main, train

    rows = synthetic(600, seed=0)
    result = train(rows, seed=0, synthetic_data=True)
    assert result["synthetic"] is True
    assert result["metrics"]["mae"] < result["metrics"]["baseline_mae_mean"]
    assert result["metrics"]["beats_baselines"]

    # JSON-dakı çəkilərlə torch şəbəkəsi və saf Python eyni ehtimalı verməlidir.
    net = torch.nn.Sequential(torch.nn.Linear(len(FEATURES), 16), torch.nn.ReLU(), torch.nn.Linear(16, 1))
    with torch.no_grad():
        for layer, data in zip((net[0], net[2]), result["layers"]):
            layer.weight.copy_(torch.tensor(data["w"]))
            layer.bias.copy_(torch.tensor(data["b"]))
    model = DifficultyModel.from_dict(result)
    x = torch.tensor([r.features for r in rows[:20]])
    expected = torch.sigmoid(net((x - torch.tensor(result["mean"])) / torch.tensor(result["std"]))).squeeze(1)
    for row, p in zip(rows[:20], expected.tolist()):
        assert model.predict_features(row.features) == pytest.approx(p, abs=1e-5)

    out = tmp_path / "m.json"
    assert main(["--synthetic", "200", "--out", str(out), "--epochs", "50"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["synthetic"] is True


def test_training_refuses_tiny_dataset():
    pytest.importorskip("torch")
    from ml.train_difficulty import train

    with pytest.raises(ValueError, match="ən azı 20"):
        train([Row([0.0] * len(FEATURES), 0.5, 5)] * 5)
