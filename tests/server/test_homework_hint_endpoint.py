"""`POST /homework/attempts/{id}/hint` — Sokratik köməkçi (Faza 2 PR 1).

STATELESS-dir: homework_store-a heç nə yazmır, "tək cəhd" qaydasına
toxunmur. Yalnız ev tapşırığındadır - canlı sessiyada bu marşrut yoxdur."""

import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from pipeline.socratic import SocraticError
from server.app import (
    app,
    get_chat_store,
    get_hint_rate_limiter,
    get_homework_store,
    get_question_set_store,
    get_socratic_hinter,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.homework_store import HomeworkStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore
from server.rate_limit import RateLimiter

_SECRET = "test-secret-key-32-chars-minimum!!"


def _fake_hinter(source, question, options, chosen_index, correct_index):
    return f"Yönləndirici sual: {question} üçün yenidən düşünün."


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    homework = HomeworkStore(":memory:")

    for dep, value in {
        get_user_store: users, get_chat_store: chats, get_question_set_store: question_sets,
        get_homework_store: homework, get_token_secret: _SECRET,
        get_socratic_hinter: _fake_hinter, get_hint_rate_limiter: RateLimiter(100, 600),
    }.items():
        app.dependency_overrides[dep] = (lambda v: lambda: v)(value)

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])
    student = users.create("telebe@masternr1.az", "hash", "Tələbə")
    chat = chats.create(kind="group", created_by=teacher["id"], name="Sinif")
    chats.add_member(chat["id"], teacher["id"])
    chats.add_member(chat["id"], student["id"])

    qs = question_sets.create(
        subject="mentiq", title="Silloqizmlər", material_kind="link",
        material_location="https://x.az", created_by=teacher["id"],
    )
    for i in range(2):
        question_sets.add_question(
            qs["id"],
            MCQQuestion(question=f"Sual {i}?", options=["A", "B", "C", "D", "E"],
                        correct_index=0, explanation=f"izah {i}"),
        )
    question_sets.mark_ready(qs["id"])
    assignment = homework.create_assignment(chat["id"], qs["id"], "2026-09-14", created_by=teacher["id"])

    yield {
        "client": client, "homework": homework, "question_sets": question_sets,
        "teacher": teacher, "student": student, "chat": chat, "qs": qs, "assignment": assignment,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def _start(env):
    r = env["client"].post(f"/homework/assignments/{env['assignment']['id']}/start", headers=_auth(env["student"]))
    return r.json()["attempt_id"]


class TestHint:
    def test_requires_auth(self, env):
        r = env["client"].post(
            "/homework/attempts/1/hint", json={"question_index": 0, "chosen_index": 1},
        )
        assert r.status_code == 401

    def test_unknown_attempt_returns_404(self, env):
        r = env["client"].post(
            "/homework/attempts/999/hint", json={"question_index": 0, "chosen_index": 1},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 404

    def test_other_students_attempt_returns_404(self, env):
        attempt_id = _start(env)
        r = env["client"].post(
            f"/homework/attempts/{attempt_id}/hint", json={"question_index": 0, "chosen_index": 1},
            headers=_auth(env["teacher"]),
        )
        assert r.status_code == 404

    def test_correct_choice_returns_no_hint_and_does_not_advance(self, env):
        attempt_id = _start(env)
        r = env["client"].post(
            f"/homework/attempts/{attempt_id}/hint", json={"question_index": 0, "chosen_index": 0},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert body == {"is_correct": True, "hint": None}
        # Stateless - "tək cəhd" qaydası pozulmayıb, sual hələ cavablanmayıb.
        assert env["homework"].get_attempt(attempt_id)["current_question_index"] == 0

    def test_wrong_choice_returns_hint_and_does_not_advance(self, env):
        attempt_id = _start(env)
        r = env["client"].post(
            f"/homework/attempts/{attempt_id}/hint", json={"question_index": 0, "chosen_index": 1},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["is_correct"] is False
        assert "Yönləndirici sual" in body["hint"]
        assert env["homework"].get_attempt(attempt_id)["current_question_index"] == 0
        assert env["homework"].get_attempt(attempt_id)["score"] == 0

    def test_can_ask_for_hint_repeatedly_then_still_submit_final_answer(self, env):
        attempt_id = _start(env)
        for _ in range(3):
            r = env["client"].post(
                f"/homework/attempts/{attempt_id}/hint", json={"question_index": 0, "chosen_index": 2},
                headers=_auth(env["student"]),
            )
            assert r.status_code == 200 and r.json()["is_correct"] is False
        # Son nəhayət doğru cavabı /answer ilə göndərir - score dəyişir.
        final = env["client"].post(
            f"/homework/attempts/{attempt_id}/answer", json={"question_index": 0, "chosen_index": 0},
            headers=_auth(env["student"]),
        )
        assert final.status_code == 200 and final.json()["is_correct"] is True
        assert env["homework"].get_attempt(attempt_id)["score"] == 1

    def test_not_current_question_returns_400(self, env):
        attempt_id = _start(env)
        r = env["client"].post(
            f"/homework/attempts/{attempt_id}/hint", json={"question_index": 1, "chosen_index": 1},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 400

    def test_completed_attempt_returns_400(self, env):
        attempt_id = _start(env)
        for i in range(2):
            env["client"].post(
                f"/homework/attempts/{attempt_id}/answer", json={"question_index": i, "chosen_index": 0},
                headers=_auth(env["student"]),
            )
        r = env["client"].post(
            f"/homework/attempts/{attempt_id}/hint", json={"question_index": 0, "chosen_index": 1},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 400

    def test_rate_limit_returns_429(self, env):
        # BİR instansı tutub geri qaytarmaq lazımdır - hər sorğuda təzə
        # `RateLimiter(1, 600)` yaratmaq sayğacı hər dəfə sıfırlayardı.
        limiter = RateLimiter(1, 600)
        app.dependency_overrides[get_hint_rate_limiter] = lambda: limiter
        attempt_id = _start(env)
        ok = env["client"].post(
            f"/homework/attempts/{attempt_id}/hint", json={"question_index": 0, "chosen_index": 1},
            headers=_auth(env["student"]),
        )
        assert ok.status_code == 200
        blocked = env["client"].post(
            f"/homework/attempts/{attempt_id}/hint", json={"question_index": 0, "chosen_index": 2},
            headers=_auth(env["student"]),
        )
        assert blocked.status_code == 429

    def test_hinter_failure_returns_503(self, env):
        def failing(*args):
            raise SocraticError("bütün provayderlər uğursuz oldu")
        app.dependency_overrides[get_socratic_hinter] = lambda: failing
        attempt_id = _start(env)
        r = env["client"].post(
            f"/homework/attempts/{attempt_id}/hint", json={"question_index": 0, "chosen_index": 1},
            headers=_auth(env["student"]),
        )
        assert r.status_code == 503
