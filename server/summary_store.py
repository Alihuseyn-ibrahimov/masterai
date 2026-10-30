"""Dərs xülasələri (Faza 3, 2026-10-30) — SQLite saxlanması.

Hər sual bankının (yəni yüklənmiş materialın) ən çox BİR xülasəsi var.
Xülasə əvvəlcə yalnız müəllimə görünür; müəllim onu bir qrup çatına
DƏRC edəndə (`chat_id` + `published_at`) həmin çatın üzvləri görür —
istifadəçi qərarı: AI mətni tələbəyə müəllim baxmadan çatmamalıdır.

`content` — `pipeline.summary.LessonSummary`-nin JSON-u.

`threading.Lock()` kifayətdir (nested public-metod çağırışı yoxdur) —
bax `user_store.py`-nin modul qeydi.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_COLUMNS = (
    "id, question_set_id, course_id, created_by, status, content, error, "
    "chat_id, published_at, created_at, updated_at"
)


class SummaryStore:
    def __init__(self, path: str = "summaries.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_set_id  INTEGER NOT NULL UNIQUE,
                    course_id        INTEGER,
                    created_by       INTEGER NOT NULL,
                    status           TEXT NOT NULL,
                    content          TEXT,
                    error            TEXT,
                    chat_id          INTEGER,
                    published_at     TEXT,
                    created_at       TEXT NOT NULL,
                    updated_at       TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_summaries_chat ON summaries(chat_id);
                """
            )
            self._conn.commit()

    def _get(self, where: str, args: tuple) -> dict | None:
        row = self._conn.execute(f"SELECT {_COLUMNS} FROM summaries WHERE {where}", args).fetchone()
        return dict(row) if row else None

    def get(self, summary_id: int) -> dict | None:
        with self._lock:
            return self._get("id = ?", (summary_id,))

    def get_for_question_set(self, question_set_id: int) -> dict | None:
        with self._lock:
            return self._get("question_set_id = ?", (question_set_id,))

    def start(self, question_set_id: int, *, created_by: int, course_id: int | None) -> dict:
        """Yeni xülasə emalı başladır. Əvvəlki (uğursuz/dərc olunmamış)
        xülasə varsa onun yerinə yazılır — bir bankın bir xülasəsi var."""
        now = _utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO summaries (question_set_id, course_id, created_by, status,
                                       content, error, chat_id, published_at, created_at, updated_at)
                VALUES (?, ?, ?, 'processing', NULL, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(question_set_id) DO UPDATE SET
                    created_by = excluded.created_by, status = 'processing',
                    content = NULL, error = NULL, chat_id = NULL, published_at = NULL,
                    updated_at = excluded.updated_at
                """,
                (question_set_id, course_id, created_by, now, now),
            )
            self._conn.commit()
            return self._get("question_set_id = ?", (question_set_id,))

    def mark_ready(self, summary_id: int, content: str) -> None:
        self._update(summary_id, "status = 'ready', content = ?, error = NULL", (content,))

    def mark_failed(self, summary_id: int, error: str) -> None:
        self._update(summary_id, "status = 'failed', error = ?", (error,))

    def set_content(self, summary_id: int, content: str) -> None:
        self._update(summary_id, "content = ?", (content,))

    def publish(self, summary_id: int, chat_id: int) -> None:
        self._update(summary_id, "chat_id = ?, published_at = ?", (chat_id, _utc_now_iso()))

    def unpublish(self, summary_id: int) -> None:
        self._update(summary_id, "chat_id = NULL, published_at = NULL", ())

    def _update(self, summary_id: int, assignments: str, args: tuple) -> None:
        with self._lock:
            self._conn.execute(
                f"UPDATE summaries SET {assignments}, updated_at = ? WHERE id = ?",
                (*args, _utc_now_iso(), summary_id),
            )
            self._conn.commit()

    def list_published_for_chats(self, chat_ids: list[int]) -> list[dict]:
        if not chat_ids:
            return []
        marks = ",".join("?" * len(chat_ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM summaries WHERE status = 'ready' "
                f"AND published_at IS NOT NULL AND chat_id IN ({marks}) "
                "ORDER BY published_at DESC",
                tuple(chat_ids),
            ).fetchall()
            return [dict(r) for r in rows]

    def fail_interrupted(self, error: str) -> int:
        """Servis restartında yarımçıq qalan emallar (bax `QuestionSetStore`)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE summaries SET status = 'failed', error = ?, updated_at = ? "
                "WHERE status = 'processing'",
                (error, _utc_now_iso()),
            )
            self._conn.commit()
            return cur.rowcount
