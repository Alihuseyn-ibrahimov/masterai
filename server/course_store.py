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

import hashlib
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from server.invite_code import generate_code, normalize_code
from server.licensing import COURSE_STATUSES, STATUS_ACTIVE, STATUS_OWNER, STATUS_TRIAL

DEFAULT_COURSE_ID = 1
DEFAULT_COURSE_NAME = "MasterAI"

PROFILE_EXAM_PREP = "exam_prep"
PROFILE_ENGLISH = "english"
COURSE_PROFILES = (PROFILE_EXAM_PREP, PROFILE_ENGLISH)

# Spec: gündəlik material/bank yükləmə limiti (sahib paneldən dəyişir).
DEFAULT_UPLOAD_LIMIT_STUDENT = 5
DEFAULT_UPLOAD_LIMIT_TEACHER = 30

# Müəllim dəvət linki: birdəfəlik, 7 gün (spec §3).
TEACHER_INVITE_TTL = timedelta(days=7)

_COLUMNS = (
    "id, name, profile, status, trial_ends_at, paid_until, seat_limit, "
    "join_code, upload_limit_student, upload_limit_teacher, created_at"
)


class UnknownProfile(ValueError):
    """Kurs profili `COURSE_PROFILES`-dən biri olmalıdır."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_invite_token(token: str) -> str:
    """Dəvət tokeni bazada YALNIZ hash kimi saxlanır: baza sızsa belə
    istifadə olunmamış link işlənə bilməz. Token 256 bit təsadüfidir,
    ona görə duzsuz SHA-256 kifayətdir (şifrə deyil, lüğət hücumu yoxdur)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teacher_invites (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            course_id  INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at    TEXT,
            used_by    INTEGER
        )
        """
    )
    # Sahib əməliyyatlarının jurnalı: «biz ödəmişdik, niyə bağlandı?»
    # mübahisəsində tarix MƏNBƏDƏN görünsün (spec §3). Yalnız əlavə olunur.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_audit_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            at        TEXT NOT NULL,
            owner_id  INTEGER NOT NULL,
            course_id INTEGER,
            action    TEXT NOT NULL,
            details   TEXT NOT NULL
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
            # Qeydiyyat kodla olduğu üçün kodsuz kurs (kurs #1 yaradılanda
            # kod verilmir) heç kimi qəbul edə bilməz — backfill.
            for row in self._conn.execute(
                "SELECT id FROM courses WHERE join_code IS NULL OR join_code = ''"
            ).fetchall():
                self._conn.execute(
                    "UPDATE courses SET join_code = ? WHERE id = ?",
                    (self._unique_code_locked(), row[0]),
                )
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

    def set_paid_until(self, course_id: int, paid_until: datetime) -> None:
        """Ödəniş qeydi: kurs `active` olur və `paid_until`-a qədər açıqdır.
        Uzatma hesabı (nə qədər, hansı tarixdən) sahib paneli qatındadır."""
        with self._lock:
            self._conn.execute(
                "UPDATE courses SET status = ?, paid_until = ? WHERE id = ?",
                (STATUS_ACTIVE, paid_until.isoformat(), course_id),
            )
            self._conn.commit()

    def create_teacher_invite(
        self, course_id: int, *, created_by: int, now: datetime | None = None
    ) -> str:
        """Yeni dəvət; XAM tokeni qaytarır (yalnız bir dəfə, link üçün)."""
        now = now or datetime.now(timezone.utc)
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._conn.execute(
                "INSERT INTO teacher_invites "
                "(token_hash, course_id, created_by, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    hash_invite_token(token), course_id, created_by,
                    now.isoformat(), (now + TEACHER_INVITE_TTL).isoformat(),
                ),
            )
            self._conn.commit()
        return token

    def peek_teacher_invite(self, token: str, *, now: datetime | None = None) -> dict | None:
        """Etibarlı (istifadə olunmamış, müddəti bitməmiş) dəvət və ya None.
        Yalnız ön yoxlama üçündür (kursun açıqlığı) — istifadə anında
        `UserStore.create_teacher_from_invite` hər şeyi YENİDƏN yoxlayır."""
        if not token:
            return None
        now = now or datetime.now(timezone.utc)
        with self._lock:
            row = self._conn.execute(
                "SELECT id, course_id, expires_at, used_at FROM teacher_invites "
                "WHERE token_hash = ?",
                (hash_invite_token(token),),
            ).fetchone()
        if row is None or row["used_at"] is not None:
            return None
        if now >= datetime.fromisoformat(row["expires_at"]):
            return None
        return dict(row)

    def set_upload_limits(self, course_id: int, *, student: int, teacher: int) -> None:
        """Gündəlik yükləmə limitləri (sahib paneli)."""
        with self._lock:
            self._conn.execute(
                "UPDATE courses SET upload_limit_student = ?, upload_limit_teacher = ? WHERE id = ?",
                (student, teacher, course_id),
            )
            self._conn.commit()

    def update_settings(
        self,
        course_id: int,
        *,
        name: str | None = None,
        seat_limit: int | None = None,
        upload_limit_student: int | None = None,
        upload_limit_teacher: int | None = None,
    ) -> None:
        """Yalnız verilən sahələr dəyişir (None = toxunma)."""
        changes = {
            "name": name,
            "seat_limit": seat_limit,
            "upload_limit_student": upload_limit_student,
            "upload_limit_teacher": upload_limit_teacher,
        }
        changes = {k: v for k, v in changes.items() if v is not None}
        if not changes:
            return
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with self._lock:
            self._conn.execute(
                f"UPDATE courses SET {assignments} WHERE id = ?", (*changes.values(), course_id)
            )
            self._conn.commit()

    def regenerate_join_code(self, course_id: int) -> str:
        """Kod kənara sızanda: köhnə kod dərhal işləməz olur."""
        with self._lock:
            code = self._unique_code_locked()
            self._conn.execute("UPDATE courses SET join_code = ? WHERE id = ?", (code, course_id))
            self._conn.commit()
            return code

    def log_owner_action(
        self, *, owner_id: int, course_id: int | None, action: str, details: str,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            self._conn.execute(
                "INSERT INTO owner_audit_log (at, owner_id, course_id, action, details) "
                "VALUES (?, ?, ?, ?, ?)",
                (now.isoformat(), owner_id, course_id, action, details),
            )
            self._conn.commit()

    def list_audit_log(self, limit: int = 100) -> list[dict]:
        """Ən yenisi birinci. Ad sütunları eyni fayldakı cədvəllərdən (JOIN)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT l.id, l.at, l.course_id, c.name AS course_name, l.action, l.details, "
                "u.display_name AS owner_name "
                "FROM owner_audit_log l "
                "LEFT JOIN courses c ON c.id = l.course_id "
                "LEFT JOIN users u ON u.id = l.owner_id "
                "ORDER BY l.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

