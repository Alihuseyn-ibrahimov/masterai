"""Dərslər və davamiyyət (MasterAI Classroom, gün 1, 2026-10-31).

Dərs bir qrup çatına (sinfə) bağlıdır: müəllim mövzu, vaxt və növ
(onlayn / sinifdə) təyin edir, dərs `scheduled` → `live` → `ended`
yolunu keçir. Davamiyyət (dərs, istifadəçi) cütü üçün BİR sətirdir —
təkrar qoşulma yeni sətir yazmır (bax CLAUDE.md «Dərs: təkrarlanan
iştirakçı», eyni tələ).

`threading.Lock()` kifayətdir (nested public-metod çağırışı yoxdur) —
bax `user_store.py`-nin modul qeydi.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

LESSON_MODES = ("online", "offline")
LESSON_STATUSES = ("scheduled", "live", "ended")

_COLUMNS = (
    "id, chat_id, course_id, created_by, title, description, starts_at, "
    "duration_min, mode, status, notes, started_at, ended_at, created_at, updated_at"
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LessonStore:
    def __init__(self, path: str = "lessons.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS lessons (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id      INTEGER NOT NULL,
                    course_id    INTEGER,
                    created_by   INTEGER NOT NULL,
                    title        TEXT NOT NULL,
                    description  TEXT NOT NULL DEFAULT '',
                    starts_at    TEXT NOT NULL,
                    duration_min INTEGER NOT NULL,
                    mode         TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'scheduled',
                    notes        TEXT NOT NULL DEFAULT '',
                    started_at   TEXT,
                    ended_at     TEXT,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lessons_chat ON lessons(chat_id, starts_at);
                CREATE TABLE IF NOT EXISTS lesson_attendance (
                    lesson_id INTEGER NOT NULL,
                    user_id   INTEGER NOT NULL,
                    method    TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (lesson_id, user_id)
                );
                """
            )
            self._conn.commit()

    def _get(self, lesson_id: int) -> dict | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM lessons WHERE id = ?", (lesson_id,)
        ).fetchone()
        return dict(row) if row else None

    def create(
        self,
        chat_id: int,
        *,
        course_id: int | None,
        created_by: int,
        title: str,
        description: str,
        starts_at: str,
        duration_min: int,
        mode: str,
    ) -> dict:
        if mode not in LESSON_MODES:
            raise ValueError(mode)
        now = _utc_now_iso()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO lessons (chat_id, course_id, created_by, title, description, "
                "starts_at, duration_min, mode, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (chat_id, course_id, created_by, title, description, starts_at,
                 duration_min, mode, now, now),
            )
            self._conn.commit()
            return self._get(cur.lastrowid)

    def get(self, lesson_id: int) -> dict | None:
        with self._lock:
            return self._get(lesson_id)

    def list_for_chats(self, chat_ids: list[int]) -> list[dict]:
        """Ən yaxın dərs əvvəldə: başlama vaxtına görə artan sıra."""
        if not chat_ids:
            return []
        marks = ",".join("?" * len(chat_ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM lessons WHERE chat_id IN ({marks}) "
                "ORDER BY starts_at, id",
                tuple(chat_ids),
            ).fetchall()
        return [dict(r) for r in rows]

    def update(self, lesson_id: int, **fields) -> dict | None:
        """Yalnız verilən sahələr dəyişir (None = toxunma)."""
        allowed = {"title", "description", "starts_at", "duration_min", "mode", "notes"}
        changes = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "mode" in changes and changes["mode"] not in LESSON_MODES:
            raise ValueError(changes["mode"])
        with self._lock:
            if changes:
                assignments = ", ".join(f"{column} = ?" for column in changes)
                self._conn.execute(
                    f"UPDATE lessons SET {assignments}, updated_at = ? WHERE id = ?",
                    (*changes.values(), _utc_now_iso(), lesson_id),
                )
                self._conn.commit()
            return self._get(lesson_id)

    def set_status(self, lesson_id: int, status: str) -> dict | None:
        """`live` ilk başlama, `ended` bitmə anını yazır. Yenidən başladılan
        dərsin `started_at`-i dəyişmir: davamiyyət onun ilk anına baxır."""
        if status not in LESSON_STATUSES:
            raise ValueError(status)
        now = _utc_now_iso()
        with self._lock:
            self._conn.execute(
                "UPDATE lessons SET status = ?, "
                "started_at = CASE WHEN ? = 'live' THEN COALESCE(started_at, ?) ELSE started_at END, "
                "ended_at = CASE WHEN ? = 'ended' THEN ? ELSE NULL END, "
                "updated_at = ? WHERE id = ?",
                (status, status, now, status, now, now, lesson_id),
            )
            self._conn.commit()
            return self._get(lesson_id)

    def delete(self, lesson_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM lesson_attendance WHERE lesson_id = ?", (lesson_id,))
            self._conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            self._conn.commit()

    def mark_attendance(self, lesson_id: int, user_id: int, method: str) -> dict:
        """Tap-və-ya-yarat: ilk qoşulma vaxtı və üsulu saxlanır."""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO lesson_attendance (lesson_id, user_id, method, joined_at) "
                "VALUES (?, ?, ?, ?)",
                (lesson_id, user_id, method, _utc_now_iso()),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT lesson_id, user_id, method, joined_at FROM lesson_attendance "
                "WHERE lesson_id = ? AND user_id = ?",
                (lesson_id, user_id),
            ).fetchone()
        return dict(row)

    def list_attendance(self, lesson_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT lesson_id, user_id, method, joined_at FROM lesson_attendance "
                "WHERE lesson_id = ? ORDER BY joined_at",
                (lesson_id,),
            ).fetchall()
        return [dict(r) for r in rows]
