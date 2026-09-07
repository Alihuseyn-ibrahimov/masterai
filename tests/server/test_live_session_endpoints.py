import pytest
from fastapi.testclient import TestClient

from server.app import app, get_live_session_store, get_question_set_store, get_token_secret, get_user_store
from server.auth import create_token
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")

    yield {"client": client, "question_sets": question_sets, "live_sessions": live_sessions, "teacher": teacher}
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def test_requires_auth(env):
    r = env["client"].post("/live/sessions", json={"question_set_id": 1})
    assert r.status_code == 401


def test_unknown_question_set_returns_404(env):
    r = env["client"].post("/live/sessions", json={"question_set_id": 999}, headers=_auth(env["teacher"]))
    assert r.status_code == 404


def test_not_ready_question_set_returns_400(env):
    qs = env["question_sets"].create(
        subject="mentiq", title="A", material_kind="link", material_location="https://x.az",
        created_by=env["teacher"]["id"],
    )
    r = env["client"].post("/live/sessions", json={"question_set_id": qs["id"]}, headers=_auth(env["teacher"]))
    assert r.status_code == 400


def test_creates_session_with_pin(env):
    qs = env["question_sets"].create(
        subject="mentiq", title="A", material_kind="link", material_location="https://x.az",
        created_by=env["teacher"]["id"],
    )
    env["question_sets"].mark_ready(qs["id"])

    r = env["client"].post("/live/sessions", json={"question_set_id": qs["id"]}, headers=_auth(env["teacher"]))
    assert r.status_code == 201
    body = r.json()
    assert body["question_set_id"] == qs["id"]
    assert body["status"] == "waiting"
    assert len(body["pin"]) == 6
