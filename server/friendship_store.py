"""Dostluq sorğularının SQLite saxlanması — minimal CRUD.

Qəbul/rədd axını (status keçidi) bu fazanın əhatəsində deyil — dostluq
endpoint-lərinin öz spec-i dizayn ediləndə əlavə olunacaq.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class DuplicateFriendship(Exception):
    """Bu iki istifadəçi arasında artıq dostluq sorğusu var."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FriendshipStore:
    def __init__(self, path: str = "friendships.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS friendships (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_id INTEGER NOT NULL,
                addressee_id INTEGER NOT NULL,
                status       TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                responded_at TEXT,
                UNIQUE(requester_id, addressee_id)
            );
            """
        )
        self._conn.commit()

    def create(self, requester_id: int, addressee_id: int) -> dict:
        try:
            cur = self._conn.execute(
                "INSERT INTO friendships "
                "(requester_id, addressee_id, status, created_at, responded_at) "
                "VALUES (?, ?, 'pending', ?, NULL)",
                (requester_id, addressee_id, _utc_now_iso()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateFriendship(requester_id, addressee_id) from exc
        return self.get(cur.lastrowid)

    def get(self, friendship_id: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT id, requester_id, addressee_id, status, created_at, responded_at "
            "FROM friendships WHERE id = ?",
            (friendship_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_by_user(self, user_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT id, requester_id, addressee_id, status, created_at, responded_at "
            "FROM friendships WHERE requester_id = ? OR addressee_id = ? "
            "ORDER BY created_at",
            (user_id, user_id),
        )
        return [dict(row) for row in cur.fetchall()]
