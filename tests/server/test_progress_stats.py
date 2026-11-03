"""İnkişaf qrafikləri (Faza 3 PR 1, 2026-11-03) — `server/progress_stats.py`."""

import pytest

from server.lesson_store import LessonStore
from server.models import HistoryEntry
from server.progress_stats import attendance_stats, attendance_stats_for_users, subject_percent, weekly_percent


def _entry(subject, score, total, date, kind="live"):
    return HistoryEntry(kind=kind, subject=subject, title="t", score=score, total_questions=total, date=date)


class TestWeeklyPercent:
    def test_empty(self):
        assert weekly_percent([]) == []

    def test_groups_same_iso_week(self):
        # 2026-11-02 (Monday) və 2026-11-04 (Wednesday) eyni həftədədir.
        entries = [
            _entry("fizika", 1, 2, "2026-11-02T10:00:00+00:00"),
            _entry("fizika", 2, 2, "2026-11-04T10:00:00+00:00"),
        ]
        result = weekly_percent(entries)
        assert len(result) == 1
        assert result[0] == {"week_start": "2026-11-02", "correct": 3, "total": 4, "percent": 75}

    def test_separates_different_weeks_sorted_ascending(self):
        entries = [
            _entry("fizika", 1, 1, "2026-11-09T10:00:00+00:00"),
            _entry("fizika", 0, 1, "2026-11-02T10:00:00+00:00"),
        ]
        result = weekly_percent(entries)
        assert [r["week_start"] for r in result] == ["2026-11-02", "2026-11-09"]


class TestSubjectPercent:
    def test_empty(self):
        assert subject_percent([]) == []

    def test_groups_by_subject_sorted_weakest_first(self):
        entries = [
            _entry("fizika", 0, 2, "2026-11-02T10:00:00+00:00"),
            _entry("kimya", 2, 2, "2026-11-02T10:00:00+00:00"),
        ]
        result = subject_percent(entries)
        assert [r["subject"] for r in result] == ["fizika", "kimya"]
        assert result[0]["percent"] == 0
        assert result[1]["percent"] == 100

    def test_combines_multiple_entries_same_subject(self):
        entries = [
            _entry("fizika", 1, 2, "2026-11-02T10:00:00+00:00"),
            _entry("fizika", 1, 2, "2026-11-09T10:00:00+00:00"),
        ]
        result = subject_percent(entries)
        assert result == [{"subject": "fizika", "correct": 2, "total": 4, "percent": 50}]


@pytest.fixture
def lessons(tmp_path):
    return LessonStore(path=str(tmp_path / "lessons.db"))


def _ended_lesson(lessons, chat_id=1):
    lesson = lessons.create(
        chat_id, course_id=None, created_by=1, title="Dərs", description="",
        starts_at="2026-11-01T10:00:00+00:00", duration_min=60, mode="offline",
    )
    lessons.set_status(lesson["id"], "ended")
    return lesson


class TestAttendanceStats:
    def test_no_lessons_gives_none_percent(self, lessons):
        assert attendance_stats(5, [1], lessons) == {"attended": 0, "total": 0, "percent": None}

    def test_scheduled_lesson_not_counted(self, lessons):
        lessons.create(
            1, course_id=None, created_by=1, title="Dərs", description="",
            starts_at="2099-01-01T10:00:00+00:00", duration_min=60, mode="offline",
        )
        assert attendance_stats(5, [1], lessons) == {"attended": 0, "total": 0, "percent": None}

    def test_attended_ended_lesson(self, lessons):
        lesson = _ended_lesson(lessons)
        lessons.mark_attendance(lesson["id"], 5, "qr")
        assert attendance_stats(5, [1], lessons) == {"attended": 1, "total": 1, "percent": 100}

    def test_missed_ended_lesson(self, lessons):
        _ended_lesson(lessons)
        assert attendance_stats(5, [1], lessons) == {"attended": 0, "total": 1, "percent": 0}

    def test_for_users_weights_by_lesson_times_student_count(self, lessons):
        lesson = _ended_lesson(lessons)
        lessons.mark_attendance(lesson["id"], 5, "qr")
        # 1 dərs x 2 tələbə = məxrəc 2, biri gəlib.
        result = attendance_stats_for_users([5, 6], [1], lessons)
        assert result == {"attended": 1, "total": 2, "percent": 50}

    def test_for_users_empty_list_gives_none(self, lessons):
        _ended_lesson(lessons)
        assert attendance_stats_for_users([], [1], lessons) == {"attended": 0, "total": 0, "percent": None}
