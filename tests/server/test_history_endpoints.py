import json

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_homework_store,
    get_live_session_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    homework = HomeworkStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_homework_store] = lambda: homework
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("tələbə@masternr1.az", "hash", "Tələbə")
    outsider = users.create("kənar@masternr1.az", "hash", "Kənar")

    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif")
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])

    yield {
        "client": client, "users": users, "chats": chats, "question_sets": question_sets,
        "homework": homework, "live_sessions": live_sessions,
        "teacher": teacher, "student": student, "outsider": outsider, "chat": chat,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _ready_question_set(env, n_questions=2, subject="mentiq", title="Silloqizmlər"):
    qs = env["question_sets"].create(
        subject=subject, title=title, material_kind="link",
        material_location="https://x.az", created_by=env["teacher"]["id"],
    )
    for i in range(n_questions):
        env["question_sets"].add_question(
            qs["id"],
            MCQQuestion(
                question=f"Sual {i}?", options=["A", "B", "C", "D", "E"],
                correct_index=0, explanation=f"izah {i}",
            ),
        )
    env["question_sets"].mark_ready(qs["id"])
    return qs


def _finished_live_session(env, *, user_id, score, total_questions=2):
    qs = _ready_question_set(env, n_questions=total_questions, subject="fizika", title="Kinematika")
    session = env["live_sessions"].create_session(qs["id"])
    participant = env["live_sessions"].add_participant(session["id"], "Ad", user_id=user_id)
    report = {
        "session_id": session["id"],
        "total_questions": total_questions,
        "rankings": [{"rank": 1, "participant_id": participant["id"], "display_name": "Ad", "score": score}],
        "per_question": [],
    }
    env["live_sessions"].save_report(session["id"], json.dumps(report))
    env["live_sessions"].set_status(session["id"], "finished")
    return session, qs


def _completed_homework(env, *, student_id, score, total_questions=2):
    qs = _ready_question_set(env, n_questions=total_questions)
    assignment = env["homework"].create_assignment(
        env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"]
    )
    attempt = env["homework"].get_or_create_attempt(assignment["id"], student_id=student_id)
    for i in range(score):
        env["homework"].answer(attempt["id"], i, chosen_index=0, is_correct=True, total_questions=total_questions)
    for i in range(score, total_questions):
        env["homework"].answer(attempt["id"], i, chosen_index=1, is_correct=False, total_questions=total_questions)
    return assignment, qs


class TestMyHistory:
    def test_requires_auth(self, env):
        assert env["client"].get("/history/me").status_code == 401

    def test_empty_when_nothing_done(self, env):
        r = env["client"].get("/history/me", headers=_auth(env["student"]))
        assert r.status_code == 200
        assert r.json() == []

    def test_includes_finished_live_session(self, env):
        _finished_live_session(env, user_id=env["student"]["id"], score=2)
        r = env["client"].get("/history/me", headers=_auth(env["student"]))
        assert r.status_code == 200
        entries = r.json()
        assert len(entries) == 1
        assert entries[0]["kind"] == "live"
        assert entries[0]["subject"] == "fizika"
        assert entries[0]["score"] == 2
        assert entries[0]["total_questions"] == 2

    def test_ignores_anonymous_participation(self, env):
        qs = _ready_question_set(env)
        session = env["live_sessions"].create_session(qs["id"])
        env["live_sessions"].add_participant(session["id"], "Qonaq")  # user_id=None
        env["live_sessions"].set_status(session["id"], "finished")
        r = env["client"].get("/history/me", headers=_auth(env["student"]))
        assert r.json() == []

    def test_includes_completed_homework(self, env):
        _completed_homework(env, student_id=env["student"]["id"], score=1)
        r = env["client"].get("/history/me", headers=_auth(env["student"]))
        entries = r.json()
        assert len(entries) == 1
        assert entries[0]["kind"] == "homework"
        assert entries[0]["score"] == 1
        assert entries[0]["chat_id"] == env["chat"]["id"]

    def test_excludes_in_progress_homework(self, env):
        qs = _ready_question_set(env)
        assignment = env["homework"].create_assignment(
            env["chat"]["id"], qs["id"], "2026-09-14", created_by=env["teacher"]["id"]
        )
        env["homework"].get_or_create_attempt(assignment["id"], student_id=env["student"]["id"])
        r = env["client"].get("/history/me", headers=_auth(env["student"]))
        assert r.json() == []

    def test_combines_and_sorts_both_kinds(self, env):
        _finished_live_session(env, user_id=env["student"]["id"], score=2)
        _completed_homework(env, student_id=env["student"]["id"], score=1)
        r = env["client"].get("/history/me", headers=_auth(env["student"]))
        entries = r.json()
        assert len(entries) == 2
        kinds = {e["kind"] for e in entries}
        assert kinds == {"live", "homework"}


class TestStudentHistory:
    def test_requires_auth(self, env):
        assert env["client"].get(f"/history/student/{env['student']['id']}").status_code == 401

    def test_non_teacher_gets_403(self, env):
        r = env["client"].get(f"/history/student/{env['teacher']['id']}", headers=_auth(env["student"]))
        assert r.status_code == 403

    def test_teacher_without_shared_chat_gets_403(self, env):
        r = env["client"].get(f"/history/student/{env['outsider']['id']}", headers=_auth(env["teacher"]))
        assert r.status_code == 403

    def test_teacher_sees_student_history(self, env):
        _completed_homework(env, student_id=env["student"]["id"], score=1)
        r = env["client"].get(f"/history/student/{env['student']['id']}", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        entries = r.json()
        assert len(entries) == 1
        assert entries[0]["kind"] == "homework"


class TestChatMembers:
    def test_requires_auth(self, env):
        assert env["client"].get(f"/chats/{env['chat']['id']}/members").status_code == 401

    def test_non_member_gets_403(self, env):
        r = env["client"].get(f"/chats/{env['chat']['id']}/members", headers=_auth(env["outsider"]))
        assert r.status_code == 403

    def test_unknown_chat_returns_404(self, env):
        r = env["client"].get("/chats/999/members", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_member_lists_all_members(self, env):
        r = env["client"].get(f"/chats/{env['chat']['id']}/members", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        user_ids = {row["user_id"] for row in r.json()}
        assert user_ids == {env["teacher"]["id"], env["student"]["id"]}
