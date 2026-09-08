import pytest

from server.badge_store import BadgeStore


@pytest.fixture
def store(tmp_path):
    return BadgeStore(path=str(tmp_path / "badges.db"))


def test_get_earned_empty_for_new_student(store):
    assert store.get_earned(1) == {}


def test_mark_earned_records_badge(store):
    store.mark_earned(1, "ilk_addim")
    earned = store.get_earned(1)
    assert "ilk_addim" in earned
    assert earned["ilk_addim"]


def test_mark_earned_is_idempotent(store):
    store.mark_earned(1, "ilk_addim")
    first = store.get_earned(1)["ilk_addim"]
    store.mark_earned(1, "ilk_addim")
    second = store.get_earned(1)["ilk_addim"]
    assert first == second


def test_mark_earned_does_not_leak_across_students(store):
    store.mark_earned(1, "ilk_addim")
    assert store.get_earned(2) == {}


def test_multiple_badges_per_student(store):
    store.mark_earned(1, "ilk_addim")
    store.mark_earned(1, "yuz_faiz")
    earned = store.get_earned(1)
    assert set(earned.keys()) == {"ilk_addim", "yuz_faiz"}
