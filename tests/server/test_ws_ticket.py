"""Birdəfəlik WebSocket ticket-i: JWT artıq URL-də getmir."""
import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_store,
    get_connection_manager,
    get_message_store,
    get_token_secret,
    get_user_store,
    get_ws_ticket_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.message_store import MessageStore
from server.user_store import UserStore
from server.ws_ticket import MAX_TICKETS, WsTicketStore

_SECRET = "test-secret-key-32-chars-minimum!!"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# ---- Store ------------------------------------------------------------------

def test_ticket_is_single_use():
    store = WsTicketStore()
    ticket = store.issue(7)
    assert store.consume(ticket) == 7
    assert store.consume(ticket) is None


def test_ticket_expires():
    clock = FakeClock()
    store = WsTicketStore(ttl_seconds=60, clock=clock)
    ticket = store.issue(7)
    clock.now += 61
    assert store.consume(ticket) is None


def test_unknown_and_empty_ticket():
    store = WsTicketStore()
    assert store.consume("") is None
    assert store.consume("uydurma") is None


def test_tickets_are_unique_and_long():
    store = WsTicketStore()
    tickets = {store.issue(1) for _ in range(50)}
    assert len(tickets) == 50
    assert all(len(t) >= 40 for t in tickets)


def test_expired_tickets_are_pruned_on_issue():
    clock = FakeClock()
    store = WsTicketStore(ttl_seconds=60, clock=clock)
    for _ in range(5):
        store.issue(1)
    clock.now += 120
    store.issue(1)
    assert len(store) == 1


def test_store_is_bounded():
    store = WsTicketStore()
    first = store.issue(1)
    for _ in range(MAX_TICKETS):
        store.issue(2)
    assert len(store) == MAX_TICKETS
    assert store.consume(first) is None


# ---- Endpoint + WebSocket ---------------------------------------------------

@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    tickets = WsTicketStore()
    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_message_store] = lambda: MessageStore(":memory:")
    app.dependency_overrides[get_connection_manager] = lambda: ConnectionManager()
    app.dependency_overrides[get_token_secret] = lambda: _SECRET
    app.dependency_overrides[get_ws_ticket_store] = lambda: tickets

    ali = users.create("ali@example.com", "hash", "Əli")
    chat = chats.create(kind="group", created_by=ali["id"], name="Qrup")
    chats.add_member(chat["id"], ali["id"])
    yield {
        "client": TestClient(app),
        "chat_id": chat["id"],
        "auth": {"Authorization": f"Bearer {create_token(ali['id'], secret=_SECRET)}"},
        "token": create_token(ali["id"], secret=_SECRET),
    }
    app.dependency_overrides.clear()


def _ticket(env) -> str:
    resp = env["client"].post("/auth/ws-ticket", headers=env["auth"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == 60
    return body["ticket"]


def test_ticket_requires_login(env):
    assert env["client"].post("/auth/ws-ticket").status_code == 401


def test_ticket_is_not_the_jwt(env):
    ticket = _ticket(env)
    assert ticket != env["token"]
    assert "." not in ticket  # JWT deyil: içində istifadəçi məlumatı yoxdur


def test_chat_socket_accepts_ticket(env):
    ticket = _ticket(env)
    with env["client"].websocket_connect(f"/ws/chat/{env['chat_id']}?ticket={ticket}") as ws:
        assert ws.receive_json()["type"] == "history"


def test_reused_ticket_is_rejected(env):
    ticket = _ticket(env)
    url = f"/ws/chat/{env['chat_id']}?ticket={ticket}"
    with env["client"].websocket_connect(url) as ws:
        ws.receive_json()
    with env["client"].websocket_connect(url) as ws:
        payload = ws.receive_json()
        closing = ws.receive()
    assert payload["type"] == "error"
    assert closing.get("code") == 4401


def test_bad_ticket_does_not_fall_back_to_token(env):
    """Səhv ticket + keçərli token: ticket göndərilibsə yalnız o yoxlanır."""
    url = f"/ws/chat/{env['chat_id']}?ticket=uydurma&token={env['token']}"
    with env["client"].websocket_connect(url) as ws:
        ws.receive_json()
        assert ws.receive().get("code") == 4401


def test_missing_credentials_rejected(env):
    with env["client"].websocket_connect(f"/ws/chat/{env['chat_id']}") as ws:
        ws.receive_json()
        assert ws.receive().get("code") == 4401


def test_legacy_token_still_works(env):
    """Keçid dövrü: brauzerdə köhnə JS qalıbsa, çat sınmasın."""
    with env["client"].websocket_connect(f"/ws/chat/{env['chat_id']}?token={env['token']}") as ws:
        assert ws.receive_json()["type"] == "history"
