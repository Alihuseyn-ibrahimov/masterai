"""Quiz olmadan konspekt (istifadəçi əlavəsi, 2026-11-03).

Müəllim material yükləyəndə sual bankı yaratmağı gözləmədən birbaşa
dərs xülasəsi sifariş edə bilsin. `skip_questions=true` göndəriləndə:
- MCQ generatoru ÇAĞIRILMIR, bank dərhal "ready" olur, 0 sualla;
- `make_summary` client nə göndərsə də MƏCBURƏN true-dur (əks halda
  heç nə əmələ gəlməzdi);
- belə bank canlı sessiya/ev tapşırığı üçün 400 ilə rədd olunur.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pipeline.summary import LessonSummary
from server.app import (
    app,
    get_chat_store,
    get_connection_manager,
    get_homework_store,
    get_material_generator,
    get_question_set_store,
    get_summarizer,
    get_summary_store,
    get_token_secret,
    get_upload_dir,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.homework_store import HomeworkStore
from server.question_set_store import QuestionSetStore
from server.summary_store import SummaryStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"
_CONTENT = {
    "title": "Konstitusiya", "intro": "Əsas qanun.",
    "key_points": ["Hakimiyyət üç qola bölünür."],
    "terms": [], "facts": [], "self_check": [],
}


class _Generator:
    """Çağırılsa testi SINDIRIR - skip_questions-un bunu çağırmaması
    əsas şərtdir."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("skip_questions=true olanda generator ÇAĞIRILMAMALIDIR")


def _fake_summarizer(source):
    return LessonSummary(**_CONTENT)


@pytest.fixture
def env(tmp_path):
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    homework = HomeworkStore(":memory:")
    summaries = SummaryStore(":memory:")
    generator = _Generator()
    overrides = {
        get_user_store: users, get_chat_store: chats, get_question_set_store: question_sets,
        get_homework_store: homework, get_summary_store: summaries,
        get_material_generator: generator, get_summarizer: _fake_summarizer,
        get_upload_dir: str(tmp_path), get_token_secret: _SECRET,
        get_connection_manager: ConnectionManager(),
    }
    for dep, value in overrides.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    teacher = users.create("t@x.az", "h", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("s@x.az", "h", "Tələbə")
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif")
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])

    with TestClient(app) as client:
        yield {
            "client": client, "question_sets": question_sets, "summaries": summaries,
            "teacher": teacher, "student": student, "chat": chat, "generator": generator,
        }
    app.dependency_overrides.clear()


def _auth(user):
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _wait_ready(question_sets, qs_id, timeout=5.0):
    deadline = time.time() + timeout
    qs = question_sets.get(qs_id)
    while qs["status"] == "processing" and time.time() < deadline:
        time.sleep(0.02)
        qs = question_sets.get(qs_id)
    return qs


def _wait_summary(summaries, qs_id, timeout=5.0):
    deadline = time.time() + timeout
    row = summaries.get_for_question_set(qs_id)
    while (row is None or row["status"] == "processing") and time.time() < deadline:
        time.sleep(0.02)
        row = summaries.get_for_question_set(qs_id)
    return row


class TestSkipQuestions:
    def test_creates_ready_bank_with_zero_questions_and_skips_generator(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={
                "subject": "mentiq", "title": "Konstitusiya", "kind": "link",
                "location": "https://x.az", "skip_questions": "true",
            },
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 202
        qs_id = r.json()["id"]

        qs = _wait_ready(env["question_sets"], qs_id)
        assert qs["status"] == "ready"
        assert env["question_sets"].count_questions(qs_id) == 0
        assert env["generator"].calls == 0

    def test_forces_make_summary_even_if_not_sent(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={
                "subject": "mentiq", "title": "Konstitusiya", "kind": "link",
                "location": "https://x.az", "skip_questions": "true",
            },
            headers=_auth(env["teacher"]),
        )
        qs_id = r.json()["id"]
        _wait_ready(env["question_sets"], qs_id)

        summary = _wait_summary(env["summaries"], qs_id)
        assert summary is not None
        assert summary["status"] == "ready"

    def test_reading_bank_rejected(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={
                "subject": "mentiq", "title": "A", "kind": "link", "location": "https://x.az",
                "skip_questions": "true", "bank_kind": "reading",
            },
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 400

    def test_live_session_rejects_zero_question_bank(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={
                "subject": "mentiq", "title": "A", "kind": "link", "location": "https://x.az",
                "skip_questions": "true",
            },
            headers=_auth(env["teacher"]),
        )
        qs_id = r.json()["id"]
        _wait_ready(env["question_sets"], qs_id)

        session = env["client"].post(
            "/live/sessions",
            json={"question_set_id": qs_id, "chat_id": env["chat"]["id"]},
            headers=_auth(env["teacher"]),
        )
        assert session.status_code == 400
        assert "xülasə" in session.json()["detail"]

    def test_homework_assignment_rejects_zero_question_bank(self, env):
        r = env["client"].post(
            "/live/question-sets",
            data={
                "subject": "mentiq", "title": "A", "kind": "link", "location": "https://x.az",
                "skip_questions": "true",
            },
            headers=_auth(env["teacher"]),
        )
        qs_id = r.json()["id"]
        _wait_ready(env["question_sets"], qs_id)

        a = env["client"].post(
            "/homework/assignments",
            json={"chat_id": env["chat"]["id"], "question_set_id": qs_id, "due_date": "2099-01-01"},
            headers=_auth(env["teacher"]),
        )
        assert a.status_code == 400
        assert "xülasə" in a.json()["detail"]
