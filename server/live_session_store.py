"""Canlı sinif sessiyaları (PIN-lə qoşulma) — SQLite saxlanması.

`live_sessions`/`live_participants`/`live_answers` `question_sets`-dən
(bax `question_set_store.py`) ayrıdır — bu, "hansı sual bankı" ilə "hansı
canlı yarış" arasındakı fərqdir (bir sual bankı ilə vaxtaşırı bir neçə
sessiya keçirilə bilər).

`threading.RLock()` bütün metodları əhatə edir (reentrant, çünki
`create_session()` PIN unikallığını yoxlamaq üçün öz daxilində SELECT
işlədir) — səbəb üçün bax `user_store.py`-nin modul qeydi.
"""

from __future__ import annotations

import random
import sqlite3
import threading
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveSessionStore:
    def __init__(self, path: str = "live_sessions.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS live_sessions (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_set_id         INTEGER NOT NULL,
                    pin                     TEXT NOT NULL,
                    status                  TEXT NOT NULL,
                    current_question_index  INTEGER NOT NULL,
                    report_json             TEXT,
                    created_at              TEXT NOT NULL
                );

                -- `duration_seconds`/`started_at`: fərdi templi canlı sessiya
                -- (bax `.planning/2026-09-08-masterai-live-session-pacing/`)
                -- — sual-üzrə paylaşılan `current_question_index` artıq
                -- irəliləmə üçün istifadə OLUNMUR (hər iştirakçının öz
                -- indeksi cavab sayından törəyir), yalnız BİR ÜMUMİ
                -- sessiya-səviyyəli vaxt limiti üçün bu iki sütun əlavə edilib.

                CREATE TABLE IF NOT EXISTS live_participants (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   INTEGER NOT NULL,
                    display_name TEXT NOT NULL,
                    joined_at    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS live_answers (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id     INTEGER NOT NULL,
                    participant_id INTEGER NOT NULL,
                    question_index INTEGER NOT NULL,
                    chosen_index   INTEGER NOT NULL,
                    is_correct     INTEGER NOT NULL,
                    answered_at    TEXT NOT NULL
                );
                """
            )
            try:
                self._conn.execute(
                    "ALTER TABLE live_participants ADD COLUMN user_id INTEGER"
                )
            except sqlite3.OperationalError:
                pass  # sütun artıq var (mövcud DB) — bax `user_store.py`-nin eyni naxışı
            try:
                self._conn.execute(
                    "ALTER TABLE live_sessions ADD COLUMN duration_seconds INTEGER"
                )
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute(
                    "ALTER TABLE live_sessions ADD COLUMN started_at TEXT"
                )
            except sqlite3.OperationalError:
                pass
            self._conn.commit()

    # ---- sessiyalar ------------------------------------------------

    def _generate_unique_pin(self) -> str:
        """6 rəqəmli PIN — yalnız AKTİV (bitməmiş) sessiyalar arasında
        unikal olmalıdır, bax dizayn sənədi. Çağıran `_lock` altında olmalıdır."""
        for _ in range(50):
            pin = f"{random.randint(0, 999999):06d}"
            cur = self._conn.execute(
                "SELECT 1 FROM live_sessions WHERE pin = ? AND status != 'finished'", (pin,)
            )
            if cur.fetchone() is None:
                return pin
        raise RuntimeError("Unikal PIN yaradıla bilmədi (50 cəhddən sonra)")

    def create_session(self, question_set_id: int) -> dict:
        with self._lock:
            pin = self._generate_unique_pin()
            cur = self._conn.execute(
                "INSERT INTO live_sessions "
                "(question_set_id, pin, status, current_question_index, report_json, created_at) "
                "VALUES (?, ?, 'waiting', 0, NULL, ?)",
                (question_set_id, pin, _utc_now_iso()),
            )
            self._conn.commit()
            return self.get(cur.lastrowid)

    def latest_for_question_sets(self, question_set_ids: list[int]) -> dict | None:
        """Verilmiş sual banklarına aid ƏN SON sessiya.

        `live_sessions` və `question_sets` AYRI bazalardadır (bax
        `question_set_store.py` modul qeydi), ona görə SQL JOIN mümkün
        deyil — bank id-ləri çağırandan gəlir.
        """
        if not question_set_ids:
            return None
        with self._lock:
            placeholders = ",".join("?" for _ in question_set_ids)
            cur = self._conn.execute(
                "SELECT id, question_set_id, pin, status, current_question_index, "
                "created_at, started_at, duration_seconds "
                f"FROM live_sessions WHERE question_set_id IN ({placeholders}) "
                "ORDER BY id DESC LIMIT 1",
                tuple(question_set_ids),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get(self, session_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, question_set_id, pin, status, current_question_index, "
                "report_json, created_at, duration_seconds, started_at "
                "FROM live_sessions WHERE id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_by_pin(self, pin: str) -> dict | None:
        """Yalnız bitməmiş (`waiting`/`active`) sessiyanı tapır — PIN
        bitmiş sessiyadan sonra təkrar istifadə oluna bilər."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, question_set_id, pin, status, current_question_index, "
                "report_json, created_at, duration_seconds, started_at FROM live_sessions "
                "WHERE pin = ? AND status != 'finished' ORDER BY id DESC LIMIT 1",
                (pin,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def start(self, session_id: int, duration_seconds: int) -> dict:
        """Sessiyanı 'active' edir, ümumi vaxt büdcəsini (saniyə) və
        başlama anını qeyd edir — bax `.planning/2026-09-08-masterai-live-
        session-pacing/`, fərdi templi model bunun üzərində qurulur."""
        with self._lock:
            self._conn.execute(
                "UPDATE live_sessions SET status = 'active', duration_seconds = ?, "
                "started_at = ? WHERE id = ?",
                (duration_seconds, _utc_now_iso(), session_id),
            )
            self._conn.commit()
            return self.get(session_id)

    def set_status(self, session_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE live_sessions SET status = ? WHERE id = ?", (status, session_id)
            )
            self._conn.commit()

    def advance(self, session_id: int) -> dict:
        """`current_question_index`-i 1 artırır. Sessiyanın bitib-bitmədiyi
        (indeks sual sayını keçib-keçmədiyi) qərarı çağıranın (runner-in)
        işidir — bu store sual sayını bilmir (bax `question_set_store`)."""
        with self._lock:
            session = self.get(session_id)
            if session is None:
                raise ValueError(f"session_id={session_id} üçün sessiya yoxdur")
            self._conn.execute(
                "UPDATE live_sessions SET current_question_index = ? WHERE id = ?",
                (session["current_question_index"] + 1, session_id),
            )
            self._conn.commit()
            return self.get(session_id)

    def save_report(self, session_id: int, report_json: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE live_sessions SET report_json = ? WHERE id = ?", (report_json, session_id)
            )
            self._conn.commit()

    # ---- iştirakçılar ------------------------------------------------

    def add_participant(
        self, session_id: int, display_name: str, user_id: int | None = None
    ) -> dict:
        """`user_id` YALNIZ tələbə daxil olmuş hesabla PIN-ə qoşulanda dolur
        (bax `app.py`, `live_play_websocket` — token könüllüdür, çünki PIN
        qoşulması hesabsız da mümkündür) — Fərdi tələbə tarixçəsi bunu
        istifadə edir, anonim qoşulmalar (`user_id IS NULL`) tarixçəyə
        düşmür."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO live_participants (session_id, display_name, joined_at, user_id) "
                "VALUES (?, ?, ?, ?)",
                (session_id, display_name, _utc_now_iso(), user_id),
            )
            self._conn.commit()
            return self.get_participant(cur.lastrowid)

    def get_participant(self, participant_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, display_name, joined_at, user_id "
                "FROM live_participants WHERE id = ?",
                (participant_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_participants(self, session_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, display_name, joined_at, user_id FROM live_participants "
                "WHERE session_id = ? ORDER BY joined_at",
                (session_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def count_participants(self, session_id: int) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM live_participants WHERE session_id = ?", (session_id,)
            )
            return cur.fetchone()[0]

    # ---- cavablar ------------------------------------------------

    def has_answered(self, session_id: int, participant_id: int, question_index: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM live_answers WHERE session_id = ? AND participant_id = ? "
                "AND question_index = ?",
                (session_id, participant_id, question_index),
            )
            return cur.fetchone() is not None

    def record_answer(
        self, session_id: int, participant_id: int, question_index: int,
        chosen_index: int, is_correct: bool,
    ) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO live_answers "
                "(session_id, participant_id, question_index, chosen_index, is_correct, answered_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, participant_id, question_index, chosen_index, int(is_correct), _utc_now_iso()),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT id, session_id, participant_id, question_index, chosen_index, "
                "is_correct, answered_at FROM live_answers WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
            data = dict(row)
            data["is_correct"] = bool(data["is_correct"])
            return data

    def count_answers_by_participant(self, session_id: int, participant_id: int) -> int:
        """Bu iştirakçının artıq verdiyi cavabların sayı — fərdi templi
        modeldə bu, onun CARİ sual indeksinə bərabərdir (cavabsız irəliləmə
        mümkün olmadığı üçün ayrıca "current_index" sütunu lazım deyil)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM live_answers WHERE session_id = ? AND participant_id = ?",
                (session_id, participant_id),
            )
            return cur.fetchone()[0]

    def list_answers_for_participant(self, session_id: int, participant_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, participant_id, question_index, chosen_index, "
                "is_correct, answered_at FROM live_answers "
                "WHERE session_id = ? AND participant_id = ? ORDER BY question_index",
                (session_id, participant_id),
            )
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                row["is_correct"] = bool(row["is_correct"])
            return rows

    def list_answers_for_question(self, session_id: int, question_index: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, participant_id, question_index, chosen_index, "
                "is_correct, answered_at FROM live_answers "
                "WHERE session_id = ? AND question_index = ?",
                (session_id, question_index),
            )
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                row["is_correct"] = bool(row["is_correct"])
            return rows

    def list_answers_for_session(self, session_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, participant_id, question_index, chosen_index, "
                "is_correct, answered_at FROM live_answers WHERE session_id = ? "
                "ORDER BY question_index, answered_at",
                (session_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                row["is_correct"] = bool(row["is_correct"])
            return rows

    def list_participations_for_user(self, user_id: int) -> list[dict]:
        """Bu istifadəçinin iştirak etdiyi bütün BİTMİŞ (`finished`) canlı
        sessiyalar — Fərdi tələbə tarixçəsi üçün (bax `app.py`,
        `/history/*`). Xal ayrıca hesablanmır, `report_json`-dan (artıq
        sessiya bitəndə bir dəfə hesablanıb keşlənib) çıxarılır."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT s.id as session_id, s.question_set_id, s.report_json, s.created_at, "
                "p.id as participant_id FROM live_participants p "
                "JOIN live_sessions s ON s.id = p.session_id "
                "WHERE p.user_id = ? AND s.status = 'finished' "
                "ORDER BY s.created_at DESC",
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def compute_scores(self, session_id: int) -> dict[int, int]:
        """Hər iştirakçı üçün düzgün cavab sayı — heç düzgün cavabı
        olmayan iştirakçılar da 0 xalla daxildir (liderlik lövhəsi tam
        siyahı olsun deyə)."""
        with self._lock:
            participants = self.list_participants(session_id)
            scores = {p["id"]: 0 for p in participants}
            cur = self._conn.execute(
                "SELECT participant_id, COUNT(*) as c FROM live_answers "
                "WHERE session_id = ? AND is_correct = 1 GROUP BY participant_id",
                (session_id,),
            )
            for row in cur.fetchall():
                if row["participant_id"] in scores:
                    scores[row["participant_id"]] = row["c"]
            return scores
