"""Çatların və üzvlərinin SQLite saxlanması — minimal CRUD.

Mesajlaşma (WebSocket, mesaj tarixçəsi) bu fazanın əhatəsində deyil — çat
infrastrukturunun öz spec-i dizayn ediləndə əlavə olunacaq.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    def __init__(self, path: str = "chats.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                kind       TEXT NOT NULL,
                name       TEXT,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_members (
                chat_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id)
            );
            """
        )
        self._conn.commit()

    def create(self, kind: str, created_by: int, name: str | None = None) -> dict:
        cur = self._conn.execute(
            "INSERT INTO chats (kind, name, created_by, created_at) VALUES (?, ?, ?, ?)",
            (kind, name, created_by, _utc_now_iso()),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)

    def get(self, chat_id: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT id, kind, name, created_by, created_at FROM chats WHERE id = ?",
            (chat_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def add_member(self, chat_id: int, user_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO chat_members (chat_id, user_id, joined_at) "
            "VALUES (?, ?, ?)",
            (chat_id, user_id, _utc_now_iso()),
        )
        self._conn.commit()

    def list_member_ids(self, chat_id: int) -> list[int]:
        cur = self._conn.execute(
            "SELECT user_id FROM chat_members WHERE chat_id = ?", (chat_id,)
        )
        return [row["user_id"] for row in cur.fetchall()]

    def list_by_user(self, user_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT c.id, c.kind, c.name, c.created_by, c.created_at FROM chats c "
            "JOIN chat_members m ON m.chat_id = c.id "
            "WHERE m.user_id = ? ORDER BY c.created_at",
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]
