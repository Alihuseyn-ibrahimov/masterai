"""Dostluq sorğularının SQLite saxlanması.

`threading.Lock()` bütün metodları əhatə edir — səbəb üçün bax
`user_store.py`-nin modul qeydi (real WebSocket testində tapılan sqlite
çoxlu-thread korlanması). Adi `Lock` (RLock yox) kifayətdir — `create()`
kilid altında yalnız private `_find_between_locked`/`_get_locked`
formalarını çağırır, public metodları yox (reentrant ehtiyac yoxdur).

`UNIQUE(requester_id, addressee_id)` yalnız BİR istiqaməti əhatə edir —
tətbiq səviyyəsində (`find_between`) hər iki istiqamət yoxlanılır.
`create()` üç hallı işləyir: yeni sorğu / mövcud terminal statuslu
(`declined`/`cancelled`/`unfriended`) sətri yeni rollarla əvəz et /
`pending`-i (`DuplicateFriendship`) ya `accepted`-i (`AlreadyFriends`)
rədd et — `quiz_session_store.py`-dəki eyni naxış.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

_RESPONDED_STATUSES = ("accepted", "declined", "cancelled", "unfriended")


class DuplicateFriendship(Exception):
    """Bu iki istifadəçi arasında artıq gözləyən (pending) sorğu var."""


class AlreadyFriends(Exception):
    """Bu iki istifadəçi artıq dostdur (accepted)."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FriendshipStore:
    def __init__(self, path: str = "friendships.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
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
        with self._lock:
            existing = self._find_between_locked(requester_id, addressee_id)
            if existing is None:
                cur = self._conn.execute(
                    "INSERT INTO friendships "
                    "(requester_id, addressee_id, status, created_at, responded_at) "
                    "VALUES (?, ?, 'pending', ?, NULL)",
                    (requester_id, addressee_id, _utc_now_iso()),
                )
                self._conn.commit()
                return self._get_locked(cur.lastrowid)

            if existing["status"] == "pending":
                raise DuplicateFriendship(requester_id, addressee_id)
            if existing["status"] == "accepted":
                raise AlreadyFriends(requester_id, addressee_id)

            # Terminal status (declined/cancelled/unfriended) — sətri yeni
            # rollarla əvəz et, yenidən sorğuya icazə ver.
            self._conn.execute(
                "UPDATE friendships SET requester_id = ?, addressee_id = ?, "
                "status = 'pending', created_at = ?, responded_at = NULL "
                "WHERE id = ?",
                (requester_id, addressee_id, _utc_now_iso(), existing["id"]),
            )
            self._conn.commit()
            return self._get_locked(existing["id"])

    def get(self, friendship_id: int) -> dict | None:
        with self._lock:
            return self._get_locked(friendship_id)

    def _get_locked(self, friendship_id: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT id, requester_id, addressee_id, status, created_at, responded_at "
            "FROM friendships WHERE id = ?",
            (friendship_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_by_user(self, user_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, requester_id, addressee_id, status, created_at, responded_at "
                "FROM friendships WHERE requester_id = ? OR addressee_id = ? "
                "ORDER BY created_at",
                (user_id, user_id),
            )
            return [dict(row) for row in cur.fetchall()]

    def find_between(self, user_a: int, user_b: int) -> dict | None:
        with self._lock:
            return self._find_between_locked(user_a, user_b)

    def _find_between_locked(self, user_a: int, user_b: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT id, requester_id, addressee_id, status, created_at, responded_at "
            "FROM friendships WHERE (requester_id = ? AND addressee_id = ?) "
            "OR (requester_id = ? AND addressee_id = ?)",
            (user_a, user_b, user_b, user_a),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def update_status(self, friendship_id: int, status: str) -> None:
        with self._lock:
            responded_at = _utc_now_iso() if status in _RESPONDED_STATUSES else None
            self._conn.execute(
                "UPDATE friendships SET status = ?, responded_at = ? WHERE id = ?",
                (status, responded_at, friendship_id),
            )
            self._conn.commit()

    def are_friends(self, user_a: int, user_b: int) -> bool:
        with self._lock:
            existing = self._find_between_locked(user_a, user_b)
            return existing is not None and existing["status"] == "accepted"
