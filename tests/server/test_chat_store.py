import pytest

from server.chat_store import ChatStore


@pytest.fixture
def store(tmp_path):
    return ChatStore(path=str(tmp_path / "chats.db"))


def test_create_direct_chat(store):
    chat = store.create(kind="direct", created_by=1)

    assert chat["id"] is not None
    assert chat["kind"] == "direct"
    assert chat["name"] is None
    assert chat["created_by"] == 1
    assert chat["created_at"]


def test_create_group_chat_with_name(store):
    chat = store.create(kind="group", created_by=1, name="Dövlət qulluğu qrupu")
    assert chat["name"] == "Dövlət qulluğu qrupu"


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


def test_get_returns_created_chat(store):
    created = store.create(kind="direct", created_by=1)
    assert store.get(created["id"]) == created


def test_add_member_and_list_by_user(store):
    chat = store.create(kind="group", created_by=1, name="Qrup")
    store.add_member(chat["id"], user_id=1)
    store.add_member(chat["id"], user_id=2)

    chats_of_user_1 = store.list_by_user(1)
    chats_of_user_2 = store.list_by_user(2)
    chats_of_user_3 = store.list_by_user(3)

    assert [c["id"] for c in chats_of_user_1] == [chat["id"]]
    assert [c["id"] for c in chats_of_user_2] == [chat["id"]]
    assert chats_of_user_3 == []


def test_list_member_ids(store):
    chat = store.create(kind="group", created_by=1, name="Qrup")
    store.add_member(chat["id"], user_id=1)
    store.add_member(chat["id"], user_id=2)

    assert sorted(store.list_member_ids(chat["id"])) == [1, 2]


def test_list_member_ids_empty_for_unknown_chat(store):
    assert store.list_member_ids(999) == []


def test_adding_same_member_twice_is_idempotent(store):
    chat = store.create(kind="group", created_by=1, name="Qrup")
    store.add_member(chat["id"], user_id=1)
    store.add_member(chat["id"], user_id=1)

    assert len(store.list_by_user(1)) == 1
