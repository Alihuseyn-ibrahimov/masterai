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

    def get(self, session_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, question_set_id, pin, status, current_question_index, "
                "report_json, created_at FROM live_sessions WHERE id = ?",
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
                "report_json, created_at FROM live_sessions "
                "WHERE pin = ? AND status != 'finished' ORDER BY id DESC LIMIT 1",
                (pin,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

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

    def add_participant(self, session_id: int, display_name: str) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO live_participants (session_id, display_name, joined_at) "
                "VALUES (?, ?, ?)",
                (session_id, display_name, _utc_now_iso()),
            )
            self._conn.commit()
            return self.get_participant(cur.lastrowid)

    def get_participant(self, participant_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, display_name, joined_at FROM live_participants WHERE id = ?",
                (participant_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_participants(self, session_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, display_name, joined_at FROM live_participants "
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
