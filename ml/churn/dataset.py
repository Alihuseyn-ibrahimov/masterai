"""Kəsik (snapshot) × şagird sətirləri: əlamətlər (yalnız keçmişdən) + hədəf (gələcəkdən).

Tərif (spec §Hədəf):
- Kəsik `t` = ayın 1-i, 00:00 UTC.
- Uyğun şagird: `joined_at < t`, son 45 gündə fəaliyyəti var, proqram bu ay davam edir.
- `churned = 1`: `[t, t+30 gün)` pəncərəsində bu ay üçün ödəniş YOXDUR və heç bir
  fəaliyyət (dərs, tapşırıq) YOXDUR. Dərsə gəlib ödəməyən = borclu, `churned = 0`.

Leakage qoruması: `features()` cədvəlləri əvvəlcə `cut(tables, t)` ilə kəsir,
yəni `t`-dən sonrakı heç bir hadisə əlamətə düşə bilməz. Ödəniş `month`-a görə yox,
`paid_at`-a görə kəsilir (oktyabrın pulu noyabrın 10-da gəlibsə, noyabrın 1-də YOXDUR).
`tables.truth` heç vaxt oxunmur.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .schema import Tables, parse_ts
from .synth import program_end

UTC = timezone.utc
LABEL_WINDOW = timedelta(days=30)
ACTIVE_LOOKBACK = timedelta(days=45)

FEATURES = [
    "tenure_days",
    "monthly_fee",
    "attend_rate_30d",
    "attend_rate_prev_30d",
    "hw_done_rate_30d",
    "hw_score_30d",
    "days_since_activity",
    "prev_month_unpaid",
    "prev_month_delay_days",
]

# Addım 4 (6-cı ay #44, feature engineering): «son 30 gün» kəsikləri trendi görmür.
# Bu əlamətlər eyni `cut` edilmiş cədvəldən hesablanır, yəni eyni leakage qorumasındadır.
ENGINEERED = [
    "attend_trend",            # son 30 gün - əvvəlki 30 gün davamiyyət
    "attend_rate_14d",         # daha qısa pəncərə: sönmə tez görünür
    "missed_lessons_streak",   # sonuncu dərsdən geriyə ardıcıl buraxılan dərslər
    "days_since_lesson",       # son DƏRSƏ gəlişdən keçən gün (ödəniş fəaliyyət sayılmır)
    "days_since_homework",     # son tapşırıqdan keçən gün
    "hw_done_trend",           # tapşırıq etmə payı: son 30 - əvvəlki 30
    "hw_score_trend",          # bal: son 30 - əvvəlki 30 (etdiyi tapşırıqlar üzrə)
    "activity_14d",            # son 14 gündə hadisə sayı (dərs + tapşırıq)
    "activity_ratio",          # son 14 gün / əvvəlki 14 gün hadisə (sönmə sürəti)
    "late_months_3m",          # son 3 ayda gec (>7 gün) və ya heç ödənməmiş aylar
    "delay_trend",             # keçən ayın gecikməsi - ondan əvvəlki ayın gecikməsi
]
FEATURES_V2 = FEATURES + ENGINEERED
LATE_DAYS = 7


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def snapshot_dates(first: datetime, last: datetime) -> list[datetime]:
    """`first`-dən `last`-a qədər (daxil) hər ayın 1-i."""
    out, cur = [], first.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cur <= last:
        out.append(cur)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def cut(tables: Tables, t: datetime) -> Tables:
    """`t`-dən ƏVVƏLKİ hadisələr. Əlamətlər yalnız bunun üzərində hesablanır."""

    def before(ts: str | None) -> bool:
        return ts is not None and parse_ts(ts) < t

    return replace(
        tables,
        chat_members=[m for m in tables.chat_members if before(m.joined_at)],
        payment_records=[p for p in tables.payment_records if before(p.paid_at)],
        lessons=[x for x in tables.lessons if before(x.starts_at)],
        lesson_attendance=[a for a in tables.lesson_attendance if before(a.joined_at)],
        homework_assignments=[h for h in tables.homework_assignments if before(h.due_date)],
        homework_attempts=[a for a in tables.homework_attempts if before(a.completed_at)],
        truth=[],
    )


class _Index:
    """Cədvəlləri şagird/qrup üzrə qruplaşdırır ki, hər sətir bütün cədvəli gəzməsin."""

    def __init__(self, tables: Tables) -> None:
        self.tables = tables
        self.members = {(m.chat_id, m.user_id): parse_ts(m.joined_at) for m in tables.chat_members}
        self.fees = {(f.chat_id, f.student_id): f.monthly_amount for f in tables.payment_fees}
        self.lessons: dict[int, list[tuple[int, datetime]]] = defaultdict(list)
        for x in tables.lessons:
            self.lessons[x.chat_id].append((x.id, parse_ts(x.starts_at)))
        self.homework: dict[int, list[tuple[int, datetime, int]]] = defaultdict(list)
        for h in tables.homework_assignments:
            self.homework[h.chat_id].append((h.id, parse_ts(h.due_date), h.question_count))
        self.attended: dict[int, dict[int, datetime]] = defaultdict(dict)
        for a in tables.lesson_attendance:
            self.attended[a.user_id][a.lesson_id] = parse_ts(a.joined_at)
        self.attempts: dict[int, dict[int, tuple[int, datetime]]] = defaultdict(dict)
        for a in tables.homework_attempts:
            if a.completed_at:
                self.attempts[a.student_id][a.assignment_id] = (a.score, parse_ts(a.completed_at))
        self.payments: dict[int, list[tuple[str, datetime]]] = defaultdict(list)
        for p in tables.payment_records:
            self.payments[p.student_id].append((p.month, parse_ts(p.paid_at)))

    def activity(self, student_id: int) -> list[datetime]:
        times = list(self.attended[student_id].values())
        times += [ts for _, ts in self.attempts[student_id].values()]
        times += [ts for _, ts in self.payments[student_id]]
        return times


def _rate(numer: int, denom: int) -> float:
    return round(numer / denom, 4) if denom else 0.0


def features(tables: Tables, t: datetime, chat_id: int, student_id: int) -> dict:
    """Bir şagirdin `t` anındakı əlamətləri. Cədvəli özü kəsir: gələcək görünmür."""
    return _features(_Index(cut(tables, t)), t, chat_id, student_id)


def _features(past: _Index, t: datetime, chat_id: int, student_id: int) -> dict:
    """`past` MÜTLƏQ `cut(tables, t)`-dən qurulmalıdır (build və features bunu edir)."""
    joined = past.members[(chat_id, student_id)]
    lo30, lo60 = t - timedelta(days=30), t - timedelta(days=60)

    def attend_rate(lo: datetime, hi: datetime) -> float:
        ids = {lid for lid, ts in past.lessons[chat_id] if lo <= ts < hi}
        return _rate(len(ids & past.attended[student_id].keys()), len(ids))

    hw = {hid: qc for hid, due, qc in past.homework[chat_id] if lo30 <= due < t}
    done = {hid: past.attempts[student_id][hid][0] for hid in hw if hid in past.attempts[student_id]}
    score = sum(sc / hw[hid] for hid, sc in done.items()) / len(done) if done else 0.0

    activity = past.activity(student_id)
    last = max(activity) if activity else joined

    prev_month_start = (t - timedelta(days=1)).replace(day=1)
    anchor = max(prev_month_start, joined)
    prev_paid = [ts for month, ts in past.payments[student_id] if month == month_key(prev_month_start)]
    if prev_paid:
        delay = max(0.0, (min(prev_paid) - anchor).total_seconds() / 86400)
    else:
        delay = max(0.0, (t - anchor).total_seconds() / 86400)  # hələ ödənməyib: indiyə qədər

    base = {
        "tenure_days": round((t - joined).total_seconds() / 86400, 1),
        "monthly_fee": past.fees.get((chat_id, student_id), 0),
        "attend_rate_30d": attend_rate(lo30, t),
        "attend_rate_prev_30d": attend_rate(lo60, lo30),
        "hw_done_rate_30d": _rate(len(done), len(hw)),
        "hw_score_30d": round(score, 4),
        "days_since_activity": round((t - last).total_seconds() / 86400, 1),
        "prev_month_unpaid": 0 if prev_paid else 1,
        "prev_month_delay_days": round(delay, 1),
    }
    base.update(_engineered(past, t, chat_id, student_id, joined, base))
    return base


def _days(a: datetime, b: datetime) -> float:
    return round((a - b).total_seconds() / 86400, 1)


def _month_delay(past: _Index, student_id: int, month_start: datetime, joined: datetime,
                 t: datetime) -> float | None:
    """Ayın ödənişi ayın əvvəlindən (və ya qoşulmadan) neçə gün sonra gəlib; `t`-yə qədər
    gəlməyibsə indiyə qədərki gün. Şagird həmin ayda hələ yox idisə `None`."""
    nxt = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    if joined >= nxt:
        return None
    anchor = max(month_start, joined)
    paid = [ts for month, ts in past.payments[student_id] if month == month_key(month_start)]
    end = min(paid) if paid else t
    return max(0.0, (end - anchor).total_seconds() / 86400)


def _engineered(past: _Index, t: datetime, chat_id: int, student_id: int, joined: datetime,
                base: dict) -> dict:
    lo14, lo28, lo30, lo60 = (t - timedelta(days=d) for d in (14, 28, 30, 60))
    attended = past.attended[student_id]

    lessons = sorted(ts_id for ts_id in ((ts, lid) for lid, ts in past.lessons[chat_id]) if ts_id[0] < t)
    ids14 = {lid for ts, lid in lessons if ts >= lo14}
    streak = 0
    for ts, lid in reversed(lessons):
        if ts < joined:
            break
        if lid in attended:
            break
        streak += 1

    def hw_window(lo: datetime, hi: datetime) -> tuple[float, float | None]:
        hw = {hid: qc for hid, due, qc in past.homework[chat_id] if lo <= due < hi and due >= joined}
        done = {hid: past.attempts[student_id][hid][0] for hid in hw if hid in past.attempts[student_id]}
        score = sum(sc / hw[hid] for hid, sc in done.items()) / len(done) if done else None
        return _rate(len(done), len(hw)), score

    done30, score30 = hw_window(lo30, t)
    done_prev, score_prev = hw_window(lo60, lo30)

    events = list(attended.values()) + [ts for _, ts in past.attempts[student_id].values()]
    recent = sum(1 for ts in events if ts >= lo14)
    before = sum(1 for ts in events if lo28 <= ts < lo14)
    lesson_times = list(attended.values())
    hw_times = [ts for _, ts in past.attempts[student_id].values()]

    prev_start = (t - timedelta(days=1)).replace(day=1)
    months = [prev_start]
    for _ in range(2):
        months.append((months[-1] - timedelta(days=1)).replace(day=1))
    delays = [_month_delay(past, student_id, m, joined, t) for m in months]
    late = sum(1 for d in delays if d is not None and d > LATE_DAYS)
    trend = (delays[0] - delays[1]) if delays[0] is not None and delays[1] is not None else 0.0

    return {
        "attend_trend": round(base["attend_rate_30d"] - base["attend_rate_prev_30d"], 4),
        "attend_rate_14d": _rate(len(ids14 & attended.keys()), len(ids14)),
        "missed_lessons_streak": streak,
        "days_since_lesson": _days(t, max(lesson_times) if lesson_times else joined),
        "days_since_homework": _days(t, max(hw_times) if hw_times else joined),
        "hw_done_trend": round(done30 - done_prev, 4),
        "hw_score_trend": round(score30 - score_prev, 4) if score30 is not None and score_prev is not None else 0.0,
        "activity_14d": recent,
        "activity_ratio": round(recent / before, 4) if before else (1.0 if recent else 0.0),
        "late_months_3m": late,
        "delay_trend": round(trend, 1),
    }


def label(tables: Tables, t: datetime, student_id: int) -> int:
    """1 = `[t, t+30)` ərzində bu ayın ödənişi də, fəaliyyət də yoxdur (şagird getdi)."""
    return _label(_Index(tables), t, student_id)


def _label(full: _Index, t: datetime, student_id: int) -> int:
    hi = t + LABEL_WINDOW
    this_month = month_key(t)
    if any(month == this_month and ts < hi for month, ts in full.payments[student_id]):
        return 0
    return 0 if any(t <= ts < hi for ts in full.activity(student_id)) else 1


def eligible(tables: Tables, t: datetime) -> list[tuple[int, int]]:
    """(chat_id, student_id) cütləri: kəsik anında kursda sayılan şagirdlər."""
    return _eligible(tables, _Index(cut(tables, t)), t)


def _eligible(tables: Tables, past: _Index, t: datetime) -> list[tuple[int, int]]:
    programs = {p.chat_id: p for p in tables.programs}
    out = []
    for (chat_id, student_id), joined in past.members.items():
        program = programs.get(chat_id)
        # Proqram pəncərə bitmədən başa çatırsa, getmək itki deyil: kəsik atılır.
        if program is not None and program_end(program) < t + LABEL_WINDOW:
            continue
        recent = any(ts >= t - ACTIVE_LOOKBACK for ts in past.activity(student_id))
        if recent or joined >= t - ACTIVE_LOOKBACK:
            out.append((chat_id, student_id))
    return sorted(out)


def build(tables: Tables, first: datetime, last: datetime) -> list[dict]:
    """Bütün kəsiklər üçün sətirlər: snapshot, chat_id, student_id, program, əlamətlər, churned."""
    kinds = {p.chat_id: p.kind for p in tables.programs}
    full = _Index(tables)
    rows = []
    for t in snapshot_dates(first, last):
        past = _Index(cut(tables, t))
        for chat_id, student_id in _eligible(tables, past, t):
            row = {"snapshot": t.date().isoformat(), "chat_id": chat_id, "student_id": student_id,
                   "program": kinds.get(chat_id, "")}
            row.update(_features(past, t, chat_id, student_id))
            row["churned"] = _label(full, t, student_id)
            rows.append(row)
    return rows


def time_split(rows: list[dict], test_from: str) -> tuple[list[dict], list[dict]]:
    """Vaxta görə bölgü (spec, leakage §4): `test_from` (YYYY-AA-GG) və sonrası test."""
    train = [r for r in rows if r["snapshot"] < test_from]
    test = [r for r in rows if r["snapshot"] >= test_from]
    return train, test


def write_csv(rows: list[dict], path: str) -> None:
    if not rows:
        raise ValueError("Dataset boşdur")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
