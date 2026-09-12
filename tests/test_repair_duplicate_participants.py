"""Canlı bazadakı təkrarlanmış iştirakçı sətirlərinin təmiri.

NİYƏ AYRICA SKRİPT, MİQRASİYA DEYİL: bu, canlı datanı BİRLƏŞDİRİR
(cavabları köçürür, sətirləri silir) — geri qaytarılması yalnız
backup-dan mümkündür. Servis start-ında sükutla işləməməlidir;
əvvəlcə quru rejimdə göstərir, sonra `--apply` ilə yazır.

Kök səbəb 2026-09-12-də `LiveSessionStore.add_participant`-də
düzəldildi (tap-və-ya-yarat). Bu skript YALNIZ həmin düzəlişdən
əvvəl yaranmış sətirləri təmizləyir.
"""

from __future__ import annotations

import pytest

from deploy.repair_duplicate_participants import find_duplicates, repair
from server.live_session_store import LiveSessionStore


@pytest.fixture
def store(tmp_path):
    return LiveSessionStore(path=str(tmp_path / "live_sessions.db"))


def _duplicate_row(store, session_id: int, name: str, user_id: int) -> int:
    """Düzəlişdən ƏVVƏLKİ davranışı təqlid edir — birbaşa `INSERT`.

    `add_participant` artıq təkrar sətir YARADA BİLMİR, ona görə
    testin köhnə vəziyyəti quraşdırmaqdan başqa yolu yoxdur.
    """
    cur = store._conn.execute(
        "INSERT INTO live_participants (session_id, display_name, joined_at, user_id) "
        "VALUES (?, ?, ?, ?)",
        (session_id, name, f"2026-09-12T07:0{user_id}:00+00:00", user_id),
    )
    store._conn.commit()
    return cur.lastrowid


class TestFindDuplicates:
    def test_clean_database_reports_nothing(self, store):
        session = store.create_session(question_set_id=1)
        store.add_participant(session["id"], "Amil", user_id=5)
        store.add_participant(session["id"], "Nigar", user_id=6)

        assert find_duplicates(store._conn) == []

    def test_reports_a_group_with_the_keeper_first(self, store):
        session = store.create_session(question_set_id=1)
        keep = _duplicate_row(store, session["id"], "Amil", 5)
        dup1 = _duplicate_row(store, session["id"], "Amil", 5)
        dup2 = _duplicate_row(store, session["id"], "Amil", 5)

        groups = find_duplicates(store._conn)
        assert len(groups) == 1
        assert groups[0]["session_id"] == session["id"]
        assert groups[0]["user_id"] == 5
        assert groups[0]["keep_id"] == keep
        assert sorted(groups[0]["drop_ids"]) == sorted([dup1, dup2])

    def test_anonymous_rows_are_never_merged(self, store):
        """Köhnə PIN sətirlərində `user_id IS NULL` — kimin olduğu
        BİLİNMİR, yəni onları birləşdirmək datanı uydurmaq olardı."""
        session = store.create_session(question_set_id=1)
        for _ in range(2):
            store._conn.execute(
                "INSERT INTO live_participants (session_id, display_name, joined_at, user_id) "
                "VALUES (?, 'Qonaq', '2026-01-01T00:00:00+00:00', NULL)",
                (session["id"],),
            )
        store._conn.commit()

        assert find_duplicates(store._conn) == []


class TestRepair:
    def test_dry_run_changes_nothing(self, store):
        session = store.create_session(question_set_id=1)
        keep = _duplicate_row(store, session["id"], "Amil", 5)
        dup = _duplicate_row(store, session["id"], "Amil", 5)
        store.record_answer(session["id"], dup, 0, 1, True)

        summary = repair(store._conn, apply=False)

        assert summary["groups"] == 1
        assert summary["removed_participants"] == 2 - 1
        assert store.count_participants(session["id"]) == 2, "quru rejim yazmamalıdır"
        assert store.count_answers_by_participant(session["id"], keep) == 0

    def test_answers_move_to_the_kept_row(self, store):
        session = store.create_session(question_set_id=1)
        keep = _duplicate_row(store, session["id"], "Amil", 5)
        dup = _duplicate_row(store, session["id"], "Amil", 5)
        store.record_answer(session["id"], keep, 0, 1, True)
        store.record_answer(session["id"], dup, 1, 0, True)

        summary = repair(store._conn, apply=True)

        assert summary["moved_answers"] == 1
        assert store.count_participants(session["id"]) == 1
        assert store.count_answers_by_participant(session["id"], keep) == 2
        assert store.compute_scores(session["id"]) == {keep: 2}

    def test_a_question_answered_twice_keeps_the_first_answer(self, store):
        """Eyni sual iki sətirdə cavablanıbsa, İLK cavab qalır —
        tələbə onu real olaraq birinci verib; ikincisi yenilənmiş
        səhifənin təkrarıdır."""
        session = store.create_session(question_set_id=1)
        keep = _duplicate_row(store, session["id"], "Amil", 5)
        dup = _duplicate_row(store, session["id"], "Amil", 5)
        store.record_answer(session["id"], keep, 0, 0, True)
        store.record_answer(session["id"], dup, 0, 3, False)

        summary = repair(store._conn, apply=True)

        assert summary["dropped_answers"] == 1
        assert store.count_answers_by_participant(session["id"], keep) == 1
        assert store.compute_scores(session["id"]) == {keep: 1}, "düzgün cavab itməməlidir"

    def test_other_sessions_are_untouched(self, store):
        dirty = store.create_session(question_set_id=1)
        _duplicate_row(store, dirty["id"], "Amil", 5)
        _duplicate_row(store, dirty["id"], "Amil", 5)

        clean = store.create_session(question_set_id=1)
        other = store.add_participant(clean["id"], "Nigar", user_id=6)
        store.record_answer(clean["id"], other["id"], 0, 0, True)

        repair(store._conn, apply=True)

        assert store.count_participants(clean["id"]) == 1
        assert store.count_answers_by_participant(clean["id"], other["id"]) == 1

    def test_running_twice_is_a_no_op(self, store):
        session = store.create_session(question_set_id=1)
        keep = _duplicate_row(store, session["id"], "Amil", 5)
        _duplicate_row(store, session["id"], "Amil", 5)
        store.record_answer(session["id"], keep, 0, 0, True)

        repair(store._conn, apply=True)
        second = repair(store._conn, apply=True)

        assert second["groups"] == 0
        assert store.count_participants(session["id"]) == 1

    def test_sessions_with_a_saved_report_are_flagged(self, store):
        """Hesabat `participant_id` ilə saxlanılıb — sətirlər
        birləşəndən sonra köhnəlir. Skript bunu SUSMAMALIDIR."""
        session = store.create_session(question_set_id=1)
        _duplicate_row(store, session["id"], "Amil", 5)
        _duplicate_row(store, session["id"], "Amil", 5)
        store.save_report(session["id"], '{"rankings": []}')

        summary = repair(store._conn, apply=True)

        assert session["id"] in summary["stale_reports"]
