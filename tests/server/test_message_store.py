import pytest

from server.message_store import MessageStore


@pytest.fixture
def store(tmp_path):
    return MessageStore(path=str(tmp_path / "messages.db"))


def test_create_text_message(store):
    message = store.create(chat_id=1, sender_id=2, kind="text", content="Salam!")

    assert message["id"] is not None
    assert message["chat_id"] == 1
    assert message["sender_id"] == 2
    assert message["kind"] == "text"
    assert message["content"] == "Salam!"
    assert message["created_at"]


def test_create_system_message_with_no_sender(store):
    message = store.create(chat_id=1, sender_id=None, kind="system", content="Qrup yaradıldı")
    assert message["sender_id"] is None


def test_list_by_chat_returns_chronological_order(store):
    store.create(chat_id=1, sender_id=2, kind="text", content="Birinci")
    store.create(chat_id=1, sender_id=3, kind="text", content="İkinci")
    store.create(chat_id=1, sender_id=2, kind="text", content="Üçüncü")

    messages = store.list_by_chat(1)

    assert [m["content"] for m in messages] == ["Birinci", "İkinci", "Üçüncü"]


def test_list_by_chat_excludes_other_chats(store):
    store.create(chat_id=1, sender_id=2, kind="text", content="Çat 1")
    store.create(chat_id=2, sender_id=2, kind="text", content="Çat 2")

    messages = store.list_by_chat(1)

    assert len(messages) == 1
    assert messages[0]["content"] == "Çat 1"


def test_list_by_chat_respects_limit_and_returns_most_recent(store):
    for i in range(5):
        store.create(chat_id=1, sender_id=2, kind="text", content=f"Mesaj {i}")

    messages = store.list_by_chat(1, limit=3)

    assert len(messages) == 3
    assert [m["content"] for m in messages] == ["Mesaj 2", "Mesaj 3", "Mesaj 4"]


def test_list_by_chat_empty_when_no_messages(store):
    assert store.list_by_chat(999) == []
