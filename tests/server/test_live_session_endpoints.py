import pytest
from fastapi.testclient import TestClient

from pipeline.models import MCQQuestion
from server.app import (
    app,
    get_chat_store,
    get_live_session_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.chat_store import ChatStore
from server.auth import create_token
from server.live_session_runner import join_session, record_answer, request_next, start_session
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")
    chats = ChatStore(":memory:")

    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")
    # `set_teacher` MƏCBURİDİR: `/live/*` endpointləri artıq müəllim
    # qapısından keçir (bax `get_current_teacher`). Əvvəl bu fixture
    # «müəllim» adlı ADİ istifadəçi yaradırdı - qapının beş yerdə
    # unudulmasının görünməməsinin səbəbi məhz bu idi.
    users.set_teacher(teacher["id"], True)
    teacher = users.get_by_id(teacher["id"])

    # `chat_id` ARTIQ MƏCBURİDİR: sessiya bir sinfə bağlıdır və müəllim
    # həmin çatın üzvü olmalıdır (bax `test_live_session_in_chat.py`).
    chat = chats.create(kind="group", created_by=teacher["id"], name="11-A")
    chats.add_member(chat["id"], teacher["id"])

    yield {
        "client": client, "question_sets": question_sets,
        "live_sessions": live_sessions, "teacher": teacher, "chat": chat,
    }
    app.dependency_overrides.clear()


def _auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user['id'], secret=_SECRET)}"}


def test_requires_auth(env):
    r = env["client"].post("/live/sessions", json={"question_set_id": 1, "chat_id": 1})
    assert r.status_code == 401


def test_unknown_question_set_returns_404(env):
    r = env["client"].post("/live/sessions", json={"question_set_id": 999, "chat_id": env["chat"]["id"]}, headers=_auth(env["teacher"]))
    assert r.status_code == 404


def test_not_ready_question_set_returns_400(env):
    qs = env["question_sets"].create(
        subject="mentiq", title="A", material_kind="link", material_location="https://x.az",
        created_by=env["teacher"]["id"],
    )
    r = env["client"].post("/live/sessions", json={"question_set_id": qs["id"], "chat_id": env["chat"]["id"]}, headers=_auth(env["teacher"]))
    assert r.status_code == 400


def test_creates_session_with_pin(env):
    qs = env["question_sets"].create(
        subject="mentiq", title="A", material_kind="link", material_location="https://x.az",
        created_by=env["teacher"]["id"],
    )
    env["question_sets"].mark_ready(qs["id"])

    r = env["client"].post("/live/sessions", json={"question_set_id": qs["id"], "chat_id": env["chat"]["id"]}, headers=_auth(env["teacher"]))
    assert r.status_code == 201
    body = r.json()
    assert body["question_set_id"] == qs["id"]
    assert body["status"] == "waiting"
    assert len(body["pin"]) == 6


class _NoopConnectionManager:
    async def broadcast_host(self, session_id, message):
        pass

    async def broadcast_players(self, session_id, message):
        pass

    async def send_to_player(self, session_id, participant_id, message):
        pass


class TestGetReport:
    def test_requires_auth(self, env):
        r = env["client"].get("/live/sessions/1/report")
        assert r.status_code == 401

    def test_unknown_session_returns_404(self, env):
        r = env["client"].get("/live/sessions/999/report", headers=_auth(env["teacher"]))
        assert r.status_code == 404

    def test_not_finished_session_returns_400(self, env):
        qs = env["question_sets"].create(
            subject="mentiq", title="A", material_kind="link", material_location="https://x.az",
            created_by=env["teacher"]["id"],
        )
        env["question_sets"].mark_ready(qs["id"])
        session = env["live_sessions"].create_session(qs["id"])

        r = env["client"].get(f"/live/sessions/{session['id']}/report", headers=_auth(env["teacher"]))
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_finished_session_returns_cached_report(self, env):
        qs = env["question_sets"].create(
            subject="mentiq", title="A", material_kind="link", material_location="https://x.az",
            created_by=env["teacher"]["id"],
        )
        env["question_sets"].add_question(
            qs["id"],
            MCQQuestion(question="Sual 1?", options=["A", "B", "C", "D", "E"], correct_index=0, explanation="izah"),
        )
        env["question_sets"].mark_ready(qs["id"])
        session = env["live_sessions"].create_session(qs["id"])

        manager = _NoopConnectionManager()
        _, participant = await join_session(session["pin"], "Əli", session_store=env["live_sessions"], connection_manager=manager)
        await start_session(session["id"], session_store=env["live_sessions"], question_set_store=env["question_sets"], connection_manager=manager)
        await record_answer(
            session["id"], participant["id"], 0, chosen_index=0,
            session_store=env["live_sessions"], question_set_store=env["question_sets"], connection_manager=manager,
        )
        # tək sual, tək iştirakçı — öz "Növbəti"si sessiyanı fərdi tempo
        # modelində bitirir (bax `request_next`, avtomatik irəliləmə YOXDUR)
        await request_next(
            session["id"], participant["id"],
            session_store=env["live_sessions"], question_set_store=env["question_sets"], connection_manager=manager,
        )

        r = env["client"].get(f"/live/sessions/{session['id']}/report", headers=_auth(env["teacher"]))
        assert r.status_code == 200
        body = r.json()
        assert body["session_id"] == session["id"]
        assert body["total_questions"] == 1
        assert body["rankings"] == [
            {"rank": 1, "participant_id": participant["id"], "display_name": "Əli", "score": 1}
        ]
        assert body["per_question"][0]["correct_count"] == 1
