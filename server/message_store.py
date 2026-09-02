"""Çat mesajlarının SQLite saxlanması.

Digər Store-larla eyni naxış (`UserStore` və s.). `kind` sərbəst TEXT-dir
(CHECK yoxdur) — Faza B-də `quiz_question`/`quiz_result` üçün miqrasiya
lazım olmayacaq (bax spec, bölmə 3).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageStore:
    def __init__(self, path: str = "messages.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    INTEGER NOT NULL,
                sender_id  INTEGER,
                kind       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def create(self, chat_id: int, sender_id: int | None, kind: str, content: str) -> dict:
        cur = self._conn.execute(
            "INSERT INTO messages (chat_id, sender_id, kind, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, sender_id, kind, content, _utc_now_iso()),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id, chat_id, sender_id, kind, content, created_at "
            "FROM messages WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return dict(row)

    def list_by_chat(self, chat_id: int, limit: int = 50) -> list[dict]:
        # Ən son `limit` mesajı DESC ilə çəkib, sonra xronoloji sıraya
        # çeviririk — "son N" məntiqini "ilk N" ilə qarışdırmamaq üçün.
        cur = self._conn.execute(
            "SELECT id, chat_id, sender_id, kind, content, created_at FROM messages "
            "WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        )
        rows = [dict(row) for row in cur.fetchall()]
        rows.reverse()
        return rows
