import pytest
from fastapi.testclient import TestClient

from server.app import (
    app,
    get_chat_store,
    get_connection_manager,
    get_message_store,
    get_token_secret,
    get_user_store,
)
from server.auth import create_token
from server.chat_store import ChatStore
from server.connection_manager import ConnectionManager
from server.message_store import MessageStore
from server.user_store import UserStore

_SECRET = "test-secret-key-32-chars-minimum!!"


@pytest.fixture
def env():
    users = UserStore(":memory:")
    chats = ChatStore(":memory:")
    messages = MessageStore(":memory:")
    manager = ConnectionManager()

    app.dependency_overrides[get_user_store] = lambda: users
    app.dependency_overrides[get_chat_store] = lambda: chats
    app.dependency_overrides[get_message_store] = lambda: messages
    app.dependency_overrides[get_connection_manager] = lambda: manager
    app.dependency_overrides[get_token_secret] = lambda: _SECRET

    client = TestClient(app)

    ali = users.create("ali@example.com", "hash", "Əli")
    vali = users.create("vali@example.com", "hash", "Vəli")
    kanar = users.create("kenar@example.com", "hash", "Kənar")
    chat = chats.create(kind="group", created_by=ali["id"], name="Qrup")
    chats.add_member(chat["id"], ali["id"])
    chats.add_member(chat["id"], vali["id"])

    yield {
        "client": client,
        "chat_id": chat["id"],
        "ali": ali,
        "vali": vali,
        "kenar": kanar,
        "messages": messages,
    }
    app.dependency_overrides.clear()


def _token(user_id: int) -> str:
    return create_token(user_id, secret=_SECRET)


def _ws_url(chat_id: int, token: str) -> str:
    return f"/ws/chat/{chat_id}?token={token}"


def _rejection(client, url: str) -> tuple[dict, int]:
    """Rədd edilən qoşulmadan səbəb mesajını və bağlanma kodunu oxuyur.

    Əvvəl bu testlər sadəcə `pytest.raises(Exception)` yoxlayırdı, yəni
    SINIQ davranışı təsdiqləyirdi: server `accept()`-dən əvvəl bağlayırdı
    və brauzerə kod ÇATMIRDI (real ölçmə: brauzer 1006 görürdü, 4404
    yox). Bax `tests/server/test_websocket_rejection_reason.py`.
    """
    with client.websocket_connect(url) as ws:
        payload = ws.receive_json()
        closing = ws.receive()
    return payload, closing.get("code")


def test_rejects_invalid_token(env):
    payload, code = _rejection(env["client"], _ws_url(env["chat_id"], "bu-token-deyil"))
    assert code == 4401
    assert payload["type"] == "error" and payload["detail"]


def test_rejects_non_member(env):
    payload, code = _rejection(env["client"], _ws_url(env["chat_id"], _token(env["kenar"]["id"])))
    assert code == 4403
    assert payload["type"] == "error" and payload["detail"]


def test_rejects_unknown_chat(env):
    payload, code = _rejection(env["client"], _ws_url(999, _token(env["ali"]["id"])))
    assert code == 4404
    assert payload["type"] == "error" and payload["detail"]


def test_sends_history_on_connect(env):
    env["messages"].create(env["chat_id"], env["ali"]["id"], "text", "Salam")
    env["messages"].create(env["chat_id"], env["vali"]["id"], "text", "Necəsiniz")

    with env["client"].websocket_connect(_ws_url(env["chat_id"], _token(env["ali"]["id"]))) as ws:
        frame = ws.receive_json()
        assert frame["type"] == "history"
        assert [m["content"] for m in frame["messages"]] == ["Salam", "Necəsiniz"]


def test_text_message_is_broadcast_to_all_connected_members(env):
    with env["client"].websocket_connect(_ws_url(env["chat_id"], _token(env["ali"]["id"]))) as ws_ali:
        ws_ali.receive_json()  # history
        with env["client"].websocket_connect(_ws_url(env["chat_id"], _token(env["vali"]["id"]))) as ws_vali:
            ws_vali.receive_json()  # history

            ws_ali.send_json({"type": "text", "content": "Salam, hazırsınız?"})

            msg_ali = ws_ali.receive_json()
            msg_vali = ws_vali.receive_json()

    assert msg_ali["type"] == "message"
    assert msg_ali["content"] == "Salam, hazırsınız?"
    assert msg_ali["sender_id"] == env["ali"]["id"]
    assert msg_vali == msg_ali  # göndərən daxil, hər ikisi eyni frame-i alır


def test_message_is_persisted(env):
    with env["client"].websocket_connect(_ws_url(env["chat_id"], _token(env["ali"]["id"]))) as ws:
        ws.receive_json()  # history
        ws.send_json({"type": "text", "content": "Yadda qalsın"})
        ws.receive_json()  # broadcast

    stored = env["messages"].list_by_chat(env["chat_id"])
    assert [m["content"] for m in stored] == ["Yadda qalsın"]


def test_malformed_message_returns_error_without_disconnecting(env):
    with env["client"].websocket_connect(_ws_url(env["chat_id"], _token(env["ali"]["id"]))) as ws:
        ws.receive_json()  # history

        ws.send_json({"type": "unknown_type"})
        error_frame = ws.receive_json()
        assert error_frame["type"] == "error"

        # bağlantı hələ açıqdır — sonra normal mesaj göndərmək mümkündür
        ws.send_json({"type": "text", "content": "Hələ işləyir"})
        ok_frame = ws.receive_json()
        assert ok_frame["type"] == "message"
        assert ok_frame["content"] == "Hələ işləyir"
