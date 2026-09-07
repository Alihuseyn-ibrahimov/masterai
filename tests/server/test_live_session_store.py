import pytest

import server.live_session_store as live_session_store_module
from server.live_session_store import LiveSessionStore


@pytest.fixture
def store(tmp_path):
    return LiveSessionStore(path=str(tmp_path / "live_sessions.db"))


def test_create_session_defaults(store):
    session = store.create_session(question_set_id=7)

    assert session["id"] is not None
    assert session["question_set_id"] == 7
    assert session["status"] == "waiting"
    assert session["current_question_index"] == 0
    assert session["report_json"] is None
    assert len(session["pin"]) == 6
    assert session["pin"].isdigit()


def test_create_session_retries_on_pin_collision(store, monkeypatch):
    """`_generate_unique_pin` bitməmiş sessiyalar arasında unikal PIN
    təmin etməlidir — ilk cəhd toqquşsa belə."""
    first = store.create_session(question_set_id=1)

    calls = iter([first["pin"], first["pin"], "654321"])
    monkeypatch.setattr(live_session_store_module.random, "randint", lambda a, b: int(next(calls)))

    second = store.create_session(question_set_id=2)
    assert second["pin"] == "654321"
    assert second["pin"] != first["pin"]


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


def test_get_by_pin_finds_waiting_session(store):
    session = store.create_session(question_set_id=1)
    assert store.get_by_pin(session["pin"]) == session


def test_get_by_pin_returns_none_for_finished_session(store):
    session = store.create_session(question_set_id=1)
    store.set_status(session["id"], "finished")
    assert store.get_by_pin(session["pin"]) is None


def test_get_by_pin_returns_none_for_unknown_pin(store):
    assert store.get_by_pin("000000") is None


def test_set_status(store):
    session = store.create_session(question_set_id=1)
    store.set_status(session["id"], "active")
    assert store.get(session["id"])["status"] == "active"


def test_advance_increments_index(store):
    session = store.create_session(question_set_id=1)
    updated = store.advance(session["id"])
    assert updated["current_question_index"] == 1
    updated = store.advance(session["id"])
    assert updated["current_question_index"] == 2


def test_advance_raises_for_unknown_session(store):
    with pytest.raises(ValueError):
        store.advance(999)


def test_save_report(store):
    session = store.create_session(question_set_id=1)
    store.save_report(session["id"], '{"total": 3}')
    assert store.get(session["id"])["report_json"] == '{"total": 3}'


def test_add_and_list_participants(store):
    session = store.create_session(question_set_id=1)
    p1 = store.add_participant(session["id"], "Əli")
    p2 = store.add_participant(session["id"], "Vəli")

    participants = store.list_participants(session["id"])
    assert [p["display_name"] for p in participants] == ["Əli", "Vəli"]
    assert store.get_participant(p1["id"])["display_name"] == "Əli"
    assert store.get_participant(p2["id"])["display_name"] == "Vəli"
    assert store.count_participants(session["id"]) == 2


def test_participants_do_not_leak_across_sessions(store):
    s1 = store.create_session(question_set_id=1)
    s2 = store.create_session(question_set_id=2)
    store.add_participant(s1["id"], "s1 iştirakçı")
    store.add_participant(s2["id"], "s2 iştirakçı")

    assert [p["display_name"] for p in store.list_participants(s1["id"])] == ["s1 iştirakçı"]
    assert [p["display_name"] for p in store.list_participants(s2["id"])] == ["s2 iştirakçı"]


def test_record_answer_and_has_answered(store):
    session = store.create_session(question_set_id=1)
    participant = store.add_participant(session["id"], "Əli")

    assert store.has_answered(session["id"], participant["id"], 0) is False
    answer = store.record_answer(session["id"], participant["id"], 0, chosen_index=2, is_correct=True)
    assert answer["is_correct"] is True
    assert answer["chosen_index"] == 2
    assert store.has_answered(session["id"], participant["id"], 0) is True
    assert store.has_answered(session["id"], participant["id"], 1) is False


def test_list_answers_for_question(store):
    session = store.create_session(question_set_id=1)
    p1 = store.add_participant(session["id"], "Əli")
    p2 = store.add_participant(session["id"], "Vəli")
    store.record_answer(session["id"], p1["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], p2["id"], 0, chosen_index=1, is_correct=False)
    store.record_answer(session["id"], p1["id"], 1, chosen_index=0, is_correct=True)

    q0_answers = store.list_answers_for_question(session["id"], 0)
    assert len(q0_answers) == 2
    q1_answers = store.list_answers_for_question(session["id"], 1)
    assert len(q1_answers) == 1


def test_list_answers_for_session(store):
    session = store.create_session(question_set_id=1)
    participant = store.add_participant(session["id"], "Əli")
    store.record_answer(session["id"], participant["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], participant["id"], 1, chosen_index=1, is_correct=False)

    all_answers = store.list_answers_for_session(session["id"])
    assert len(all_answers) == 2


def test_compute_scores_includes_zero_score_participants(store):
    session = store.create_session(question_set_id=1)
    p1 = store.add_participant(session["id"], "Əli")
    p2 = store.add_participant(session["id"], "Vəli")
    store.record_answer(session["id"], p1["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], p1["id"], 1, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], p2["id"], 0, chosen_index=3, is_correct=False)

    scores = store.compute_scores(session["id"])
    assert scores == {p1["id"]: 2, p2["id"]: 0}


def test_compute_scores_does_not_leak_across_sessions(store):
    s1 = store.create_session(question_set_id=1)
    s2 = store.create_session(question_set_id=2)
    p1 = store.add_participant(s1["id"], "s1 iştirakçı")
    p2 = store.add_participant(s2["id"], "s2 iştirakçı")
    store.record_answer(s1["id"], p1["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(s2["id"], p2["id"], 0, chosen_index=0, is_correct=True)

    assert store.compute_scores(s1["id"]) == {p1["id"]: 1}
    assert store.compute_scores(s2["id"]) == {p2["id"]: 1}
