"""`LiveSessionStore.chat_scores_by_user` — sinif lövhəsinin canlı hissəsi.

NİYƏ YENİ METOD LAZIMDIR: mövcud `compute_scores(session_id)`
`participant_id` ilə açarlanır və BİR sessiyaya aiddir. Lövhə üçün
lazım olan isə `{user_id: cəm}` və ÇAT ÜZRƏ (bütün sessiyaların cəmi).
İkisi fərqli suallardır — biri «bu yarışda kim qabaqdadır», digəri
«bu sinifdə kim ümumən qabaqdadır».

`HomeworkStore.get_chat_leaderboard` eyni işin ev tapşırığı
versiyasıdır və naxış oradan götürülüb (JOIN + GROUP BY, cəhdi
olmayan üzvü qaytarmır — çağıran 0-la doldurur).
"""

from __future__ import annotations

from server.live_session_store import LiveSessionStore


def _answer(store, session_id, participant_id, index, correct):
    store.record_answer(session_id, participant_id, index, 0, correct)


class TestChatScoresByUser:
    def test_counts_correct_answers_for_the_chat(self):
        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1, chat_id=5, created_by=1)
        p = store.add_participant(session["id"], "Nərmin", user_id=7)
        _answer(store, session["id"], p["id"], 0, True)
        _answer(store, session["id"], p["id"], 1, True)
        _answer(store, session["id"], p["id"], 2, False)

        assert store.chat_scores_by_user(5) == {7: 2}

    def test_sums_across_several_sessions(self):
        """ƏSAS FƏRQ `compute_scores`-dan: sinifdə vaxtaşırı bir neçə
        sessiya keçirilir, lövhə isə ÜMUMİ mənzərəni göstərir."""
        store = LiveSessionStore(":memory:")
        first = store.create_session(question_set_id=1, chat_id=5, created_by=1)
        second = store.create_session(question_set_id=2, chat_id=5, created_by=1)
        p1 = store.add_participant(first["id"], "Nərmin", user_id=7)
        p2 = store.add_participant(second["id"], "Nərmin", user_id=7)
        _answer(store, first["id"], p1["id"], 0, True)
        _answer(store, second["id"], p2["id"], 0, True)
        _answer(store, second["id"], p2["id"], 1, True)

        assert store.chat_scores_by_user(5) == {7: 3}

    def test_keys_are_user_ids_not_participant_ids(self):
        """Qoruyucu: eyni tələbə hər sessiyada YENİ `participant_id`
        alır. Açar səhv olsa, bir adam lövhədə bir neçə sətirlə
        görünərdi."""
        store = LiveSessionStore(":memory:")
        first = store.create_session(question_set_id=1, chat_id=5, created_by=1)
        second = store.create_session(question_set_id=2, chat_id=5, created_by=1)
        p1 = store.add_participant(first["id"], "Nərmin", user_id=7)
        p2 = store.add_participant(second["id"], "Nərmin", user_id=7)
        assert p1["id"] != p2["id"], "hər sessiyada yeni participant_id gözlənilir"
        # Cavab MƏCBURİDİR: sıfır xallı sətir qəsdən qaytarılmır, ona
        # görə cavabsız test boş nəticə alıb yanlış yerdən sınırdı
        # (ilk versiyamda məhz belə oldu).
        _answer(store, first["id"], p1["id"], 0, True)
        _answer(store, second["id"], p2["id"], 0, True)

        assert list(store.chat_scores_by_user(5)) == [7], "bir tələbə iki sətirlə görünür"

    def test_other_chats_are_not_counted(self):
        store = LiveSessionStore(":memory:")
        mine = store.create_session(question_set_id=1, chat_id=5, created_by=1)
        other = store.create_session(question_set_id=1, chat_id=6, created_by=1)
        pm = store.add_participant(mine["id"], "Nərmin", user_id=7)
        po = store.add_participant(other["id"], "Nərmin", user_id=7)
        _answer(store, mine["id"], pm["id"], 0, True)
        _answer(store, other["id"], po["id"], 0, True)

        assert store.chat_scores_by_user(5) == {7: 1}

    def test_chatless_sessions_are_not_counted(self):
        """Köhnə (PIN) sessiyalarda `chat_id` NULL-dur. SQL-də `= NULL`
        heç vaxt doğru olmur, amma səhv yazılsa həmin xallar bütün
        siniflərə sızardı."""
        store = LiveSessionStore(":memory:")
        legacy = store.create_session(question_set_id=1)
        p = store.add_participant(legacy["id"], "Köhnə", user_id=7)
        _answer(store, legacy["id"], p["id"], 0, True)

        assert store.chat_scores_by_user(5) == {}
        assert store.chat_scores_by_user(None) == {}

    def test_participants_with_no_correct_answers_are_absent(self):
        """`HomeworkStore.get_chat_leaderboard` ilə EYNİ müqavilə:
        sıfır xallı sətir qaytarılmır, çağıran üzv siyahısı ilə
        birləşdirib 0-la doldurur. İki mənbə fərqli davransa, lövhədə
        biri üzvü göstərər, digəri göstərməzdi."""
        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1, chat_id=5, created_by=1)
        p = store.add_participant(session["id"], "Nərmin", user_id=7)
        _answer(store, session["id"], p["id"], 0, False)

        assert store.chat_scores_by_user(5) == {}

    def test_several_students_are_separated(self):
        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1, chat_id=5, created_by=1)
        a = store.add_participant(session["id"], "Nərmin", user_id=7)
        b = store.add_participant(session["id"], "Rəşad", user_id=8)
        _answer(store, session["id"], a["id"], 0, True)
        _answer(store, session["id"], b["id"], 0, True)
        _answer(store, session["id"], b["id"], 1, True)

        assert store.chat_scores_by_user(5) == {7: 1, 8: 2}

    def test_empty_chat_returns_empty(self):
        assert LiveSessionStore(":memory:").chat_scores_by_user(5) == {}

    def test_legacy_anonymous_rows_are_ignored(self):
        """Canlı bazada `user_id IS NULL` olan köhnə sətirlər var
        (anonim PIN qoşulmaları). Onları saymaq mümkün deyil — kimin
        olduğu bilinmir — və `None` açarı lövhəni sındırardı."""

        store = LiveSessionStore(":memory:")
        session = store.create_session(question_set_id=1, chat_id=5, created_by=1)
        # Anonim sətri əl ilə yazırıq: `add_participant` artıq buna
        # icazə vermir (bax Faza 4), amma köhnə data mövcuddur.
        cur = store._conn.execute(
            "INSERT INTO live_participants (session_id, display_name, joined_at, user_id) "
            "VALUES (?, 'Qonaq', '2026-09-01', NULL)",
            (session["id"],),
        )
        store._conn.commit()
        _answer(store, session["id"], cur.lastrowid, 0, True)

        assert store.chat_scores_by_user(5) == {}
