"""Kurs cədvəli və mövcud istifadəçilərin kurs #1-ə miqrasiyası.

Ən vacib zəmanət: köhnə baza (kurs anlayışından əvvəlki) açılanda
mövcud istifadəçilər SƏSSİZCƏ kurs #1-ə (müddətsiz `owner`) düşür —
Amil və digərləri üçün heç nə dəyişmir.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from server.course_store import DEFAULT_COURSE_ID, CourseStore, UnknownProfile
from server.licensing import course_is_open
from server.user_store import UserStore

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "users.db")


@pytest.fixture
def courses(db_path):
    UserStore(db_path)  # app.py-dəki sıra: əvvəl istifadəçilər
    return CourseStore(db_path)


def _make_legacy_db(path):
    """Kurslardan əvvəlki sxem: `is_teacher`/`is_admin` var, kurs yoxdur."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            phone         TEXT UNIQUE,
            display_name  TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            is_teacher    INTEGER NOT NULL DEFAULT 0,
            is_admin      INTEGER NOT NULL DEFAULT 0
        );
        INSERT INTO users (email, password_hash, display_name, created_at, is_teacher, is_admin)
        VALUES ('amil@example.az', 'h1', 'Amil', '2026-09-01T00:00:00+00:00', 1, 1),
               ('telebe@example.az', 'h2', 'Tələbə', '2026-09-02T00:00:00+00:00', 0, 0);
        """
    )
    conn.commit()
    conn.close()


class TestMigration:
    def test_legacy_users_move_to_default_course(self, db_path):
        _make_legacy_db(db_path)
        users = UserStore(db_path)

        amil = users.get_by_email("amil@example.az")
        student = users.get_by_email("telebe@example.az")
        assert amil["course_id"] == DEFAULT_COURSE_ID
        assert student["course_id"] == DEFAULT_COURSE_ID
        assert amil["is_active"] == 1
        assert amil["is_platform_owner"] == 0
        # Mövcud rollar toxunulmaz qalır
        assert amil["is_teacher"] == 1 and amil["is_admin"] == 1

    def test_default_course_is_owner_exam_prep_and_always_open(self, db_path):
        _make_legacy_db(db_path)
        UserStore(db_path)
        course = CourseStore(db_path).get(DEFAULT_COURSE_ID)

        assert course["status"] == "owner"
        assert course["profile"] == "exam_prep"
        assert course["seat_limit"] is None
        assert course_is_open(course, NOW + timedelta(days=3650))

    def test_migration_is_idempotent(self, db_path):
        _make_legacy_db(db_path)
        UserStore(db_path)
        UserStore(db_path)
        CourseStore(db_path)

        assert len(CourseStore(db_path).list_all()) == 1

    def test_course_store_alone_on_fresh_file(self, db_path):
        """CourseStore istifadəçi cədvəlindən əvvəl açılsa da çökməməlidir."""
        store = CourseStore(db_path)
        assert store.get(DEFAULT_COURSE_ID)["status"] == "owner"


class TestCreate:
    def test_trial_course_ends_after_trial_days(self, courses):
        course = courses.create("English Club", "english", trial_days=30, seat_limit=25, now=NOW)

        assert course["id"] != DEFAULT_COURSE_ID
        assert course["status"] == "trial"
        assert course["profile"] == "english"
        assert course["seat_limit"] == 25
        ends = datetime.fromisoformat(course["trial_ends_at"])
        assert ends == NOW + timedelta(days=30)
        assert course["paid_until"] is None
        assert course["upload_limit_student"] == 5
        assert course["upload_limit_teacher"] == 30

    def test_join_code_generated_and_unique(self, courses):
        a = courses.create("A", "english", trial_days=30, seat_limit=10, now=NOW)
        b = courses.create("B", "english", trial_days=30, seat_limit=10, now=NOW)
        assert len(a["join_code"]) == 6
        assert a["join_code"] != b["join_code"]

    def test_unknown_profile_rejected(self, courses):
        with pytest.raises(UnknownProfile):
            courses.create("X", "math", trial_days=30, seat_limit=10, now=NOW)


class TestLookup:
    def test_get_by_join_code_normalizes_input(self, courses):
        course = courses.create("A", "english", trial_days=30, seat_limit=10, now=NOW)
        code = course["join_code"]
        messy = f" {code[:3].lower()}-{code[3:].lower()} "
        assert courses.get_by_join_code(messy)["id"] == course["id"]

    def test_get_by_join_code_unknown_is_none(self, courses):
        assert courses.get_by_join_code("ZZZZZZ") is None
        assert courses.get_by_join_code("") is None
        assert courses.get_by_join_code(None) is None

    def test_get_missing_is_none(self, courses):
        assert courses.get(999) is None

    def test_set_status(self, courses):
        course = courses.create("A", "english", trial_days=30, seat_limit=10, now=NOW)
        courses.set_status(course["id"], "suspended")
        assert courses.get(course["id"])["status"] == "suspended"

    def test_set_status_rejects_unknown(self, courses):
        course = courses.create("A", "english", trial_days=30, seat_limit=10, now=NOW)
        with pytest.raises(ValueError):
            courses.set_status(course["id"], "expired")


class TestUserCourseFields:
    def test_new_user_gets_default_course(self, db_path):
        users = UserStore(db_path)
        user = users.create("yeni@example.az", "h", "Yeni")
        assert user["course_id"] == DEFAULT_COURSE_ID
        assert user["is_active"] == 1
        assert user["is_platform_owner"] == 0

    def test_new_user_in_given_course(self, db_path):
        users = UserStore(db_path)
        course = CourseStore(db_path).create("A", "english", trial_days=30, seat_limit=10, now=NOW)
        user = users.create("yeni@example.az", "h", "Yeni", course_id=course["id"])
        assert user["course_id"] == course["id"]

    def test_set_active_and_platform_owner(self, db_path):
        users = UserStore(db_path)
        user = users.create("yeni@example.az", "h", "Yeni")
        users.set_active(user["id"], False)
        users.set_platform_owner(user["id"], True)
        fresh = users.get_by_id(user["id"])
        assert fresh["is_active"] == 0
        assert fresh["is_platform_owner"] == 1


def test_user_store_courses_share_in_memory_db():
    """`:memory:` bazada ayrı bağlantı ayrı baza olardı — kurs görünməzdi."""
    users = UserStore(":memory:")
    course = users.courses.create("A", "english", trial_days=30, seat_limit=10, now=NOW)
    user = users.create("a@example.az", "h", "A", course_id=course["id"])
    assert users.courses.get(user["course_id"])["name"] == "A"
