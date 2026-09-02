import pytest

from server.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list[dict] = []

    async def send_json(self, message: dict) -> None:
        if self.fail:
            raise RuntimeError("bağlantı qopub")
        self.sent.append(message)


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.mark.asyncio
async def test_broadcast_reaches_all_connected_clients(manager):
    ws_a = FakeWebSocket()
    ws_b = FakeWebSocket()
    manager.connect(chat_id=1, user_id=10, websocket=ws_a)
    manager.connect(chat_id=1, user_id=20, websocket=ws_b)

    await manager.broadcast(1, {"type": "message", "content": "salam"})

    assert ws_a.sent == [{"type": "message", "content": "salam"}]
    assert ws_b.sent == [{"type": "message", "content": "salam"}]


@pytest.mark.asyncio
async def test_broadcast_does_not_leak_to_other_chats(manager):
    ws_chat1 = FakeWebSocket()
    ws_chat2 = FakeWebSocket()
    manager.connect(chat_id=1, user_id=10, websocket=ws_chat1)
    manager.connect(chat_id=2, user_id=10, websocket=ws_chat2)

    await manager.broadcast(1, {"type": "message", "content": "yalnız çat 1"})

    assert ws_chat1.sent == [{"type": "message", "content": "yalnız çat 1"}]
    assert ws_chat2.sent == []


@pytest.mark.asyncio
async def test_disconnected_client_does_not_receive_broadcasts(manager):
    ws = FakeWebSocket()
    manager.connect(chat_id=1, user_id=10, websocket=ws)
    manager.disconnect(chat_id=1, user_id=10, websocket=ws)

    await manager.broadcast(1, {"type": "message", "content": "salam"})

    assert ws.sent == []


@pytest.mark.asyncio
async def test_stale_connection_does_not_break_broadcast_to_others(manager):
    stale = FakeWebSocket(fail=True)
    healthy = FakeWebSocket()
    manager.connect(chat_id=1, user_id=10, websocket=stale)
    manager.connect(chat_id=1, user_id=20, websocket=healthy)

    await manager.broadcast(1, {"type": "message", "content": "salam"})

    assert healthy.sent == [{"type": "message", "content": "salam"}]


@pytest.mark.asyncio
async def test_stale_connection_is_removed_after_failed_send(manager):
    stale = FakeWebSocket(fail=True)
    manager.connect(chat_id=1, user_id=10, websocket=stale)

    await manager.broadcast(1, {"type": "message", "content": "1-ci cəhd"})
    # ikinci broadcast-da artıq siyahıda olmamalıdır — sakit təkrar sınaq yoxdur
    healthy = FakeWebSocket()
    manager.connect(chat_id=1, user_id=20, websocket=healthy)
    await manager.broadcast(1, {"type": "message", "content": "2-ci cəhd"})

    assert healthy.sent == [{"type": "message", "content": "2-ci cəhd"}]


def test_same_user_can_have_multiple_connections(manager):
    ws_tab1 = FakeWebSocket()
    ws_tab2 = FakeWebSocket()
    manager.connect(chat_id=1, user_id=10, websocket=ws_tab1)
    manager.connect(chat_id=1, user_id=10, websocket=ws_tab2)

    assert manager.connection_count(chat_id=1) == 2


def test_connection_count_zero_when_empty(manager):
    assert manager.connection_count(chat_id=999) == 0
