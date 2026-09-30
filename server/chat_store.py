"""Çatların və üzvlərinin SQLite saxlanması — minimal CRUD.

Mesajlaşma (WebSocket, mesaj tarixçəsi) bu fazanın əhatəsində deyil — çat
infrastrukturunun öz spec-i dizayn ediləndə əlavə olunacaq.

`threading.Lock()` bütün metodları əhatə edir — səbəb üçün bax
`user_store.py`-nin modul qeydi (real WebSocket testində tapılan sqlite
çoxlu-thread korlanması).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

from server.course_store import DEFAULT_COURSE_ID
from server.invite_code import generate_code, normalize_code


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    def __init__(self, path: str = "chats.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
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
            # Dəvət kodu — `live_session_store.py`-dəki eyni
            # `ALTER TABLE ADD COLUMN` naxışı (mövcud DB-də sütun artıq
            # ola bilər).
            try:
                self._conn.execute("ALTER TABLE chats ADD COLUMN invite_code TEXT")
            except sqlite3.OperationalError:
                pass
            # Kurs sərhədi (spec 2026-09-29 §4): köhnə çatlar kurs #1-dədir.
            try:
                self._conn.execute("ALTER TABLE chats ADD COLUMN course_id INTEGER")
            except sqlite3.OperationalError:
                pass
            self._conn.execute(
                "UPDATE chats SET course_id = ? WHERE course_id IS NULL", (DEFAULT_COURSE_ID,)
            )
            self._conn.commit()
            self._backfill_invite_codes_locked()

    def _backfill_invite_codes_locked(self) -> None:
        """Sütun əlavə olunanda mövcud çatlar NULL qalır. Backfill
        olmasa həmin çatlara heç vaxt qoşulmaq olmazdı — canlı bazada
        artıq çatlar var."""
        cur = self._conn.execute(
            "SELECT id FROM chats WHERE kind = 'group' AND "
            "(invite_code IS NULL OR invite_code = '')"
        )
        for row in cur.fetchall():
            self._conn.execute(
                "UPDATE chats SET invite_code = ? WHERE id = ?",
                (self._unique_code_locked(), row["id"]),
            )
        self._conn.commit()

    def _unique_code_locked(self) -> str:
        """Toqquşma ehtimalı çox kiçikdir, amma sıfır deyil — kod
        UNIKAL olmalıdır, əks halda iki çat eyni kodla tapılar."""
        while True:
            code = generate_code()
            cur = self._conn.execute(
                "SELECT 1 FROM chats WHERE invite_code = ?", (code,)
            )
            if cur.fetchone() is None:
                return code

    def create(
        self,
        kind: str,
        created_by: int,
        name: str | None = None,
        course_id: int = DEFAULT_COURSE_ID,
    ) -> dict:
        with self._lock:
            # Şəxsi çata kod ilə qoşulmaq anlayışı yoxdur — yalnız
            # qrup çatı dəvət kodu alır.
            code = self._unique_code_locked() if kind == "group" else None
            cur = self._conn.execute(
                "INSERT INTO chats (kind, name, created_by, created_at, invite_code, course_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (kind, name, created_by, _utc_now_iso(), code, course_id),
            )
            self._conn.commit()
            return self._get_locked(cur.lastrowid)

    def get_by_invite_code(self, raw_code: str | None) -> dict | None:
        """Kod ilə çat. Böyük/kiçik hərf, defis və boşluq fərqi
        SƏHV SAYILMIR — tələbə ekranda `K7M-3QX` görür və olduğu kimi
        yazır."""
        code = normalize_code(raw_code)
        if not code:
            return None
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, kind, name, created_by, created_at, invite_code, course_id "
                "FROM chats WHERE invite_code = ?",
                (code,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def regenerate_invite_code(self, chat_id: int) -> str:
        """Kod sinifdən kənara çıxsa (şəkil, ekran paylaşımı) müəllim
        onu yeniləyir — köhnə kod dərhal işləməz olur."""
        with self._lock:
            code = self._unique_code_locked()
            self._conn.execute(
                "UPDATE chats SET invite_code = ? WHERE id = ?", (code, chat_id)
            )
            self._conn.commit()
            return code

    def get(self, chat_id: int) -> dict | None:
        with self._lock:
            return self._get_locked(chat_id)

    def _get_locked(self, chat_id: int) -> dict | None:
        cur = self._conn.execute(
            "SELECT id, kind, name, created_by, created_at, invite_code, course_id "
            "FROM chats WHERE id = ?",
            (chat_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def add_member(self, chat_id: int, user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO chat_members (chat_id, user_id, joined_at) "
                "VALUES (?, ?, ?)",
                (chat_id, user_id, _utc_now_iso()),
            )
            self._conn.commit()

    def list_member_ids(self, chat_id: int) -> list[int]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT user_id FROM chat_members WHERE chat_id = ?", (chat_id,)
            )
            return [row["user_id"] for row in cur.fetchall()]

    def list_by_user(self, user_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT c.id, c.kind, c.name, c.created_by, c.created_at, c.invite_code "
                "FROM chats c "
                "JOIN chat_members m ON m.chat_id = c.id "
                "WHERE m.user_id = ? ORDER BY c.created_at",
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_ids_by_course(self, course_id: int) -> list[int]:
        """Sahib panelinin aktivlik sayğacları üçün (çatlar ayrı faylda,
        JOIN mümkün deyil — digər store-lar çat ID-ləri ilə sayır)."""
        with self._lock:
            return [
                row[0] for row in self._conn.execute(
                    "SELECT id FROM chats WHERE course_id = ?", (course_id,)
                ).fetchall()
            ]
