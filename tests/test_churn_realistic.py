"""`ml/churn/realistic.py`: pilot üçün real kursa bənzəyən sintetik data (2026-11-17)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

import pytest

from ml.churn import dataset, realistic
from ml.churn.schema import parse_ts, read_tables, write_tables

UTC = timezone.utc
AS_OF = realistic.DEFAULT_AS_OF


@pytest.fixture(scope="module")
def tables():
    return realistic.generate(26, as_of=AS_OF)


def test_same_seed_same_course(tables):
    again = realistic.generate(26, as_of=AS_OF)
    assert again.payment_records == tables.payment_records and again.truth == tables.truth
    assert realistic.generate(27, as_of=AS_OF).payment_records != tables.payment_records


def test_as_of_outside_the_two_school_years_is_rejected():
    with pytest.raises(ValueError):
        realistic.generate(26, as_of=datetime(2026, 3, 1, tzinfo=UTC))


def test_nothing_after_today(tables):
    stamps = [p.paid_at for p in tables.payment_records] + [a.joined_at for a in tables.lesson_attendance] \
        + [m.joined_at for m in tables.chat_members] + [x.starts_at for x in tables.lessons]
    assert max(parse_ts(s) for s in stamps) < AS_OF


def test_size_and_shape(tables):
    s = realistic.summary_line(tables)
    assert s["groups"] == len(realistic.GROUPS)
    assert 150 <= s["students"] <= 230
    assert 70 <= s["active_now"] <= 130
    assert s["partial_payments"] > 0 and s["left_by_reason"]["signal"] > s["left_by_reason"]["sudden"]
    names = [x.display_name for x in tables.students]
    assert len(set(names)) == len(names) and any("ə" in n.lower() for n in names)


def test_no_lessons_on_holidays(tables):
    days = {parse_ts(x.starts_at).date() for x in tables.lessons}
    assert not days & realistic.HOLIDAYS


def test_one_record_per_student_month_and_amount_never_above_fee(tables):
    keys = Counter((p.chat_id, p.student_id, p.month) for p in tables.payment_records)
    assert max(keys.values()) == 1
    fees = {(f.chat_id, f.student_id): f.monthly_amount for f in tables.payment_fees}
    assert all(p.amount <= fees[(p.chat_id, p.student_id)]
               for p in tables.payment_records if (p.chat_id, p.student_id) in fees)


def test_price_rise_only_for_new_students(tables):
    """İl boyu qrupda sentyabr 2026-dan gələn +10 AZN ödəyir, köhnələr köhnə qiymətlə."""
    eng = next(i for i, g in enumerate(realistic.GROUPS, 1) if g.name == "İngilis dili B1")
    joined = {m.user_id: parse_ts(m.joined_at) for m in tables.chat_members if m.chat_id == eng}
    fees = {f.student_id: f.monthly_amount for f in tables.payment_fees if f.chat_id == eng}
    full_new = {fees[s] for s, j in joined.items() if j >= realistic.NEW_YEAR and s in fees}
    full_old = {fees[s] for s, j in joined.items() if j < realistic.NEW_YEAR and s in fees}
    assert 100 in full_new and 90 in full_old and 100 not in full_old


def test_ended_cohorts_are_emptied_and_some_leavers_forgotten(tables):
    ended = {i for i, g in enumerate(realistic.GROUPS, 1) if g.ends and g.ends <= AS_OF}
    assert all(m.removed_at for m in tables.chat_members if m.chat_id in ended)
    left = {x.student_id for x in tables.truth if x.left_at}
    kept = [m for m in tables.chat_members if m.user_id in left and m.chat_id not in ended and not m.removed_at]
    assert kept  # rəhbərin unutduğu getmiş şagird: Kassa «2+ aydır ödəmir» göstərir


def test_churn_is_seasonal_over_seeds():
    """Yanvar-aprel itkisi payız başlanğıcından yüksəkdir (bir neçə seed üzrə, səs-küyə görə)."""
    first, last = datetime(2025, 10, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)
    rate: Counter = Counter()
    total: Counter = Counter()
    for seed in (26, 1, 2):
        for r in dataset.build(realistic.generate(seed, as_of=AS_OF), first, last):
            total[r["snapshot"]] += 1
            rate[r["snapshot"]] += r["churned"]
    autumn = sum(rate[m] for m in ("2025-10-01", "2025-11-01")) / sum(total[m] for m in ("2025-10-01", "2025-11-01"))
    spring = sum(rate[m] for m in ("2026-02-01", "2026-03-01")) / sum(total[m] for m in ("2026-02-01", "2026-03-01"))
    assert spring > autumn
    overall = sum(rate.values()) / sum(total.values())
    assert 0.03 <= overall <= 0.15


def test_dataset_respects_program_end(tables):
    """Bitmiş abituriyent axını iyul kəsiyində yoxdur: proqramın sonu itki deyil."""
    rows = dataset.build(tables, datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 1, tzinfo=UTC))
    ended = {i for i, g in enumerate(realistic.GROUPS, 1) if g.ends and g.ends <= datetime(2026, 7, 31, tzinfo=UTC)}
    assert rows and not {r["chat_id"] for r in rows} & ended


def test_csv_roundtrip(tables, tmp_path):
    write_tables(tables, str(tmp_path))
    back = read_tables(str(tmp_path))
    assert back.chat_members == tables.chat_members and back.programs == tables.programs
    assert back.expenses == tables.expenses and back.students == tables.students
