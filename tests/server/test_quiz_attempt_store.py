import pytest

from server.quiz_attempt_store import QuizAttemptStore


@pytest.fixture
def store(tmp_path):
    return QuizAttemptStore(path=str(tmp_path / "attempts.db"))


def test_create_correct_attempt(store):
    attempt = store.create(question_id=1, user_id=2, chosen_index=0, is_correct=True)

    assert attempt["id"] is not None
    assert attempt["question_id"] == 1
    assert attempt["user_id"] == 2
    assert attempt["chosen_index"] == 0
    assert attempt["is_correct"] is True
    assert attempt["answered_at"]


def test_create_incorrect_attempt(store):
    attempt = store.create(question_id=1, user_id=2, chosen_index=3, is_correct=False)
    assert attempt["is_correct"] is False


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


def test_get_returns_created_attempt(store):
    created = store.create(question_id=1, user_id=2, chosen_index=0, is_correct=True)
    assert store.get(created["id"]) == created


def test_list_by_user(store):
    store.create(question_id=1, user_id=2, chosen_index=0, is_correct=True)
    store.create(question_id=2, user_id=2, chosen_index=1, is_correct=False)
    store.create(question_id=1, user_id=3, chosen_index=0, is_correct=True)

    results = store.list_by_user(2)
    assert len(results) == 2
    assert {a["question_id"] for a in results} == {1, 2}


def test_list_by_question(store):
    store.create(question_id=1, user_id=2, chosen_index=0, is_correct=True)
    store.create(question_id=1, user_id=3, chosen_index=1, is_correct=False)
    store.create(question_id=2, user_id=2, chosen_index=0, is_correct=True)

    results = store.list_by_question(1)
    assert len(results) == 2
    assert {a["user_id"] for a in results} == {2, 3}


def test_list_by_question_empty_when_none(store):
    assert store.list_by_question(999) == []
