"""Kurs lisenziyası — kursun açıq/bağlı olması (təmiz funksiyalar).

NİYƏ «BİTİB» STATUSU SAXLANMIR: `expired` yazan cron işi olsaydı, o iş
dayandığı gün (server restart, xəta, unudulmuş timer) kurslar SƏSSİZCƏ
pulsuz qalardı. Tarixdən hesablama heç vaxt «unudulmur» — hər sorğu
cari vaxtı özü müqayisə edir.

NİYƏ ŞÜBHƏLİ HALDA BAĞLI: tarixi olmayan sınaq, naməlum status — bunlar
konfiqurasiya xətasıdır. Xətanın nəticəsi «sonsuz pulsuz» olmamalıdır;
bağlı kurs sahibə dərhal görünür, açıq qalan kurs isə heç vaxt.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

# Statuslar — `courses.status` sütununun mümkün dəyərləri.
STATUS_OWNER = "owner"
STATUS_TRIAL = "trial"
STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"
COURSE_STATUSES = (STATUS_OWNER, STATUS_TRIAL, STATUS_ACTIVE, STATUS_SUSPENDED)

_SECONDS_PER_DAY = 24 * 60 * 60


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    # Saat qurşağı olmayan dəyər UTC sayılır — bazaya hər şey UTC yazılır.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _period_end(course: dict) -> datetime | None:
    """Kursun cari açıq dövrünün sonu (trial → sınaq sonu, active → ödəniş sonu)."""
    if course["status"] == STATUS_TRIAL:
        return _parse(course.get("trial_ends_at"))
    if course["status"] == STATUS_ACTIVE:
        return _parse(course.get("paid_until"))
    return None


def course_is_open(course: dict | None, now: datetime) -> bool:
    if course is None:
        return False
    status = course.get("status")
    if status == STATUS_OWNER:
        return True
    if status not in (STATUS_TRIAL, STATUS_ACTIVE):
        return False
    end = _period_end(course)
    return end is not None and now < end


def days_left(course: dict, now: datetime) -> int | None:
    """Qalan gün sayı (yarımçıq gün tam sayılır). `owner` üçün `None` —
    müddət yoxdur. Bağlı kurs üçün 0."""
    if course["status"] == STATUS_OWNER:
        return None
    end = _period_end(course)
    if end is None:
        return 0
    seconds = (end - now).total_seconds()
    if seconds <= 0:
        return 0
    return math.ceil(seconds / _SECONDS_PER_DAY)
