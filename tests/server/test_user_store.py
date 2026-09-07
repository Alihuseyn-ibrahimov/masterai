import pytest

from server.user_store import DuplicateEmail, UserStore


@pytest.fixture
def store(tmp_path):
    return UserStore(path=str(tmp_path / "users.db"))


class TestCreate:
    def test_returns_full_record(self, store):
        user = store.create("ali@example.az", "hashlənmiş-şifrə", "Əli")

        assert user["id"] is not None
        assert user["email"] == "ali@example.az"
        assert user["password_hash"] == "hashlənmiş-şifrə"
        assert user["display_name"] == "Əli"
        assert user["phone"] is None
        assert user["created_at"]
        assert user["is_teacher"] == 0
        assert user["is_admin"] == 0

    def test_normalizes_email_case(self, store):
        user = store.create("Ali@Example.AZ", "hash", "Əli")
        assert user["email"] == "ali@example.az"

    def test_duplicate_email_raises(self, store):
        store.create("ali@example.az", "hash1", "Əli")
        with pytest.raises(DuplicateEmail):
            store.create("Ali@Example.az", "hash2", "Əli İkinci")

    def test_stores_optional_phone(self, store):
        user = store.create("ali@example.az", "hash", "Əli", phone="+994501112233")
        assert user["phone"] == "+994501112233"


class TestGetByEmail:
    def test_returns_none_when_missing(self, store):
        assert store.get_by_email("yoxdur@example.az") is None

    def test_lookup_is_case_insensitive(self, store):
        store.create("ali@example.az", "hash", "Əli")
        assert store.get_by_email("ALI@EXAMPLE.AZ") is not None


class TestGetById:
    def test_returns_none_when_missing(self, store):
        assert store.get_by_id(999) is None

    def test_returns_created_user(self, store):
        created = store.create("ali@example.az", "hash", "Əli")
        fetched = store.get_by_id(created["id"])
        assert fetched == created


def test_ping_returns_true_when_db_alive(store):
    assert store.ping() is True


def test_count_all(store):
    assert store.count_all() == 0
    store.create("ali@example.az", "hash", "Əli")
    store.create("vali@example.az", "hash", "Vəli")
    assert store.count_all() == 2


def test_set_teacher(store):
    user = store.create("ali@example.az", "hash", "Əli")
    store.set_teacher(user["id"], True)
    assert store.get_by_id(user["id"])["is_teacher"] == 1
    store.set_teacher(user["id"], False)
    assert store.get_by_id(user["id"])["is_teacher"] == 0


def test_set_admin(store):
    user = store.create("ali@example.az", "hash", "Əli")
    store.set_admin(user["id"], True)
    assert store.get_by_id(user["id"])["is_admin"] == 1
    store.set_admin(user["id"], False)
    assert store.get_by_id(user["id"])["is_admin"] == 0


def test_isolated_db_per_instance(tmp_path):
    store_a = UserStore(path=str(tmp_path / "a.db"))
    store_b = UserStore(path=str(tmp_path / "b.db"))

    store_a.create("ali@example.az", "hash", "Əli")

    assert store_a.get_by_email("ali@example.az") is not None
    assert store_b.get_by_email("ali@example.az") is None
