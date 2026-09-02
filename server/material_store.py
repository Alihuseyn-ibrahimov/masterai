"""Yüklənən materialların SQLite saxlanması — minimal CRUD.

`label` sütunu material yükləmə fazasında (`ALTER TABLE ... ADD COLUMN`)
əlavə olundu — köhnə sətirlərdə `NULL`/`None`, geriyə uyğundur.

`threading.RLock()` bütün metodları əhatə edir (reentrant, çünki
`create()` öz daxilində `get()`-i çağırır) — səbəb üçün bax
`user_store.py`-nin modul qeydi (real WebSocket testində tapılan sqlite
çoxlu-thread korlanması).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MaterialStore:
    def __init__(self, path: str = "materials.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS materials (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id     INTEGER NOT NULL,
                    uploaded_by INTEGER NOT NULL,
                    kind        TEXT NOT NULL,
                    location    TEXT NOT NULL,
                    status      TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                );
                """
            )
            try:
                self._conn.execute("ALTER TABLE materials ADD COLUMN label TEXT")
            except sqlite3.OperationalError:
                pass  # sütun artıq var (mövcud DB)
            self._conn.commit()

    def create(
        self, chat_id: int, uploaded_by: int, kind: str, location: str, label: str | None = None
    ) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO materials (chat_id, uploaded_by, kind, location, status, created_at, label) "
                "VALUES (?, ?, ?, ?, 'processing', ?, ?)",
                (chat_id, uploaded_by, kind, location, _utc_now_iso(), label),
            )
            self._conn.commit()
            return self.get(cur.lastrowid)

    def get(self, material_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, chat_id, uploaded_by, kind, location, status, created_at, label "
                "FROM materials WHERE id = ?",
                (material_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_by_chat(self, chat_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, chat_id, uploaded_by, kind, location, status, created_at, label "
                "FROM materials WHERE chat_id = ? ORDER BY created_at",
                (chat_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def update_status(self, material_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE materials SET status = ? WHERE id = ?", (status, material_id)
            )
            self._conn.commit()
