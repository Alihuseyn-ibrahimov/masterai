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

from server.course_store import DEFAULT_COURSE_ID, CourseStore, ensure_course_schema

# Hər SELECT eyni sütunları qaytarır — yeni sütun bir yerdə əlavə olunur.
_COLUMNS = (
    "id, email, password_hash, phone, display_name, created_at, is_teacher, is_admin, "
    "course_id, is_active, is_platform_owner"
)


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
        # Eyni bağlantı + kilid — bax `CourseStore` qeydi.
        self.courses = CourseStore(conn=self._conn, lock=self._lock)

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
            try:
                self._conn.execute(
                    "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # sütun artıq var (mövcud DB)
            # Kurs lisenziyası (spec 2026-09-29). `course_id` NULL buraxılır,
            # sonra kurs #1-ə backfill olunur — ALTER TABLE sabit DEFAULT-u
            # yalnız literal kimi qəbul edir, ona görə açıq UPDATE.
            for ddl in (
                "ALTER TABLE users ADD COLUMN course_id INTEGER",
                "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE users ADD COLUMN is_platform_owner INTEGER NOT NULL DEFAULT 0",
            ):
                try:
                    self._conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # sütun artıq var (mövcud DB)
            ensure_course_schema(self._conn)
            self._conn.execute(
                "UPDATE users SET course_id = ? WHERE course_id IS NULL", (DEFAULT_COURSE_ID,)
            )
            self._conn.commit()

    def create(
        self,
        email: str,
        password_hash: str,
        display_name: str,
        phone: str | None = None,
        course_id: int = DEFAULT_COURSE_ID,
    ) -> dict:
        normalized = _normalize_email(email)
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO users (email, password_hash, phone, display_name, created_at, course_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (normalized, password_hash, phone, display_name, _utc_now_iso(), course_id),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                raise DuplicateEmail(normalized) from exc
            return self.get_by_id(cur.lastrowid)

    def get_by_email(self, email: str) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                f"SELECT {_COLUMNS} "
                "FROM users WHERE email = ?",
                (_normalize_email(email),),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_by_id(self, user_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                f"SELECT {_COLUMNS} "
                "FROM users WHERE id = ?",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def set_teacher(self, user_id: int, is_teacher: bool) -> None:
        """`is_teacher` bayrağını dəyişir — Çox-müəllimli idarəetmədən
        (Faza 4) əvvəl idarəetmə UI-ı YOXDUR, VPS-də əl ilə bir dəfəlik
        skriptdən çağırılırdı; indi `POST /admin/teachers` bunu çağırır
        (bax `app.py`, yalnız `is_admin` istifadəçilər üçün)."""
        with self._lock:
            self._conn.execute(
                "UPDATE users SET is_teacher = ? WHERE id = ?", (int(is_teacher), user_id)
            )
            self._conn.commit()

    def set_admin(self, user_id: int, is_admin: bool) -> None:
        """`is_admin` bayrağını dəyişir — İLK admin hələ də VPS-də əl ilə
        (bu metodla) təyin edilməlidir (bootstrap problemi: admin YOXDURSA
        heç kim admin təyin edə bilməz), sonrakı adminlər tətbiq daxilindən
        təyin oluna bilər (bax dizayn qeydi, `masterai/CLAUDE.md`)."""
        with self._lock:
            self._conn.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id)
            )
            self._conn.commit()

    def set_active(self, user_id: int, is_active: bool) -> None:
        """`is_active=0` — giriş bağlanır (token növbəti sorğuda işləmir)
        və tələbə yeri boşalır. Data silinmir."""
        with self._lock:
            self._conn.execute(
                "UPDATE users SET is_active = ? WHERE id = ?", (int(is_active), user_id)
            )
            self._conn.commit()

    def set_platform_owner(self, user_id: int, is_owner: bool) -> None:
        """Platforma sahibi bayrağı — `set_admin` kimi YALNIZ VPS-də əl ilə
        çağırılır. Bu bayrağı dəyişən API endpoint-i qəsdən YOXDUR."""
        with self._lock:
            self._conn.execute(
                "UPDATE users SET is_platform_owner = ? WHERE id = ?", (int(is_owner), user_id)
            )
            self._conn.commit()

    def list_teachers(self) -> list[dict]:
        """Hazırda `is_teacher=1` olan bütün istifadəçilər — admin-in
        "Müəllim idarəetməsi" ekranında siyahını görməsi üçün (bax
        `app.py`, `GET /admin/teachers`)."""
        with self._lock:
            cur = self._conn.execute(
                f"SELECT {_COLUMNS} "
                "FROM users WHERE is_teacher = 1 ORDER BY display_name"
            )
            return [dict(row) for row in cur.fetchall()]

    def ping(self) -> bool:
        """DB bağlantısının işlək olduğunu yoxlayır (`/health` üçün)."""
        with self._lock:
            self._conn.execute("SELECT 1")
            return True

    def count_all(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
