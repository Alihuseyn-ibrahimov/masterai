import pytest

from server.friendship_store import AlreadyFriends, DuplicateFriendship, FriendshipStore


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


def test_duplicate_pending_friendship_request_rejected(store):
    store.create(requester_id=1, addressee_id=2)
    with pytest.raises(DuplicateFriendship):
        store.create(requester_id=1, addressee_id=2)


def test_reverse_direction_pending_request_also_rejected(store):
    store.create(requester_id=1, addressee_id=2)
    with pytest.raises(DuplicateFriendship):
        store.create(requester_id=2, addressee_id=1)


def test_request_when_already_accepted_raises_already_friends(store):
    created = store.create(requester_id=1, addressee_id=2)
    store.update_status(created["id"], "accepted")

    with pytest.raises(AlreadyFriends):
        store.create(requester_id=1, addressee_id=2)
    with pytest.raises(AlreadyFriends):
        store.create(requester_id=2, addressee_id=1)


@pytest.mark.parametrize("terminal_status", ["declined", "cancelled", "unfriended"])
def test_request_after_terminal_status_replaces_row_with_new_roles(store, terminal_status):
    created = store.create(requester_id=1, addressee_id=2)
    store.update_status(created["id"], terminal_status)

    # Yeni sorğu — bu dəfə əks istiqamətdə (2 -> 1)
    reopened = store.create(requester_id=2, addressee_id=1)

    assert reopened["id"] == created["id"]  # eyni sətir əvəz olunub
    assert reopened["requester_id"] == 2
    assert reopened["addressee_id"] == 1
    assert reopened["status"] == "pending"
    assert reopened["responded_at"] is None


def test_find_between_finds_either_direction(store):
    created = store.create(requester_id=1, addressee_id=2)

    assert store.find_between(1, 2) == created
    assert store.find_between(2, 1) == created


def test_find_between_returns_none_when_no_relationship(store):
    assert store.find_between(1, 2) is None


def test_update_status_sets_responded_at(store):
    created = store.create(requester_id=1, addressee_id=2)
    assert created["responded_at"] is None

    store.update_status(created["id"], "accepted")
    updated = store.get(created["id"])

    assert updated["status"] == "accepted"
    assert updated["responded_at"] is not None


def test_are_friends_true_only_when_accepted(store):
    created = store.create(requester_id=1, addressee_id=2)
    assert store.are_friends(1, 2) is False
    assert store.are_friends(2, 1) is False

    store.update_status(created["id"], "accepted")
    assert store.are_friends(1, 2) is True
    assert store.are_friends(2, 1) is True


def test_are_friends_false_when_no_relationship(store):
    assert store.are_friends(1, 2) is False
