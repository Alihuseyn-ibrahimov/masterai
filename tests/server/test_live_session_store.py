import pytest

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


# `test_create_session_retries_on_pin_collision` SİLİNDİ (Faza 4):
# `_generate_unique_pin` artıq yoxdur. PIN axını tamamilə getdi —
# sessiya sinfə bağlıdır, tələbə çatdan qoşulur.


def test_get_returns_none_when_missing(store):
    assert store.get(999) is None


# `get_by_pin` testləri SİLİNDİ (Faza 4) — metod yoxdur. Sessiya
# ID ilə tapılır (`test_live_session_chat_link.py`), üzvlük isə
# çat üzərindən yoxlanılır (`test_live_session_in_chat.py`).


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
    p1 = store.add_participant(session["id"], "Əli", user_id=1)
    p2 = store.add_participant(session["id"], "Vəli", user_id=2)

    participants = store.list_participants(session["id"])
    assert [p["display_name"] for p in participants] == ["Əli", "Vəli"]
    assert store.get_participant(p1["id"])["display_name"] == "Əli"
    assert store.get_participant(p2["id"])["display_name"] == "Vəli"
    assert store.count_participants(session["id"]) == 2


class TestParticipantIsUniquePerUser:
    """REAL PRODUKSİYA BUG-I (2026-09-12, sessiya #31).

    Tələbə səhifəni hər yeniləyəndə (və ya telefon bağlantını itirib
    qayıdanda) yeni WebSocket açılır — `add_participant` isə hər dəfə
    YENİ sətir yazırdı. Canlı bazada bir Amil ÜÇ sətirlə göründü
    (07:02:48, 07:03:02, 07:04:15) və onun balı üç sətrə bölündü,
    yəni sessiya hesabatı yanlış çıxdı.

    Ona görə `add_participant` indi «tap-və-ya-yarat»dır: (sessiya,
    istifadəçi) cütü üçün HƏMİŞƏ bir sətir.
    """

    def test_second_join_returns_the_same_row(self, store):
        session = store.create_session(question_set_id=1)
        first = store.add_participant(session["id"], "Amil", user_id=5)
        second = store.add_participant(session["id"], "Amil", user_id=5)

        assert second["id"] == first["id"]
        assert store.count_participants(session["id"]) == 1
        assert len(store.list_participants(session["id"])) == 1

    def test_joined_at_is_not_reset_on_rejoin(self, store):
        """Qoşulma vaxtı İLK qoşulmanı göstərməlidir — sıralama və
        hesabat ona söykənir."""
        session = store.create_session(question_set_id=1)
        first = store.add_participant(session["id"], "Amil", user_id=5)
        again = store.add_participant(session["id"], "Amil", user_id=5)

        assert again["joined_at"] == first["joined_at"]

    def test_display_name_is_refreshed_on_rejoin(self, store):
        session = store.create_session(question_set_id=1)
        first = store.add_participant(session["id"], "Köhnə ad", user_id=5)
        again = store.add_participant(session["id"], "Yeni ad", user_id=5)

        assert again["id"] == first["id"]
        assert again["display_name"] == "Yeni ad"
        assert store.get_participant(first["id"])["display_name"] == "Yeni ad"

    def test_different_users_stay_separate(self, store):
        session = store.create_session(question_set_id=1)
        a = store.add_participant(session["id"], "Amil", user_id=5)
        b = store.add_participant(session["id"], "Nigar", user_id=6)

        assert a["id"] != b["id"]
        assert store.count_participants(session["id"]) == 2

    def test_same_user_in_another_session_is_a_new_row(self, store):
        first = store.create_session(question_set_id=1)
        second = store.create_session(question_set_id=1)
        a = store.add_participant(first["id"], "Amil", user_id=5)
        b = store.add_participant(second["id"], "Amil", user_id=5)

        assert a["id"] != b["id"]

    def test_answers_survive_a_rejoin(self, store):
        """Bug-ın əsl zərəri: cavablar köhnə sətirdə qalıb yenisinə
        yazılmırdı, yəni «Növbəti sual» indeksi sıfırlanırdı."""
        session = store.create_session(question_set_id=1)
        participant = store.add_participant(session["id"], "Amil", user_id=5)
        store.record_answer(session["id"], participant["id"], 0, 2, True)

        again = store.add_participant(session["id"], "Amil", user_id=5)

        assert store.count_answers_by_participant(session["id"], again["id"]) == 1
        assert store.compute_scores(session["id"]) == {participant["id"]: 1}


def test_add_participant_requires_a_user(store):
    """Anonim iştirakçı yolu SİLİNDİ (Faza 4).

    Əvvəl `user_id` könüllü idi (PIN qoşulması hesabsız idi) və belə
    iştirakçıların nəticəsi HEÇ KİMİN tarixçəsinə düşmürdü. İndi hər
    nəticə bir hesaba bağlıdır.
    """
    session = store.create_session(question_set_id=1)
    logged_in = store.add_participant(session["id"], "Aygün", user_id=42)
    assert logged_in["user_id"] == 42

    with pytest.raises(TypeError):
        store.add_participant(session["id"], "Qonaq")


def test_list_participations_for_user_only_finished_sessions(store):
    finished = store.create_session(question_set_id=1)
    participant = store.add_participant(finished["id"], "Aygün", user_id=42)
    store.save_report(finished["id"], '{"rankings": [{"participant_id": %d, "score": 2}]}' % participant["id"])
    store.set_status(finished["id"], "finished")

    still_active = store.create_session(question_set_id=2)
    store.add_participant(still_active["id"], "Aygün", user_id=42)

    rows = store.list_participations_for_user(42)
    assert len(rows) == 1
    assert rows[0]["session_id"] == finished["id"]
    assert rows[0]["participant_id"] == participant["id"]


def test_list_participations_for_user_ignores_anonymous_and_other_users(store):
    session = store.create_session(question_set_id=1)
    store.add_participant(session["id"], "Qonaq", user_id=1)
    store.add_participant(session["id"], "Başqası", user_id=7)
    store.set_status(session["id"], "finished")
    assert store.list_participations_for_user(42) == []


def test_participants_do_not_leak_across_sessions(store):
    s1 = store.create_session(question_set_id=1)
    s2 = store.create_session(question_set_id=2)
    store.add_participant(s1["id"], "s1 iştirakçı", user_id=1)
    store.add_participant(s2["id"], "s2 iştirakçı", user_id=1)

    assert [p["display_name"] for p in store.list_participants(s1["id"])] == ["s1 iştirakçı"]
    assert [p["display_name"] for p in store.list_participants(s2["id"])] == ["s2 iştirakçı"]


def test_record_answer_and_has_answered(store):
    session = store.create_session(question_set_id=1)
    participant = store.add_participant(session["id"], "Əli", user_id=1)

    assert store.has_answered(session["id"], participant["id"], 0) is False
    answer = store.record_answer(session["id"], participant["id"], 0, chosen_index=2, is_correct=True)
    assert answer["is_correct"] is True
    assert answer["chosen_index"] == 2
    assert store.has_answered(session["id"], participant["id"], 0) is True
    assert store.has_answered(session["id"], participant["id"], 1) is False


def test_list_answers_for_question(store):
    session = store.create_session(question_set_id=1)
    p1 = store.add_participant(session["id"], "Əli", user_id=1)
    p2 = store.add_participant(session["id"], "Vəli", user_id=2)
    store.record_answer(session["id"], p1["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], p2["id"], 0, chosen_index=1, is_correct=False)
    store.record_answer(session["id"], p1["id"], 1, chosen_index=0, is_correct=True)

    q0_answers = store.list_answers_for_question(session["id"], 0)
    assert len(q0_answers) == 2
    q1_answers = store.list_answers_for_question(session["id"], 1)
    assert len(q1_answers) == 1


def test_list_answers_for_session(store):
    session = store.create_session(question_set_id=1)
    participant = store.add_participant(session["id"], "Əli", user_id=1)
    store.record_answer(session["id"], participant["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], participant["id"], 1, chosen_index=1, is_correct=False)

    all_answers = store.list_answers_for_session(session["id"])
    assert len(all_answers) == 2


def test_compute_scores_includes_zero_score_participants(store):
    session = store.create_session(question_set_id=1)
    p1 = store.add_participant(session["id"], "Əli", user_id=1)
    p2 = store.add_participant(session["id"], "Vəli", user_id=2)
    store.record_answer(session["id"], p1["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], p1["id"], 1, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], p2["id"], 0, chosen_index=3, is_correct=False)

    scores = store.compute_scores(session["id"])
    assert scores == {p1["id"]: 2, p2["id"]: 0}


def test_start_sets_active_status_duration_and_started_at(store):
    session = store.create_session(question_set_id=1)
    updated = store.start(session["id"], 180)

    assert updated["status"] == "active"
    assert updated["duration_seconds"] == 180
    assert updated["started_at"] is not None
    assert store.get(session["id"]) == updated


def test_count_answers_by_participant(store):
    session = store.create_session(question_set_id=1)
    p1 = store.add_participant(session["id"], "Əli", user_id=1)
    p2 = store.add_participant(session["id"], "Vəli", user_id=2)
    store.record_answer(session["id"], p1["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(session["id"], p1["id"], 1, chosen_index=1, is_correct=False)
    store.record_answer(session["id"], p2["id"], 0, chosen_index=2, is_correct=False)

    assert store.count_answers_by_participant(session["id"], p1["id"]) == 2
    assert store.count_answers_by_participant(session["id"], p2["id"]) == 1


def test_list_answers_for_participant_ordered_by_question_index(store):
    session = store.create_session(question_set_id=1)
    participant = store.add_participant(session["id"], "Əli", user_id=1)
    store.record_answer(session["id"], participant["id"], 1, chosen_index=1, is_correct=False)
    store.record_answer(session["id"], participant["id"], 0, chosen_index=0, is_correct=True)

    answers = store.list_answers_for_participant(session["id"], participant["id"])
    assert [a["question_index"] for a in answers] == [0, 1]
    assert answers[0]["is_correct"] is True


def test_compute_scores_does_not_leak_across_sessions(store):
    s1 = store.create_session(question_set_id=1)
    s2 = store.create_session(question_set_id=2)
    p1 = store.add_participant(s1["id"], "s1 iştirakçı", user_id=1)
    p2 = store.add_participant(s2["id"], "s2 iştirakçı", user_id=1)
    store.record_answer(s1["id"], p1["id"], 0, chosen_index=0, is_correct=True)
    store.record_answer(s2["id"], p2["id"], 0, chosen_index=0, is_correct=True)

    assert store.compute_scores(s1["id"]) == {p1["id"]: 1}
    assert store.compute_scores(s2["id"]) == {p2["id"]: 1}
