"""Lisenziya məntiqi — kursun açıq/bağlı olması tarixdən hesablanır.

Status bazada «expired» kimi YAZILMIR: onu yazan cron işi dayansaydı,
kurslar səssizcə pulsuz qalardı. Ona görə hər sərhəd burada yoxlanır.
"""

from datetime import datetime, timedelta, timezone

import pytest

from server.licensing import course_is_open, days_left

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _course(status, *, trial_ends_at=None, paid_until=None):
    return {
        "status": status,
        "trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
        "paid_until": paid_until.isoformat() if paid_until else None,
    }


class TestCourseIsOpen:
    def test_owner_course_is_always_open(self):
        assert course_is_open(_course("owner"), NOW) is True

    def test_suspended_course_is_closed_even_with_future_payment(self):
        course = _course("suspended", paid_until=NOW + timedelta(days=30))
        assert course_is_open(course, NOW) is False

    def test_trial_open_before_end(self):
        course = _course("trial", trial_ends_at=NOW + timedelta(seconds=1))
        assert course_is_open(course, NOW) is True

    def test_trial_closed_exactly_at_end(self):
        course = _course("trial", trial_ends_at=NOW)
        assert course_is_open(course, NOW) is False

    def test_trial_closed_after_end(self):
        course = _course("trial", trial_ends_at=NOW - timedelta(days=1))
        assert course_is_open(course, NOW) is False

    def test_active_open_before_paid_until(self):
        course = _course("active", paid_until=NOW + timedelta(days=3))
        assert course_is_open(course, NOW) is True

    def test_active_closed_after_paid_until(self):
        course = _course("active", paid_until=NOW - timedelta(seconds=1))
        assert course_is_open(course, NOW) is False

    def test_trial_without_end_date_is_closed(self):
        """Tarixi olmayan sınaq — konfiqurasiya xətasıdır. Təhlükəsiz
        tərəf bağlı olmaqdır, «sonsuz pulsuz» yox."""
        assert course_is_open(_course("trial"), NOW) is False

    def test_active_without_paid_until_is_closed(self):
        assert course_is_open(_course("active"), NOW) is False

    def test_unknown_status_is_closed(self):
        assert course_is_open(_course("expired"), NOW) is False

    def test_missing_course_is_closed(self):
        assert course_is_open(None, NOW) is False

    def test_naive_timestamp_treated_as_utc(self):
        naive = (NOW + timedelta(hours=1)).replace(tzinfo=None)
        course = {"status": "trial", "trial_ends_at": naive.isoformat(), "paid_until": None}
        assert course_is_open(course, NOW) is True


class TestDaysLeft:
    def test_owner_has_no_limit(self):
        assert days_left(_course("owner"), NOW) is None

    def test_suspended_has_zero(self):
        assert days_left(_course("suspended"), NOW) == 0

    @pytest.mark.parametrize(
        "delta, expected",
        [
            (timedelta(days=5), 5),
            (timedelta(days=4, hours=1), 5),  # yarımçıq gün tam sayılır
            (timedelta(hours=1), 1),
            (timedelta(0), 0),
            (timedelta(days=-2), 0),
        ],
    )
    def test_trial_days_rounded_up_and_clamped(self, delta, expected):
        course = _course("trial", trial_ends_at=NOW + delta)
        assert days_left(course, NOW) == expected

    def test_active_uses_paid_until(self):
        course = _course(
            "active",
            trial_ends_at=NOW - timedelta(days=10),
            paid_until=NOW + timedelta(days=20),
        )
        assert days_left(course, NOW) == 20
