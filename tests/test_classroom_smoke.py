"""Gün 14: canlı serverin uc-uca yoxlama skripti (`deploy/diagnostics/classroom_smoke.py`).

Skript real API-yə urllib ilə gedir; burada `_send` TestClient-ə yönəldilir və
bütün zəncir (sinif → dərs → video → QR → lövhə OCR → quiz → konspekt → AI yoxlama
→ tutor → bitir) saxta AI ilə, amma REAL tesseract ilə keçir.
"""

import importlib.util
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion, PipelineResult
from pipeline.review_team import FACT_SYSTEM_PROMPT, PEDAGOGUE_SYSTEM_PROMPT, review_questions
from pipeline.summary import LessonSummary
from pipeline.tutor_graph import run_tutor
from server.app import (
    app,
    get_chat_store,
    get_lesson_store,
    get_livekit_config,
    get_material_generator,
    get_material_store,
    get_question_set_store,
    get_reviewer,
    get_summarizer,
    get_summary_store,
    get_token_secret,
    get_tutor,
    get_upload_dir,
    get_user_store,
)
from server.auth import hash_password
from server.chat_store import ChatStore
from server.lesson_store import LessonStore
from server.material_store import MaterialStore
from server.question_set_store import QuestionSetStore
from server.summary_store import SummaryStore
from server.user_store import UserStore
from server.video import LiveKitConfig

_PATH = Path(__file__).resolve().parents[1] / "deploy" / "diagnostics" / "classroom_smoke.py"
_spec = importlib.util.spec_from_file_location("classroom_smoke", _PATH)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract yoxdur")


class ClientApi(smoke.Api):
    def __init__(self, client):
        super().__init__("http://test")
        self.client = client

    def _send(self, method, path, data, headers):
        resp = self.client.request(method, path, content=data, headers=headers)
        return resp.status_code, resp.content


def _llm(system, user):
    if system in (FACT_SYSTEM_PROMPT, PEDAGOGUE_SYSTEM_PROMPT):
        return '[{"n": 1, "ok": true}, {"n": 2, "ok": false, "issue": "x"}, {"n": 3, "ok": true}]'
    if "tutorusan" in system:
        return "Milli Məclis 125 deputatdan ibarətdir [1]."
    return "{}"


def _generator(source, question_count=10, **options):
    return PipelineResult(
        questions=[MCQQuestion(question=f"Sual {i}?", options=list("ABCDE"), correct_index=0, explanation="i")
                   for i in range(question_count)],
        source=source, chunks_processed=1, chunks_failed=0, requested_question_count=question_count)


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    course = users.courses.create("Kurs", "exam_prep", trial_days=30, seat_limit=30)
    teacher = users.create("t@x.az", hash_password("parol12345"), "Müəllim", course_id=course["id"])
    users.set_teacher(teacher["id"], True)
    users.create("s@x.az", hash_password("parol12345"), "Tələbə", course_id=course["id"])
    overrides = {
        get_user_store: users, get_chat_store: ChatStore(":memory:"), get_lesson_store: LessonStore(":memory:"),
        get_question_set_store: QuestionSetStore(":memory:"), get_summary_store: SummaryStore(":memory:"),
        get_material_store: MaterialStore(":memory:"), get_token_secret: "test-secret-key-32-chars-minimum!!",
        get_upload_dir: str(tmp_path), get_material_generator: _generator,
        get_summarizer: lambda source: LessonSummary(title="Konspekt", intro="Giriş.", key_points=["Bir."]),
        get_reviewer: lambda source, qs: review_questions(qs, "Milli Məclis 125", completers={"x": _llm},
                                                          order=["x"]),
        get_tutor: lambda q, d, h: run_tutor(q, d, h, completers={"x": _llm}, order=["x"]),
        get_livekit_config: LiveKitConfig("wss://demo.livekit.cloud", "key", "s" * 40),
    }
    for dep, value in overrides.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _run(client, email="t@x.az", password="parol12345", **options):
    lines = []
    runner = smoke.Smoke(ClientApi(client), audio=options.get("audio"), skip_ai=options.get("skip_ai", False),
                         timeout=20, out=lines.append)
    ok = runner.run(email, password)
    return ok, runner, lines


@needs_tesseract
def test_board_image_is_readable_by_real_ocr(tmp_path):
    from pipeline.board_ocr import read_board

    path = tmp_path / "board.png"
    path.write_bytes(smoke.board_image())
    text = read_board(str(path))
    assert sum(w in text for w in ("Konstitusiya", "Məclis", "Prezident", "125", "1995")) >= 4


@needs_tesseract
def test_full_chain_passes_and_reuses_smoke_class(env, monkeypatch):
    monkeypatch.setattr(smoke.time, "sleep", lambda s: None)
    ok, runner, lines = _run(env)
    assert ok, "\n".join(lines)
    names = [name for name, _, _ in runner.results]
    assert names[0] == "Giriş (müəllim)" and names[-1] == "Dərsi bitir"
    assert "AI tutor" in names and "Quiz (AI)" in names
    first_class = runner.chat_id

    ok, runner, lines = _run(env, skip_ai=True)
    assert ok and runner.chat_id == first_class  # ikinci işdə yeni sinif yaranmır
    assert "Quiz (AI)" not in [name for name, _, _ in runner.results]


def test_wrong_password_stops_at_login(env):
    ok, runner, lines = _run(env, password="yanlis-parol")
    assert not ok and len(runner.results) == 1 and "401" in lines[0]


def test_student_account_is_rejected(env):
    ok, _, lines = _run(env, email="s@x.az")
    assert not ok and "müəllim deyil" in lines[0]


@needs_tesseract
def test_video_without_livekit_is_reported_but_chain_continues(env, monkeypatch):
    monkeypatch.setattr(smoke.time, "sleep", lambda s: None)
    app.dependency_overrides[get_livekit_config] = lambda: None
    ok, runner, lines = _run(env)
    failed = [name for name, passed, _ in runner.results if not passed]
    assert not ok and failed == ["Video tokeni (LiveKit)"]
    assert any("LiveKit açarları" in line for line in lines)
    assert runner.results[-1][0] == "Dərsi bitir" and runner.results[-1][1]
