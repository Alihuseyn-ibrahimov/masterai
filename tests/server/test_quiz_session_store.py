import pytest

from server.quiz_session_store import QuizAlreadyActive, QuizSessionStore


@pytest.fixture
def store(tmp_path):
    return QuizSessionStore(path=str(tmp_path / "quiz_sessions.db"))


def test_create_starts_at_first_question(store):
    session = store.create(chat_id=1, material_id=10, question_ids=[100, 101, 102])

    assert session["chat_id"] == 1
    assert session["material_id"] == 10
    assert session["question_ids"] == [100, 101, 102]
    assert session["current_index"] == 0
    assert session["status"] == "active"
    assert session["current_question_started_at"]


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


def test_create_raises_when_active_session_exists(store):
    store.create(chat_id=1, material_id=10, question_ids=[100])
    with pytest.raises(QuizAlreadyActive):
        store.create(chat_id=1, material_id=20, question_ids=[200])


def test_advance_moves_to_next_question(store):
    store.create(chat_id=1, material_id=10, question_ids=[100, 101, 102])
    session = store.advance(1)

    assert session["current_index"] == 1
    assert session["status"] == "active"


def test_advance_past_last_question_marks_finished(store):
    store.create(chat_id=1, material_id=10, question_ids=[100, 101])
    store.advance(1)
    session = store.advance(1)

    assert session["status"] == "finished"


def test_create_replaces_finished_session_with_new_round(store):
    store.create(chat_id=1, material_id=10, question_ids=[100])
    store.advance(1)  # finished

    new_session = store.create(chat_id=1, material_id=20, question_ids=[200, 201])

    assert new_session["material_id"] == 20
    assert new_session["question_ids"] == [200, 201]
    assert new_session["current_index"] == 0
    assert new_session["status"] == "active"


def test_advance_raises_when_no_session(store):
    with pytest.raises(ValueError):
        store.advance(999)


def test_count_all(store):
    assert store.count_all() == 0
    store.create(chat_id=1, material_id=10, question_ids=[100])
    store.create(chat_id=2, material_id=20, question_ids=[200])
    assert store.count_all() == 2
