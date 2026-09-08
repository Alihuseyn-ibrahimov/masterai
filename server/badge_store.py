"""Nailiyyət nişanları (Faza 6) — SQLite saxlanması.

Nişan MEYARLARI burada YOXDUR — bu Store yalnız "hansı tələbə hansı
nişanı nə vaxt qazanıb" məlumatını saxlayır (idempotent). Meyarların
yoxlanması `app.py`-də (`_evaluate_badges`) mövcud tarixçə/ev tapşırığı
datası üzərindən aparılır, bax dizayn sənədi.

`threading.Lock()` kifayətdir (nested public-metod çağırışı yoxdur) —
bax `user_store.py`-nin modul qeydi (ümumi RLock/Lock seçimi qaydası).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BadgeStore:
    def __init__(self, path: str = "badges.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS earned_badges (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id  INTEGER NOT NULL,
                    badge_type  TEXT NOT NULL,
                    earned_at   TEXT NOT NULL,
                    UNIQUE(student_id, badge_type)
                );
                """
            )
            self._conn.commit()

    def get_earned(self, student_id: int) -> dict[str, str]:
        """`{badge_type: earned_at}` xəritəsi — mövcud olmayan nişan
        açarı bu tələbə üçün hələ qazanılmayıb deməkdir."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT badge_type, earned_at FROM earned_badges WHERE student_id = ?",
                (student_id,),
            )
            return {row["badge_type"]: row["earned_at"] for row in cur.fetchall()}

    def mark_earned(self, student_id: int, badge_type: str) -> None:
        """İdempotentdir — nişan artıq qazanılıbsa sükutla heç nə etmir
        (`UNIQUE(student_id, badge_type)` toqquşmasını udur)."""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO earned_badges (student_id, badge_type, earned_at) "
                    "VALUES (?, ?, ?)",
                    (student_id, badge_type, _utc_now_iso()),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                pass
