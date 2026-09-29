"""Qapalı qeydiyyatın store qatı: yer limiti və müəllim dəvəti.

Yer limiti «say + yaz» BİR tranzaksiyada olmalıdır: iki tələbə son yerə
eyni anda yazılanda ikisi də keçməməlidir. Müəllim dəvəti birdəfəlikdir
və yalnız hash kimi saxlanır (baza sızsa link işlənə bilməsin).
"""

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from server.course_store import DEFAULT_COURSE_ID
from server.user_store import CourseFull, DuplicateEmail, InvalidInvite, UserStore

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def users():
    return UserStore(":memory:")


def _course(users, seat_limit):
    return users.courses.create("English", "english", trial_days=30, seat_limit=seat_limit, now=NOW)


class TestDefaultCourseCode:
    def test_default_course_gets_join_code(self, users):
        """Qeydiyyat kodla olanda kurs #1-in (mövcud imtahan kursu) da
        kodu olmalıdır - əks halda ora heç kim qoşula bilməz."""
        code = users.courses.get(DEFAULT_COURSE_ID)["join_code"]
        assert code and len(code) == 6

    def test_legacy_course_row_without_code_is_backfilled(self, tmp_path):
        path = str(tmp_path / "users.db")
        UserStore(path)
        conn = sqlite3.connect(path)
        conn.execute("UPDATE courses SET join_code = NULL WHERE id = 1")
        conn.commit()
        conn.close()
        assert UserStore(path).courses.get(DEFAULT_COURSE_ID)["join_code"]


class TestSeatLimit:
    def test_student_created_under_limit(self, users):
        course = _course(users, 2)
        user = users.create_student("a@x.az", "h", "A", course_id=course["id"])
        assert user["course_id"] == course["id"]
        assert user["is_teacher"] == 0

    def test_full_course_rejects(self, users):
        course = _course(users, 1)
        users.create_student("a@x.az", "h", "A", course_id=course["id"])
        with pytest.raises(CourseFull):
            users.create_student("b@x.az", "h", "B", course_id=course["id"])
        assert users.get_by_email("b@x.az") is None

    def test_inactive_student_frees_seat(self, users):
        course = _course(users, 1)
        first = users.create_student("a@x.az", "h", "A", course_id=course["id"])
        users.set_active(first["id"], False)
        users.create_student("b@x.az", "h", "B", course_id=course["id"])

    def test_teachers_do_not_use_seats(self, users):
        course = _course(users, 1)
        teacher = users.create("t@x.az", "h", "T", course_id=course["id"])
        users.set_teacher(teacher["id"], True)
        users.create_student("a@x.az", "h", "A", course_id=course["id"])

    def test_no_limit_means_unlimited(self, users):
        for i in range(5):
            users.create_student(f"s{i}@x.az", "h", "S", course_id=DEFAULT_COURSE_ID)

    def test_seats_counted_per_course(self, users):
        a = _course(users, 1)
        b = _course(users, 1)
        users.create_student("a@x.az", "h", "A", course_id=a["id"])
        users.create_student("b@x.az", "h", "B", course_id=b["id"])

    def test_count_active_students(self, users):
        course = _course(users, 5)
        users.create_student("a@x.az", "h", "A", course_id=course["id"])
        second = users.create_student("b@x.az", "h", "B", course_id=course["id"])
        users.set_active(second["id"], False)
        assert users.count_active_students(course["id"]) == 1

    def test_duplicate_email_still_raises(self, users):
        course = _course(users, 5)
        users.create_student("a@x.az", "h", "A", course_id=course["id"])
        with pytest.raises(DuplicateEmail):
            users.create_student("A@x.az", "h", "A2", course_id=course["id"])

    def test_concurrent_last_seat_only_one_wins(self, tmp_path):
        """İki AYRI bağlantı (iki proses kimi) son yer uğrunda yarışır."""
        path = str(tmp_path / "users.db")
        first_store = UserStore(path)
        course = _course(first_store, 1)
        stores = [first_store, UserStore(path)]
        barrier = threading.Barrier(2)
        results = []

        def attempt(i):
            barrier.wait()
            try:
                stores[i].create_student(f"s{i}@x.az", "h", "S", course_id=course["id"])
                results.append("ok")
            except CourseFull:
                results.append("full")

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == ["full", "ok"]
        assert first_store.count_active_students(course["id"]) == 1


class TestTeacherInvites:
    def test_invite_creates_teacher_in_course(self, users):
        course = _course(users, 5)
        token = users.courses.create_teacher_invite(course["id"], created_by=1, now=NOW)
        teacher = users.create_teacher_from_invite("t@x.az", "h", "T", token, now=NOW)
        assert teacher["is_teacher"] == 1
        assert teacher["course_id"] == course["id"]

    def test_token_is_stored_only_as_hash(self, tmp_path):
        path = str(tmp_path / "users.db")
        users = UserStore(path)
        course = _course(users, 5)
        token = users.courses.create_teacher_invite(course["id"], created_by=1, now=NOW)
        raw = sqlite3.connect(path).execute("SELECT * FROM teacher_invites").fetchall()
        assert token not in repr(raw)

    def test_invite_is_single_use(self, users):
        course = _course(users, 5)
        token = users.courses.create_teacher_invite(course["id"], created_by=1, now=NOW)
        users.create_teacher_from_invite("t@x.az", "h", "T", token, now=NOW)
        with pytest.raises(InvalidInvite):
            users.create_teacher_from_invite("t2@x.az", "h", "T2", token, now=NOW)

    def test_invite_expires_after_seven_days(self, users):
        course = _course(users, 5)
        token = users.courses.create_teacher_invite(course["id"], created_by=1, now=NOW)
        later = NOW + timedelta(days=7, seconds=1)
        with pytest.raises(InvalidInvite):
            users.create_teacher_from_invite("t@x.az", "h", "T", token, now=later)

    def test_unknown_invite(self, users):
        with pytest.raises(InvalidInvite):
            users.create_teacher_from_invite("t@x.az", "h", "T", "uydurma", now=NOW)
        with pytest.raises(InvalidInvite):
            users.create_teacher_from_invite("t@x.az", "h", "T", "", now=NOW)

    def test_duplicate_email_does_not_burn_invite(self, users):
        """E-poçt artıq varsa dəvət İSTİFADƏ OLUNMUŞ sayılmamalıdır -
        müəllim başqa e-poçtla yenidən cəhd edə bilməlidir."""
        course = _course(users, 5)
        users.create("t@x.az", "h", "Köhnə")
        token = users.courses.create_teacher_invite(course["id"], created_by=1, now=NOW)
        with pytest.raises(DuplicateEmail):
            users.create_teacher_from_invite("t@x.az", "h", "T", token, now=NOW)
        teacher = users.create_teacher_from_invite("yeni@x.az", "h", "T", token, now=NOW)
        assert teacher["is_teacher"] == 1

    def test_teacher_invite_ignores_seat_limit(self, users):
        course = _course(users, 1)
        users.create_student("a@x.az", "h", "A", course_id=course["id"])
        token = users.courses.create_teacher_invite(course["id"], created_by=1, now=NOW)
        users.create_teacher_from_invite("t@x.az", "h", "T", token, now=NOW)
