"""İstifadəçi hesablarının SQLite saxlanması.

`dildostu/server/dildostu_server/user_store.py` naxışı: `sqlite3` standart
kitabxana, tək worker, qısa əməliyyatlar. Şifrə YALNIZ hash kimi saxlanır —
bu modul hash-ləməni özü etmir (bax `auth.py`), yalnız verilən dəyəri yazır.

`threading.RLock()` bütün metodları əhatə edir: `check_same_thread=False`
sqlite3-ə çoxlu thread-dən çağırışa YALNIZ İCAZƏ verir, onu thread-safe
ETMİR — real WebSocket smoke testində (Starlette `TestClient` hər
bağlantını ayrı OS thread-ində işlədir) bunsuz `OperationalError: cannot
commit - no transaction is active` alınırdı. `RLock` (adi `Lock` yox)
seçilib, çünki `create()` öz daxilində `get_by_id()`-i çağırır (reentrant
olmalıdır, əks halda özü-özünü bloklayardı).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone


class DuplicateEmail(Exception):
    """Bu e-poçt artıq qeydiyyatdadır."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_email(email: str) -> str:
    """E-poçt registrə həssas olmamalıdır (Ali@X.com == ali@x.com)."""
    return email.strip().lower()


class UserStore:
    def __init__(self, path: str = "users.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    email         TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    phone         TEXT UNIQUE,
                    display_name  TEXT NOT NULL,
                    created_at    TEXT NOT NULL
                );
                """
            )
            try:
                self._conn.execute(
                    "ALTER TABLE users ADD COLUMN is_teacher INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # sütun artıq var (mövcud DB) — bax `material_store.py`-nin eyni naxışı
            self._conn.commit()

    def create(
        self,
        email: str,
        password_hash: str,
        display_name: str,
        phone: str | None = None,
    ) -> dict:
        normalized = _normalize_email(email)
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO users (email, password_hash, phone, display_name, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (normalized, password_hash, phone, display_name, _utc_now_iso()),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                raise DuplicateEmail(normalized) from exc
            return self.get_by_id(cur.lastrowid)

    def get_by_email(self, email: str) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, email, password_hash, phone, display_name, created_at, is_teacher "
                "FROM users WHERE email = ?",
                (_normalize_email(email),),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_by_id(self, user_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, email, password_hash, phone, display_name, created_at, is_teacher "
                "FROM users WHERE id = ?",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def set_teacher(self, user_id: int, is_teacher: bool) -> None:
        """`is_teacher` bayrağını dəyişir — idarəetmə UI-ı YOXDUR (bax
        dizayn sənədi, Ev Təkrarı Rejimi), bu, VPS-də əl ilə bir dəfəlik
        skriptdən (və ya bu test kimi) çağırılmaq üçündür."""
        with self._lock:
            self._conn.execute(
                "UPDATE users SET is_teacher = ? WHERE id = ?", (int(is_teacher), user_id)
            )
            self._conn.commit()

    def ping(self) -> bool:
        """DB bağlantısının işlək olduğunu yoxlayır (`/health` üçün)."""
        with self._lock:
            self._conn.execute("SELECT 1")
            return True

    def count_all(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
