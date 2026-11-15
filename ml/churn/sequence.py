"""Addım 4: hər şagird üçün son 6 ayın aylıq ardıcıllığı (GRU üçün).

Cədvəl əlamətləri (`dataset.FEATURES_V2`) trendi əl ilə yazılmış fərqlərlə
verir. GRU isə xam aylıq sıranı görür və trendi özü öyrənməlidir. Hər ay üçün:

- `enrolled`: həmin ay şagird artıq kursda idi (əks halda bütün dəyərlər 0);
- `attend`: dərslərə gəlmə payı;
- `hw_done`: tapşırıq etmə payı;
- `hw_score`: etdiyi tapşırıqlarda orta bal payı;
- `paid`: həmin ayın ödənişi `t`-yə qədər gəlib;
- `delay`: ödəniş gecikməsi (gün / 30, 2-də kəsilir; ödənməyibsə `t`-yə qədər).

Leakage: hamısı `dataset.cut(tables, t)`-dən qurulmuş indeksdən hesablanır,
yəni `t`-dən sonrakı heç bir hadisə görünmür (test var). Cari (natamam) ay
ardıcıllığa DAXİL DEYİL: son element `t`-dən əvvəlki tam aydır.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import dataset
from .schema import Tables

MONTHS = 6
STEP_FEATURES = ["enrolled", "attend", "hw_done", "hw_score", "paid", "delay"]


def _month_starts(t: datetime, n: int = MONTHS) -> list[datetime]:
    """`t`-dən əvvəlki `n` tam ayın 1-i, köhnədən yeniyə."""
    out = [(t - timedelta(days=1)).replace(day=1)]
    while len(out) < n:
        out.insert(0, (out[0] - timedelta(days=1)).replace(day=1))
    return out


def _next(m: datetime) -> datetime:
    return (m.replace(day=28) + timedelta(days=4)).replace(day=1)


def _sequence(past: dataset._Index, t: datetime, chat_id: int, student_id: int) -> list[list[float]]:
    joined = past.members[(chat_id, student_id)]
    attended = past.attended[student_id]
    steps = []
    for start in _month_starts(t):
        end = min(_next(start), t)
        if joined >= end:
            steps.append([0.0] * len(STEP_FEATURES))
            continue
        lo = max(start, joined)
        lessons = {lid for lid, ts in past.lessons[chat_id] if lo <= ts < end}
        hw = {hid: qc for hid, due, qc in past.homework[chat_id] if lo <= due < end}
        done = {hid: past.attempts[student_id][hid][0] for hid in hw if hid in past.attempts[student_id]}
        score = sum(sc / hw[hid] for hid, sc in done.items()) / len(done) if done else 0.0
        delay = dataset._month_delay(past, student_id, start, joined, t)
        paid = any(month == dataset.month_key(start) for month, _ in past.payments[student_id])
        steps.append([
            1.0,
            dataset._rate(len(lessons & attended.keys()), len(lessons)),
            dataset._rate(len(done), len(hw)),
            round(score, 4),
            1.0 if paid else 0.0,
            round(min(2.0, (delay or 0.0) / 30), 4),
        ])
    return steps


def sequence(tables: Tables, t: datetime, chat_id: int, student_id: int) -> list[list[float]]:
    """Bir şagird üçün; cədvəli özü kəsir (testlər üçün)."""
    return _sequence(dataset._Index(dataset.cut(tables, t)), t, chat_id, student_id)


def build_sequences(tables: Tables, rows: list[dict]) -> list[list[list[float]]]:
    """`dataset.build` sətirləri ilə EYNİ sırada ardıcıllıqlar."""
    by_snapshot: dict[str, dataset._Index] = {}
    out = []
    for r in rows:
        if r["snapshot"] not in by_snapshot:
            t = datetime.fromisoformat(r["snapshot"]).replace(tzinfo=dataset.UTC)
            by_snapshot[r["snapshot"]] = dataset._Index(dataset.cut(tables, t))
        t = datetime.fromisoformat(r["snapshot"]).replace(tzinfo=dataset.UTC)
        out.append(_sequence(by_snapshot[r["snapshot"]], t, r["chat_id"], r["student_id"]))
    return out
