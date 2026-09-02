import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_friendship_store,
    get_material_store,
    get_question_store,
    get_quiz_session_store,
    get_user_store,
)
from server.friendship_store import FriendshipStore
from server.material_store import MaterialStore
from server.question_store import QuestionStore
from server.quiz_session_store import QuizSessionStore
from server.user_store import UserStore


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")

    users = UserStore(":memory:")
    materials = MaterialStore(":memory:")
    questions = QuestionStore(":memory:")
    sessions = QuizSessionStore(":memory:")
    friendships = FriendshipStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_material_store] = lambda: materials
    app.dependency_overrides[get_question_store] = lambda: questions
    app.dependency_overrides[get_quiz_session_store] = lambda: sessions
    app.dependency_overrides[get_friendship_store] = lambda: friendships

    client = TestClient(app)
    yield {
        "client": client,
        "users": users,
        "materials": materials,
        "questions": questions,
        "sessions": sessions,
        "friendships": friendships,
    }
    app.dependency_overrides.clear()


def _mcq() -> MCQQuestion:
    return MCQQuestion(
        question="S?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah"
    )


class TestAdminStats:
    def test_missing_key_returns_403(self, env):
        r = env["client"].get("/admin/stats")
        assert r.status_code == 403

    def test_wrong_key_returns_403(self, env):
        r = env["client"].get("/admin/stats", headers={"X-Admin-Key": "wrong-key"})
        assert r.status_code == 403

    def test_admin_key_not_configured_returns_403(self, env, monkeypatch):
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
        r = env["client"].get("/admin/stats", headers={"X-Admin-Key": ""})
        assert r.status_code == 403

    def test_correct_key_returns_accurate_counts(self, env):
        users, materials, questions, sessions, friendships = (
            env["users"],
            env["materials"],
            env["questions"],
            env["sessions"],
            env["friendships"],
        )

        u1 = users.create("ali@example.com", "hash", "Əli")
        u2 = users.create("vali@example.com", "hash", "Vəli")

        m1 = materials.create(chat_id=1, uploaded_by=u1["id"], kind="pdf", location="/a.pdf")
        materials.create(chat_id=1, uploaded_by=u1["id"], kind="link", location="https://x.az")
        materials.update_status(m1["id"], "ready")

        questions.create_from_mcq(m1["id"], _mcq())
        questions.create_from_mcq(m1["id"], _mcq())

        sessions.create(chat_id=1, material_id=m1["id"], question_ids=[1, 2])

        f = friendships.create(u1["id"], u2["id"])
        friendships.update_status(f["id"], "accepted")

        r = env["client"].get("/admin/stats", headers={"X-Admin-Key": "test-admin-key"})
        assert r.status_code == 200
        body = r.json()
        assert body["users_total"] == 2
        assert body["materials_total"] == 2
        assert body["materials_ready"] == 1
        assert body["materials_failed"] == 0
        assert body["questions_total"] == 2
        assert body["quiz_sessions_total"] == 1
        assert body["friendships_accepted"] == 1
