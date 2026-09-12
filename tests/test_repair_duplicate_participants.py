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

import json
import pathlib
import subprocess
import sys

import pytest

from deploy.repair_duplicate_participants import (
    find_duplicates,
    recompute_reports,
    repair,
)
from pipeline.models import MCQQuestion
from server.question_set_store import QuestionSetStore
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


class TestRecomputeReports:
    """Birləşmədən SONRA saxlanmış hesabat köhnəlir — sıralama
    `participant_id` ilə yazılıb və silinmiş ID-lərə istinad edir.
    Müəllim hesabat səhifəsində hələ də üç «Amil» görərdi."""

    @pytest.fixture
    def question_sets(self, tmp_path):
        store = QuestionSetStore(path=str(tmp_path / "question_sets.db"))
        qs = store.create(
            subject="mentiq", title="Bank", material_kind="link",
            material_location="https://x.az", created_by=1,
        )
        for i in range(2):
            store.add_question(qs["id"], MCQQuestion(
                question=f"Sual {i}?", options=["A", "B", "C", "D", "E"],
                correct_index=0, explanation="izah mətni burada",
            ))
        store.mark_ready(qs["id"])
        store.question_set_id = qs["id"]
        return store

    def test_rankings_no_longer_reference_deleted_rows(self, store, question_sets):
        session = store.create_session(question_set_id=question_sets.question_set_id)
        keep = _duplicate_row(store, session["id"], "Amil", 5)
        dup = _duplicate_row(store, session["id"], "Amil", 5)
        store.record_answer(session["id"], dup, 0, 0, True)
        store.save_report(
            session["id"],
            json.dumps({"rankings": [
                {"rank": 1, "participant_id": dup, "display_name": "Amil", "score": 1},
                {"rank": 2, "participant_id": keep, "display_name": "Amil", "score": 0},
            ]}, ensure_ascii=False),
        )

        repair(store._conn, apply=True)
        changed = recompute_reports(store, question_sets, [session["id"]])

        assert changed == [session["id"]]
        rankings = json.loads(store.get(session["id"])["report_json"])["rankings"]
        assert [r["participant_id"] for r in rankings] == [keep]
        assert rankings[0]["score"] == 1, "cavab köçdüyü üçün xal qorunmalıdır"

    def test_a_session_without_a_report_is_skipped(self, store, question_sets):
        """Bitməmiş sessiyaya hesabat YAZMAQ olmaz — o, sessiya
        bitəndə normal axında yaranır."""
        session = store.create_session(question_set_id=question_sets.question_set_id)
        store.add_participant(session["id"], "Amil", user_id=5)

        assert recompute_reports(store, question_sets, [session["id"]]) == []
        assert store.get(session["id"])["report_json"] is None


class TestCommandLine:
    """CLI-nin ÖZÜ — import yolu ilə deyil, subprocess kimi.

    NİYƏ LAZIM OLDU: real VPS icrasında birləşmə yazıldı, sonra
    `--recompute-reports` `ModuleNotFoundError: No module named 'server'`
    ilə sındı. Birbaşa icrada `sys.path[0]` `deploy/` olur, layihə kökü
    yox. Yuxarıdaki testlər bunu GÖRƏ BİLMƏZDİ, çünki pytest
    `pythonpath = ["."]` ilə işləyir.

    `cwd` qəsdən layihə kökündən KƏNARDIR — skript işlədiyi qovluqdan
    asılı olmamalıdır.
    """

    def _script(self) -> pathlib.Path:
        return pathlib.Path(__file__).resolve().parent.parent / "deploy" / "repair_duplicate_participants.py"

    def test_dry_run_from_another_directory(self, store, tmp_path):
        session = store.create_session(question_set_id=1)
        _duplicate_row(store, session["id"], "Amil", 5)
        _duplicate_row(store, session["id"], "Amil", 5)
        # `store` fixture-u EYNİ `tmp_path`-dan istifadə edir.
        db = str(tmp_path / "live_sessions.db")

        result = subprocess.run(
            [sys.executable, str(self._script()), db],
            cwd=str(tmp_path), capture_output=True, text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "Təkrarlanmış qrup: 1" in result.stdout
        assert store.count_participants(session["id"]) == 2, "quru rejim yazmamalıdır"

    def test_recompute_reports_runs_as_a_script(self, store, tmp_path):
        """Məhz VPS-də sınan yol — `server` idxalı."""
        qs_path = tmp_path / "question_sets.db"
        qs_store = QuestionSetStore(path=str(qs_path))
        qs = qs_store.create(
            subject="mentiq", title="Bank", material_kind="link",
            material_location="https://x.az", created_by=1,
        )
        qs_store.add_question(qs["id"], MCQQuestion(
            question="Sual?", options=["A", "B", "C", "D", "E"],
            correct_index=0, explanation="izah mətni burada",
        ))
        qs_store.mark_ready(qs["id"])

        session = store.create_session(question_set_id=qs["id"])
        keep = _duplicate_row(store, session["id"], "Amil", 5)
        dup = _duplicate_row(store, session["id"], "Amil", 5)
        store.record_answer(session["id"], dup, 0, 0, True)
        store.save_report(session["id"], json.dumps({"rankings": [
            {"rank": 1, "participant_id": dup, "display_name": "Amil", "score": 1},
        ]}, ensure_ascii=False))

        result = subprocess.run(
            [sys.executable, str(self._script()), str(tmp_path / "live_sessions.db"),
             "--apply", "--recompute-reports", str(qs_path)],
            cwd=str(tmp_path), capture_output=True, text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "ModuleNotFoundError" not in result.stderr
        assert f"Hesabat yenidən hesablandı: [{session['id']}]" in result.stdout

        fresh = LiveSessionStore(path=str(tmp_path / "live_sessions.db"))
        rankings = json.loads(fresh.get(session["id"])["report_json"])["rankings"]
        assert [r["participant_id"] for r in rankings] == [keep]
        assert rankings[0]["score"] == 1

    def test_named_sessions_are_recomputed_on_a_clean_database(self, store, tmp_path):
        """REAL BOŞLUQ (VPS, 2026-09-12): birləşmə bir icrada yazıldı,
        hesabatın yenidən hesablanması isə sındı. İkinci icrada baza
        artıq TƏMİZ idi, ona görə skript «təkrar yoxdur» deyib erkən
        çıxdı və köhnəlmiş hesabata HEÇ ÇATMADI.

        `--sessions` məhz bunun üçündür: təkrar olmasa da adı çəkilən
        sessiyanın hesabatı yenidən hesablanır.
        """
        qs_path = tmp_path / "question_sets.db"
        qs_store = QuestionSetStore(path=str(qs_path))
        qs = qs_store.create(
            subject="mentiq", title="Bank", material_kind="link",
            material_location="https://x.az", created_by=1,
        )
        qs_store.add_question(qs["id"], MCQQuestion(
            question="Sual?", options=["A", "B", "C", "D", "E"],
            correct_index=0, explanation="izah mətni burada",
        ))
        qs_store.mark_ready(qs["id"])

        session = store.create_session(question_set_id=qs["id"])
        participant = store.add_participant(session["id"], "Amil", user_id=5)
        store.record_answer(session["id"], participant["id"], 0, 0, True)
        # Köhnə hesabat: artıq mövcud olmayan iştirakçıya istinad edir.
        store.save_report(session["id"], json.dumps({"rankings": [
            {"rank": 1, "participant_id": 999, "display_name": "Amil", "score": 1},
        ]}, ensure_ascii=False))

        assert find_duplicates(store._conn) == [], "baza onsuz da təmizdir"

        result = subprocess.run(
            [sys.executable, str(self._script()), str(tmp_path / "live_sessions.db"),
             "--apply", "--recompute-reports", str(qs_path),
             "--sessions", str(session["id"])],
            cwd=str(tmp_path), capture_output=True, text=True,
        )

        assert result.returncode == 0, result.stderr
        assert f"Hesabat yenidən hesablandı: [{session['id']}]" in result.stdout

        fresh = LiveSessionStore(path=str(tmp_path / "live_sessions.db"))
        rankings = json.loads(fresh.get(session["id"])["report_json"])["rankings"]
        assert [r["participant_id"] for r in rankings] == [participant["id"]]

    def test_sessions_without_recompute_flag_is_rejected(self, store, tmp_path):
        """`--sessions` tək başına mənasızdır — sükutla heç nə etməkdənsə
        açıq xəta versin."""
        result = subprocess.run(
            [sys.executable, str(self._script()), str(tmp_path / "live_sessions.db"), "--sessions", "31"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "--recompute-reports" in (result.stderr + result.stdout)
