"""Canlı sessiya WS endpoint-lərinin bağlanma/qoşulma səviyyəli testləri.

QEYD: bura qəsdən HƏR TEST-də TƏK WebSocket bağlantısı ilə sınanır (host
VƏ player-in EYNİ ANDA qoşulub qarşılıqlı təsirləşdiyi ssenari YOX) —
Starlette `TestClient`-in hər WebSocket bağlantısını ayrı OS thread-ində
işlətdiyi, bunun da real thread olmadan tam doğrulanmış biznes-məntiqi
(bax `test_live_session_runner.py`, `FakeConnectionManager` ilə) test
mühitində asma yaratdığı artıq `test_quiz_websocket.py`-də sənədləşdirilib
— eyni tələni təkrarlamırıq. Bura yalnız REST+WS "tellərinin" (auth,
PIN axtarışı, qoşulma qəbulu) qırılmadığını yoxlayır.
"""

import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_live_connection_manager,
    get_live_session_store,
    get_question_set_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.live_connection_manager import LiveConnectionManager
from server.live_session_store import LiveSessionStore
from server.question_set_store import QuestionSetStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    question_sets = QuestionSetStore(":memory:")
    live_sessions = LiveSessionStore(":memory:")
    manager = LiveConnectionManager()

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_question_set_store] = lambda: question_sets
    app.dependency_overrides[get_live_session_store] = lambda: live_sessions
    app.dependency_overrides[get_live_connection_manager] = lambda: manager
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)
    teacher = users.create("teacher@masternr1.az", "hash", "Müəllim")

    qs = question_sets.create(
        subject="mentiq", title="A", material_kind="link", material_location="https://x.az",
        created_by=teacher["id"],
    )
    question_sets.mark_ready(qs["id"])
    session = live_sessions.create_session(qs["id"])

    yield {"client": client, "live_sessions": live_sessions, "teacher": teacher, "session": session}
    app.dependency_overrides.clear()


def _host_url(pin: str, user: dict) -> str:
    token = create_token(user["id"], secret=_SECRET)
    return f"/ws/live/{pin}/host?token={token}"


class TestHostWebSocket:
    def test_invalid_token_closes_connection(self, env):
        """Rədd SƏBƏBİ ilə olmalıdır: `accept()`-dən əvvəl bağlansa,
        brauzerə 4401 yox, 1006 çatır və client sonsuz yenidən qoşulur
        (real produksiyada baş verdi)."""
        with env["client"].websocket_connect(
            f"/ws/live/{env['session']['pin']}/host?token=zibil"
        ) as ws:
            payload = ws.receive_json()
            closing = ws.receive()
        assert closing.get("code") == 4401
        assert payload["type"] == "error" and payload["detail"]

    def test_unknown_pin_closes_connection(self, env):
        with env["client"].websocket_connect(_host_url("000000", env["teacher"])) as ws:
            payload = ws.receive_json()
            closing = ws.receive()
        assert closing.get("code") == 4404
        assert payload["type"] == "error" and payload["detail"]

    def test_valid_connection_receives_waiting_state(self, env):
        with env["client"].websocket_connect(_host_url(env["session"]["pin"], env["teacher"])) as ws:
            state = ws.receive_json()
            assert state["type"] == "state"
            assert state["status"] == "waiting"
            assert state["participants"] == []


class TestPlayWebSocket:
    def test_unknown_pin_closes_connection(self, env):
        with pytest.raises(Exception):
            with env["client"].websocket_connect("/ws/live/000000/play") as ws:
                ws.send_json({"display_name": "Əli"})
                ws.receive_json()

    def test_missing_display_name_closes_connection(self, env):
        with pytest.raises(Exception):
            with env["client"].websocket_connect(f"/ws/live/{env['session']['pin']}/play") as ws:
                ws.send_json({})
                ws.receive_json()

    def test_valid_join_receives_participant_id(self, env):
        with env["client"].websocket_connect(f"/ws/live/{env['session']['pin']}/play") as ws:
            ws.send_json({"display_name": "Əli"})
            joined = ws.receive_json()
            assert joined["type"] == "joined"
            assert joined["session_id"] == env["session"]["id"]

        participants = env["live_sessions"].list_participants(env["session"]["id"])
        assert [p["display_name"] for p in participants] == ["Əli"]

    def test_join_to_already_active_session_closes_connection(self, env):
        env["live_sessions"].set_status(env["session"]["id"], "active")
        with pytest.raises(Exception):
            with env["client"].websocket_connect(f"/ws/live/{env['session']['pin']}/play") as ws:
                ws.send_json({"display_name": "Əli"})
                ws.receive_json()

    def test_join_with_valid_token_links_participant_to_user(self, env):
        token = create_token(env["teacher"]["id"], secret=_SECRET)
        with env["client"].websocket_connect(f"/ws/live/{env['session']['pin']}/play") as ws:
            ws.send_json({"display_name": "Əli", "token": token})
            joined = ws.receive_json()
            assert joined["type"] == "joined"

        participants = env["live_sessions"].list_participants(env["session"]["id"])
        assert participants[0]["user_id"] == env["teacher"]["id"]

    def test_join_with_invalid_token_still_joins_anonymously(self, env):
        with env["client"].websocket_connect(f"/ws/live/{env['session']['pin']}/play") as ws:
            ws.send_json({"display_name": "Əli", "token": "zibil"})
            joined = ws.receive_json()
            assert joined["type"] == "joined"

        participants = env["live_sessions"].list_participants(env["session"]["id"])
        assert participants[0]["user_id"] is None
