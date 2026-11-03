"""`GET/POST /homework/assignments/{id}/discussion` — Tapşırıq müzakirəsi
(Faza 3 PR 2). Sinif çatından AYRI mövzu, amma icazə eynidir: tapşırığı
yaradan müəllim VƏ çatın hər üzvü (tələbə daxil) iştirak edə bilər."""

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import app, get_chat_store, get_homework_store, get_question_set_store, get_token_secret, get_user_store
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    homework = HomeworkStore(":memory:")

    for dep, value in {
        get_user_store: users, get_chat_store: chats, get_question_set_store: question_sets,
        get_homework_store: homework, get_token_secret: _SECRET,
    }.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("telebe@masternr1.az", "hash", "Tələbə")
    other = users.create("basqa@masternr1.az", "hash", "Başqası")
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif")
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])

    qs = question_sets.create(
        subject="mentiq", title="Silloqizmlər", material_kind="link",
        material_location="https://x.az", created_by=teacher["id"],
    )
    question_sets.add_question(
        qs["id"], MCQQuestion(question="Sual?", options=["A", "B", "C", "D", "E"],
                               correct_index=0, explanation="izah"),
    )
    question_sets.mark_ready(qs["id"])
    assignment = homework.create_assignment(chat["id"], qs["id"], "2026-09-14", created_by=teacher["id"])

    yield {
        "client": client, "teacher": teacher, "student": student, "other": other,
        "chat": chat, "assignment": assignment,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _url(env, suffix=""):
    return f"/homework/assignments/{env['assignment']['id']}/discussion{suffix}"


class TestListDiscussion:
    def test_requires_auth(self, env):
        assert env["client"].get(_url(env)).status_code == 401

    def test_non_member_gets_403(self, env):
        r = env["client"].get(_url(env), headers=_auth(env["other"]))
        assert r.status_code == 403

    def test_unknown_assignment_returns_404(self, env):
        r = env["client"].get("/homework/assignments/999/discussion", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_empty_by_default(self, env):
        r = env["client"].get(_url(env), headers=_auth(env["student"]))
        assert r.status_code == 200
        assert r.json() == []


class TestPostDiscussion:
    def test_requires_auth(self, env):
        assert env["client"].post(_url(env), json={"content": "salam"}).status_code == 401

    def test_non_member_gets_403(self, env):
        r = env["client"].post(_url(env), json={"content": "salam"}, headers=_auth(env["other"]))
        assert r.status_code == 403

    def test_blank_content_rejected(self, env):
        r = env["client"].post(_url(env), json={"content": "   "}, headers=_auth(env["student"]))
        assert r.status_code == 400

    def test_student_can_post_and_sees_display_name(self, env):
        r = env["client"].post(_url(env), json={"content": "Bu sualı anlamadım."}, headers=_auth(env["student"]))
        assert r.status_code == 201
        body = r.json()
        assert body["content"] == "Bu sualı anlamadım."
        assert body["display_name"] == "Tələbə"
        assert body["sender_id"] == env["student"]["id"]

    def test_teacher_can_post(self, env):
        r = env["client"].post(_url(env), json={"content": "2-ci sualı nəzərdə tuturam."}, headers=_auth(env["teacher"]))
        assert r.status_code == 201
        assert r.json()["display_name"] == "Müəllim"

    def test_messages_appear_in_order_for_both_sides(self, env):
        env["client"].post(_url(env), json={"content": "Sual 1"}, headers=_auth(env["student"]))
        env["client"].post(_url(env), json={"content": "Cavab 1"}, headers=_auth(env["teacher"]))
        r = env["client"].get(_url(env), headers=_auth(env["student"]))
        contents = [m["content"] for m in r.json()]
        assert contents == ["Sual 1", "Cavab 1"]
