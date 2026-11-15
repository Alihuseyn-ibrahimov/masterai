"""Kurs Kassası, addım 1: sintetik generator, hədəf tərifi və leakage qoruması.

Spec: docs/superpowers/specs/2026-11-15-kurs-kassasi-design.md
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ml.churn import dataset, synth
from ml.churn.__main__ import main
from ml.churn.schema import (
    Attempt,
    Attendance,
    ChatMember,
    Lesson,
    PaymentFee,
    PaymentRecord,
    Program,
    Tables,
    iso,
    parse_ts,
    read_tables,
    write_tables,
)

UTC = timezone.utc
FIRST = datetime(2025, 10, 1, tzinfo=UTC)
LAST = datetime(2026, 6, 1, tzinfo=UTC)
NOV = datetime(2025, 11, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def tables() -> Tables:
    return synth.generate(n_students=300, seed=11)


@pytest.fixture(scope="module")
def rows(tables) -> list[dict]:
    return dataset.build(tables, FIRST, LAST)


def _d(*args) -> str:
    return iso(datetime(*args, tzinfo=UTC))


def _tiny(**extra) -> Tables:
    """Bir qrup, bir şagird: əl ilə qurulmuş hallar üçün."""
    t = Tables(
        programs=[Program(1, "ingilis", 70, None)],
        chat_members=[ChatMember(1, 7, _d(2025, 9, 3))],
        payment_fees=[PaymentFee(1, 7, 70)],
        lessons=[Lesson(1, 1, _d(2025, 10, 14, 10)), Lesson(2, 1, _d(2025, 11, 11, 10))],
    )
    for key, value in extra.items():
        setattr(t, key, value)
    return t


# ---------- generator ----------

def test_same_seed_same_data():
    assert synth.generate(120, seed=3) == synth.generate(120, seed=3)
    assert synth.generate(120, seed=3) != synth.generate(120, seed=4)


def test_monthly_churn_in_realistic_range(rows):
    total = Counter(r["snapshot"] for r in rows)
    churned = Counter(r["snapshot"] for r in rows if r["churned"])
    overall = sum(churned.values()) / len(rows)
    assert 0.04 <= overall <= 0.12, overall
    for month, n in total.items():
        assert churned[month] / n <= 0.2, month


def test_debtors_exist_and_are_not_churn(rows):
    # Borclu, amma kursda qalan şagirdlər olmalıdır: panelin ayrıca «borc» sualı budur.
    debtors = [r for r in rows if r["prev_month_unpaid"] and not r["churned"]]
    assert len(debtors) / len(rows) > 0.03


def test_no_events_after_student_left(tables):
    left = {x.student_id: parse_ts(x.left_at) for x in tables.truth if x.left_at}
    assert left, "generator heç kimi getdirmədi"
    for a in tables.lesson_attendance:
        assert a.user_id not in left or parse_ts(a.joined_at) < left[a.user_id]
    for p in tables.payment_records:
        assert p.student_id not in left or parse_ts(p.paid_at) < left[p.student_id]
    for a in tables.homework_attempts:
        assert a.student_id not in left or parse_ts(a.completed_at) < left[a.student_id]


def test_both_leave_reasons_present(tables):
    reasons = Counter(x.left_reason for x in tables.truth if x.left_reason)
    assert reasons["signal"] > reasons["sudden"] > 0


def test_program_end_stops_lessons_and_snapshots(tables, rows):
    magistr = next(p for p in tables.programs if p.kind == "magistr")
    end = synth.program_end(magistr)
    assert all(parse_ts(x.starts_at) < end for x in tables.lessons if x.chat_id == magistr.chat_id)
    # Mayda bitən proqramın iyun kəsiyi yoxdur: proqramın bitməsi itki sayılmır.
    assert not [r for r in rows if r["program"] == "magistr" and r["snapshot"] >= "2026-06-01"]


def test_churned_students_show_signal_on_average(rows):
    churn = [r for r in rows if r["churned"]]
    stay = [r for r in rows if not r["churned"]]
    mean = lambda xs, k: sum(x[k] for x in xs) / len(xs)  # noqa: E731
    assert mean(churn, "attend_rate_30d") < mean(stay, "attend_rate_30d")
    assert mean(churn, "prev_month_unpaid") > mean(stay, "prev_month_unpaid")


# ---------- hədəf ----------

def test_label_no_payment_no_activity_is_churn():
    assert dataset.label(_tiny(), NOV, 7) == 1


def test_label_attending_debtor_is_not_churn():
    t = _tiny(lesson_attendance=[Attendance(2, 7, _d(2025, 11, 11, 10, 3))])
    assert dataset.label(t, NOV, 7) == 0


def test_label_paid_this_month_is_not_churn():
    t = _tiny(payment_records=[PaymentRecord(1, 7, "2025-11", 70, _d(2025, 11, 20))])
    assert dataset.label(t, NOV, 7) == 0


def test_label_prepaid_before_snapshot_is_not_churn():
    t = _tiny(payment_records=[PaymentRecord(1, 7, "2025-11", 70, _d(2025, 10, 28))])
    assert dataset.label(t, NOV, 7) == 0


def test_label_ignores_payment_after_window():
    t = _tiny(payment_records=[PaymentRecord(1, 7, "2025-11", 70, _d(2025, 12, 5))])
    assert dataset.label(t, NOV, 7) == 1


# ---------- leakage ----------

def test_late_payment_for_previous_month_is_not_visible_yet():
    # Oktyabrın pulu noyabrın 10-da gəlib: noyabrın 1-də hələ ödənməmiş görünməlidir.
    t = _tiny(payment_records=[PaymentRecord(1, 7, "2025-10", 70, _d(2025, 11, 10))])
    f = dataset.features(t, NOV, 1, 7)
    assert f["prev_month_unpaid"] == 1
    assert f["prev_month_delay_days"] == 31.0


def test_features_ignore_future_events(tables, rows):
    future_junk = replace(
        tables,
        lesson_attendance=tables.lesson_attendance
        + [Attendance(1, r["student_id"], _d(2026, 6, 20)) for r in rows[:50]],
        payment_records=tables.payment_records
        + [PaymentRecord(r["chat_id"], r["student_id"], "2025-10", 1, _d(2026, 6, 20)) for r in rows[:50]],
        homework_attempts=tables.homework_attempts
        + [Attempt(1, r["student_id"], 10, _d(2026, 6, 20)) for r in rows[:50]],
    )
    for r in rows[::40]:
        t = datetime.fromisoformat(r["snapshot"]).replace(tzinfo=UTC)
        # Addım 4-ün trend əlamətləri də (FEATURES_V2) gələcəyi görməməlidir.
        assert dataset.features(future_junk, t, r["chat_id"], r["student_id"]) == {
            k: r[k] for k in dataset.FEATURES_V2
        }


def test_features_never_read_truth(tables, rows):
    no_truth = replace(tables, truth=[])
    r = rows[len(rows) // 2]
    t = datetime.fromisoformat(r["snapshot"]).replace(tzinfo=UTC)
    assert dataset.features(no_truth, t, r["chat_id"], r["student_id"]) == dataset.features(
        tables, t, r["chat_id"], r["student_id"]
    )


def test_every_row_has_all_features(rows):
    for r in rows:
        assert set(dataset.FEATURES_V2) <= r.keys()
        assert r["churned"] in (0, 1)


def test_time_split_test_is_strictly_later(rows):
    train, test = dataset.time_split(rows, "2026-04-01")
    assert train and test
    assert max(r["snapshot"] for r in train) < min(r["snapshot"] for r in test)
    assert len(train) + len(test) == len(rows)


def test_inactive_student_drops_out_of_snapshots():
    # Sentyabrda qoşulub heç nə etməyən şagird 45 gündən sonra kəsiklərdə sayılmır.
    t = _tiny()
    assert dataset.eligible(t, datetime(2025, 10, 1, tzinfo=UTC)) == [(1, 7)]
    assert dataset.eligible(t, datetime(2025, 12, 1, tzinfo=UTC)) == []


# ---------- fayllar və CLI ----------

def test_tables_csv_roundtrip(tmp_path):
    t = synth.generate(40, seed=2)
    write_tables(t, str(tmp_path))
    assert read_tables(str(tmp_path)) == t


def test_cli_writes_dataset(tmp_path, capsys):
    assert main(["--students", "60", "--seed", "5", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "churn_dataset.csv").exists()
    assert (tmp_path / "payment_records.csv").exists()
    assert "itki" in capsys.readouterr().out


def test_window_boundary_is_thirty_days():
    assert dataset.LABEL_WINDOW == timedelta(days=30)


# ---------- addım 4: trend əlamətləri və aylıq ardıcıllıq ----------

def test_engineered_features_on_tiny_case():
    # Oktyabr dərsinə gəlib, noyabr dərsini buraxıb: dekabrın 1-də 1 ardıcıl buraxılış.
    t = _tiny(lesson_attendance=[Attendance(1, 7, _d(2025, 10, 14, 10, 2))])
    f = dataset.features(t, datetime(2025, 12, 1, tzinfo=UTC), 1, 7)
    assert f["missed_lessons_streak"] == 1
    assert f["days_since_lesson"] == 47.6
    assert f["attend_trend"] == f["attend_rate_30d"] - f["attend_rate_prev_30d"]
    # Heç bir ay ödənməyib: son 3 ayın hamısı «gec».
    assert f["late_months_3m"] == 3


def test_sequence_shape_and_enrollment():
    from ml.churn import sequence
    t = _tiny(lesson_attendance=[Attendance(1, 7, _d(2025, 10, 14, 10, 2))])
    seq = sequence.sequence(t, datetime(2025, 12, 1, tzinfo=UTC), 1, 7)
    assert len(seq) == sequence.MONTHS
    assert all(len(step) == len(sequence.STEP_FEATURES) for step in seq)
    # İyun-avqust: şagird hələ yox idi (sentyabrda qoşulub).
    assert [step[0] for step in seq] == [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
    assert seq[4][1] == 1.0 and seq[5][1] == 0.0  # oktyabrda gəlib, noyabrda yox


def test_sequences_ignore_future_events(tables, rows):
    from ml.churn import sequence
    sample = rows[::60]
    junk = replace(
        tables,
        lesson_attendance=tables.lesson_attendance
        + [Attendance(1, r["student_id"], _d(2026, 6, 20)) for r in sample],
        payment_records=tables.payment_records
        + [PaymentRecord(r["chat_id"], r["student_id"], "2025-10", 1, _d(2026, 6, 20)) for r in sample],
    )
    assert sequence.build_sequences(junk, sample) == sequence.build_sequences(tables, sample)
