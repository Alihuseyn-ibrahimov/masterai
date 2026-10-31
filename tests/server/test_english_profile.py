"""İngilis dili profili — server qatı (spec 2026-09-29 §5).

- Bankın profili YARADILANDA kursdan götürülür və bankda saxlanılır.
- Reading bankı yalnız `english` kursunda; mətn bankda saxlanılır və ev
  tapşırığında tələbəyə göstərilir; canlı sessiya onu QƏBUL ETMİR (orada
  mətn tələbənin qarşısında olmur).
- İmtahan kursu (kurs #1) üçün generator əvvəlki kimi `exam_prep` alır.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion, PipelineResult
from server.app import (
    app,
    get_chat_store,
    get_connection_manager,
    get_homework_store,
    get_live_session_store,
    get_material_generator,
    get_material_store,
    get_message_store,
    get_question_set_store,
    get_question_store,
    get_token_secret,
    get_upload_dir,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.course_store import DEFAULT_COURSE_ID
from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.material_store import MaterialStore
from server.message_store import MessageStore
from server.question_set_store import QuestionSetStore
from server.question_store import QuestionStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_PASSAGE = "Tom goes to school every day. He likes English very much."
_QUESTION = MCQQuestion(question="What does Tom like?", options=["English", "Maths", "Art", "Music", "Sport"],
                        correct_index=0, explanation="Mətndə Tom ingilis dilini sevdiyi yazılıb.")


class _Generator:
    """Çağırış parametrlərini yazır; reading üçün mətn qaytarır."""

    def __init__(self):
        self.calls = []

    def __call__(
        self, source, question_count=10, *, profile="exam_prep", bank_kind="practice",
        difficulty_mix=None, subject=None,
    ):
        self.calls.append({"profile": profile, "bank_kind": bank_kind})
        return PipelineResult(
            questions=[_QUESTION], source=source, chunks_processed=1, chunks_failed=0,
            requested_question_count=question_count,
            passage=_PASSAGE if bank_kind == "reading" else None,
        )


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live = LiveSessionStore(":memory:")
    homework = HomeworkStore(":memory:")
    materials = MaterialStore(":memory:")
    generator = _Generator()
    overrides = {
        get_user_store: users, get_chat_store: chats, get_question_set_store: question_sets,
        get_live_session_store: live, get_homework_store: homework, get_material_store: materials,
        get_message_store: MessageStore(":memory:"), get_question_store: QuestionStore(":memory:"),
        get_connection_manager: ConnectionManager(), get_material_generator: generator,
        get_upload_dir: str(tmp_path), get_token_secret: _SECRET,
    }

    def _const(value):
        return lambda: value

    for dep, value in overrides.items():
        app.dependency_overrides[dep] = _const(value)

    english = users.courses.create("English", "english", trial_days=30, seat_limit=30)

    def teacher(email, course_id):
        row = users.create(email, "h", email.split("@")[0], course_id=course_id)
        users.set_teacher(row["id"], True)
        return users.get_by_id(row["id"])

    t_en = teacher("en@x.az", english["id"])
    t_ex = teacher("ex@x.az", DEFAULT_COURSE_ID)
    student = users.create("s@x.az", "h", "Tələbə", course_id=english["id"])
    chat = chats.create(kind="group", created_by=t_en["id"], name="Sinif", course_id=english["id"])
    chats.add_member(chat["id"], t_en["id"])
    chats.add_member(chat["id"], student["id"])
    yield {
        "client": TestClient(app), "users": users, "question_sets": question_sets, "chats": chats,
        "generator": generator, "t_en": t_en, "t_ex": t_ex, "student": student, "chat": chat,
        "english": english,
    }
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _create_bank(env, teacher, **extra):
    data = {"subject": "xarici_dil", "title": "Unit 1", "kind": "link", "location": "https://x.az", **extra}
    return env["client"].post("/live/question-sets", data=data, headers=_auth(teacher))


def _wait_ready(env, qs_id):
    deadline = time.time() + 2
    while time.time() < deadline:
        qs = env["question_sets"].get(qs_id)
        if qs["status"] != "processing":
            return qs
        time.sleep(0.02)
    return env["question_sets"].get(qs_id)


class TestBankProfile:
    def test_english_course_bank_uses_english_profile(self, env):
        r = _create_bank(env, env["t_en"])
        assert r.status_code == 202
        body = r.json()
        assert body["profile"] == "english" and body["bank_kind"] == "practice"
        _wait_ready(env, body["id"])
        assert env["generator"].calls == [{"profile": "english", "bank_kind": "practice"}]

    def test_exam_course_unchanged(self, env):
        r = _create_bank(env, env["t_ex"], subject="mentiq")
        _wait_ready(env, r.json()["id"])
        assert r.json()["profile"] == "exam_prep"
        assert env["generator"].calls == [{"profile": "exam_prep", "bank_kind": "practice"}]

    def test_reading_bank_stores_passage(self, env):
        r = _create_bank(env, env["t_en"], bank_kind="reading")
        assert r.status_code == 202
        qs = _wait_ready(env, r.json()["id"])
        assert qs["status"] == "ready" and qs["bank_kind"] == "reading"
        assert env["question_sets"].get_passage(qs["id"]) == _PASSAGE

    def test_reading_rejected_in_exam_course(self, env):
        r = _create_bank(env, env["t_ex"], subject="mentiq", bank_kind="reading")
        assert r.status_code == 400
        assert env["generator"].calls == []

    def test_unknown_bank_kind_rejected(self, env):
        assert _create_bank(env, env["t_en"], bank_kind="essay").status_code == 400


def _ready_bank(env, bank_kind):
    qs = env["question_sets"].create("xarici_dil", "Unit", "link", "https://x", created_by=env["t_en"]["id"],
                                     course_id=env["english"]["id"], profile="english", bank_kind=bank_kind)
    env["question_sets"].add_question(qs["id"], _QUESTION)
    if bank_kind == "reading":
        env["question_sets"].set_passage(qs["id"], _PASSAGE)
    env["question_sets"].mark_ready(qs["id"])
    return qs


class TestWhereReadingIsUsed:
    def test_live_session_rejects_reading_bank(self, env):
        qs = _ready_bank(env, "reading")
        r = env["client"].post("/live/sessions", json={"question_set_id": qs["id"], "chat_id": env["chat"]["id"]},
                               headers=_auth(env["t_en"]))
        assert r.status_code == 400
        assert "ev tapşırığı" in r.json()["detail"]

    def test_live_session_accepts_practice_bank(self, env):
        qs = _ready_bank(env, "practice")
        r = env["client"].post("/live/sessions", json={"question_set_id": qs["id"], "chat_id": env["chat"]["id"]},
                               headers=_auth(env["t_en"]))
        assert r.status_code == 201

    @pytest.mark.parametrize("bank_kind,expected", [("reading", _PASSAGE), ("practice", None)])
    def test_homework_shows_passage_to_student(self, env, bank_kind, expected):
        qs = _ready_bank(env, bank_kind)
        a = env["client"].post("/homework/assignments", json={
            "chat_id": env["chat"]["id"], "question_set_id": qs["id"], "due_date": "2099-01-01"},
            headers=_auth(env["t_en"]))
        assert a.status_code == 201
        r = env["client"].post(f"/homework/assignments/{a.json()['id']}/start", headers=_auth(env["student"]))
        assert r.status_code == 200
        assert r.json()["passage"] == expected


class TestQualityUsesBankProfile:
    def _codes(self, env, bank_kind):
        qs = _ready_bank(env, bank_kind)
        env["question_sets"].add_question(qs["id"], MCQQuestion(
            question="According to the text, where does Tom go every day?",
            options=["School", "Park", "Shop", "Home", "Gym"], correct_index=0,
            explanation="Mətndə Tom hər gün məktəbə getdiyi yazılıb."))
        r = env["client"].get(f"/live/question-sets/{qs['id']}/quality", headers=_auth(env["t_en"]))
        return {f["code"] for f in r.json()["findings"]}

    def test_practice_bank_flags_text_recall(self, env):
        assert "materiala_istinad" in self._codes(env, "practice")

    def test_reading_bank_allows_text_questions(self, env):
        assert "materiala_istinad" not in self._codes(env, "reading")


def test_me_course_exposes_profile(env):
    r = env["client"].get("/me/course", headers=_auth(env["t_en"]))
    assert r.json()["profile"] == "english"


def test_chat_material_uses_chat_course_profile(env):
    r = env["client"].post(f"/chats/{env['chat']['id']}/materials",
                           data={"kind": "link", "location": "https://x.az", "question_count": 3},
                           headers=_auth(env["t_en"]))
    assert r.status_code == 202
    deadline = time.time() + 2
    while not env["generator"].calls and time.time() < deadline:
        time.sleep(0.02)
    assert env["generator"].calls == [{"profile": "english", "bank_kind": "practice"}]
