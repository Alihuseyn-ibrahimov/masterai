"""Kursların (tenant) SQLite saxlanması — `users.db` faylında.

NİYƏ `users.db`-də: tələbə yeri limiti qeydiyyat anında yoxlanır və
«say + yaz» BİR tranzaksiyada olmalıdır (əks halda iki eyni-anlı
qeydiyyat son yeri ikisi də tutar). Store-lar ayrı fayllardadır, fayllar
arası tranzaksiya yoxdur — ona görə kurslar istifadəçilərlə eyni
fayldadır (bax `UserStore.create`).

Miqrasiya: `ensure_course_schema` həm `UserStore`, həm `CourseStore`
açılanda çağırılır (idempotent). Kurs #1 (`owner`, müddətsiz) yaradılır
və kursu olmayan bütün istifadəçilər ona yazılır — kurs anlayışından
əvvəlki istifadəçilər üçün heç nə dəyişmir.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from server.invite_code import generate_code, normalize_code
from server.licensing import COURSE_STATUSES, STATUS_OWNER, STATUS_TRIAL

DEFAULT_COURSE_ID = 1
DEFAULT_COURSE_NAME = "MasterAI"

PROFILE_EXAM_PREP = "exam_prep"
PROFILE_ENGLISH = "english"
COURSE_PROFILES = (PROFILE_EXAM_PREP, PROFILE_ENGLISH)

# Spec: gündəlik material/bank yükləmə limiti (sahib paneldən dəyişir).
DEFAULT_UPLOAD_LIMIT_STUDENT = 5
DEFAULT_UPLOAD_LIMIT_TEACHER = 30

_COLUMNS = (
    "id, name, profile, status, trial_ends_at, paid_until, seat_limit, "
    "join_code, upload_limit_student, upload_limit_teacher, created_at"
)


class UnknownProfile(ValueError):
    """Kurs profili `COURSE_PROFILES`-dən biri olmalıdır."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_course_schema(conn: sqlite3.Connection) -> None:
    """`courses` cədvəli + kurs #1. Çağıran commit edir."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS courses (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            name                 TEXT NOT NULL,
            profile              TEXT NOT NULL,
            status               TEXT NOT NULL,
            trial_ends_at        TEXT,
            paid_until           TEXT,
            seat_limit           INTEGER,
            join_code            TEXT UNIQUE,
            upload_limit_student INTEGER NOT NULL DEFAULT 5,
            upload_limit_teacher INTEGER NOT NULL DEFAULT 30,
            created_at           TEXT NOT NULL
        )
        """
    )
    # `INSERT OR IGNORE` + sabit id: iki dəfə açılsa da tək kurs #1 olur.
    conn.execute(
        "INSERT OR IGNORE INTO courses (id, name, profile, status, seat_limit, created_at) "
        "VALUES (?, ?, ?, ?, NULL, ?)",
        (DEFAULT_COURSE_ID, DEFAULT_COURSE_NAME, PROFILE_EXAM_PREP, STATUS_OWNER, _utc_now_iso()),
    )


class CourseStore:
    """Tətbiqdə `UserStore.courses` kimi işlədilir — eyni bağlantı və
    kilid. Səbəblər: (1) yer limiti «say + yaz» bir tranzaksiyada
    olmalıdır; (2) testlər `UserStore(":memory:")` işlədir və ayrı
    bağlantı ayrı, BOŞ baza görərdi. `path` yalnız tək başına açmaq üçün
    (miqrasiya testi, VPS skripti)."""

    def __init__(
        self,
        path: str = "users.db",
        *,
        conn: sqlite3.Connection | None = None,
        lock: threading.RLock | None = None,
    ) -> None:
        if conn is None:
            conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
        self._conn = conn
        self._lock = lock or threading.RLock()
        with self._lock:
            ensure_course_schema(self._conn)
            self._conn.commit()

    def create(
        self,
        name: str,
        profile: str,
        *,
        trial_days: int,
        seat_limit: int | None,
        now: datetime | None = None,
    ) -> dict:
        if profile not in COURSE_PROFILES:
            raise UnknownProfile(profile)
        now = now or datetime.now(timezone.utc)
        trial_ends_at = (now + timedelta(days=trial_days)).isoformat()
        with self._lock:
            code = self._unique_code_locked()
            cur = self._conn.execute(
                "INSERT INTO courses (name, profile, status, trial_ends_at, seat_limit, "
                "join_code, upload_limit_student, upload_limit_teacher, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    name, profile, STATUS_TRIAL, trial_ends_at, seat_limit, code,
                    DEFAULT_UPLOAD_LIMIT_STUDENT, DEFAULT_UPLOAD_LIMIT_TEACHER,
                    now.isoformat(),
                ),
            )
            self._conn.commit()
            return self._get_locked(cur.lastrowid)

    def _unique_code_locked(self) -> str:
        while True:
            code = generate_code()
            taken = self._conn.execute(
                "SELECT 1 FROM courses WHERE join_code = ?", (code,)
            ).fetchone()
            if not taken:
                return code

    def _get_locked(self, course_id: int) -> dict | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        return dict(row) if row else None

    def get(self, course_id: int | None) -> dict | None:
        if course_id is None:
            return None
        with self._lock:
            return self._get_locked(course_id)

    def get_by_join_code(self, raw_code: str | None) -> dict | None:
        code = normalize_code(raw_code)
        if not code:
            return None
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_COLUMNS} FROM courses WHERE join_code = ?", (code,)
            ).fetchone()
            return dict(row) if row else None

    def list_all(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(f"SELECT {_COLUMNS} FROM courses ORDER BY id")
            return [dict(row) for row in cur.fetchall()]

    def set_status(self, course_id: int, status: str) -> None:
        if status not in COURSE_STATUSES:
            raise ValueError(f"naməlum kurs statusu: {status}")
        with self._lock:
            self._conn.execute(
                "UPDATE courses SET status = ? WHERE id = ?", (status, course_id)
            )
            self._conn.commit()
