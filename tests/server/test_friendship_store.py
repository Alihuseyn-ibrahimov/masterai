import pytest

from server.friendship_store import FriendshipStore


@pytest.fixture
def store(tmp_path):
    return FriendshipStore(path=str(tmp_path / "friendships.db"))


def test_create_defaults_to_pending(store):
    friendship = store.create(requester_id=1, addressee_id=2)

    assert friendship["id"] is not None
    assert friendship["requester_id"] == 1
    assert friendship["addressee_id"] == 2
    assert friendship["status"] == "pending"
    assert friendship["responded_at"] is None
    assert friendship["created_at"]


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


def test_get_returns_created_friendship(store):
    created = store.create(requester_id=1, addressee_id=2)
    assert store.get(created["id"]) == created


def test_list_by_user_includes_both_requester_and_addressee_role(store):
    store.create(requester_id=1, addressee_id=2)
    store.create(requester_id=3, addressee_id=1)
    store.create(requester_id=2, addressee_id=3)  # 1-ə aid deyil

    results = store.list_by_user(1)

    assert len(results) == 2
    user_ids_involved = {(f["requester_id"], f["addressee_id"]) for f in results}
    assert (1, 2) in user_ids_involved
    assert (3, 1) in user_ids_involved


def test_duplicate_friendship_request_rejected(store):
    from server.friendship_store import DuplicateFriendship

    store.create(requester_id=1, addressee_id=2)
    with pytest.raises(DuplicateFriendship):
        store.create(requester_id=1, addressee_id=2)
