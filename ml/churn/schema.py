"""Kassa datası: masterai cədvəllərinin churn üçün lazım olan sütunları.

Sütun adları `server/*_store.py`-dəki ilə EYNİDİR (chat_members, payment_fees,
payment_records, lessons, lesson_attendance, homework_assignments,
homework_attempts). Ona görə real bazadan oxuyan yükləyici (növbəti addım) bu
dataclass-ları dolduracaq və `dataset.py` heç dəyişməyəcək.

Vaxtlar masterai-dəki kimi UTC ISO mətnidir (`2026-01-05T10:00:00+00:00`).
Müqayisə üçün `parse_ts` ilə `datetime`-a çevrilir.
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ChatMember:  # chat_members
    chat_id: int
    user_id: int
    joined_at: str


@dataclass
class PaymentFee:  # payment_fees
    chat_id: int
    student_id: int
    monthly_amount: int  # AZN


@dataclass
class PaymentRecord:  # payment_records
    chat_id: int
    student_id: int
    month: str  # YYYY-AA: ödənişin AİD OLDUĞU ay
    amount: int
    paid_at: str  # pulun QEYD OLUNDUĞU an. Leakage üçün yalnız bu sayılır


@dataclass
class Lesson:  # lessons
    id: int
    chat_id: int
    starts_at: str


@dataclass
class Attendance:  # lesson_attendance
    lesson_id: int
    user_id: int
    joined_at: str


@dataclass
class Assignment:  # homework_assignments (+ question_count, sintetikdə)
    id: int
    chat_id: int
    due_date: str
    question_count: int = 10


@dataclass
class Attempt:  # homework_attempts
    assignment_id: int
    student_id: int
    score: int  # düzgün cavab sayı (masterai-dəki kimi)
    completed_at: str | None


@dataclass
class Program:
    """Kurs proqramı (qrup çatı). Sintetikdir; real masterai-də qrupun adı/kursu var."""

    chat_id: int
    kind: str  # abituriyent | magistr | ingilis
    monthly_fee: int
    end_month: int | None  # proqram bu ayın sonunda bitir (6 = iyun), None = il boyu


@dataclass
class Truth:
    """YALNIZ sintetik: gizli həqiqət. dataset.py buna TOXUNMUR (spec, leakage §5)."""

    student_id: int
    chat_id: int
    left_at: str | None
    left_reason: str | None  # signal | sudden | None


@dataclass
class Tables:
    programs: list[Program] = field(default_factory=list)
    chat_members: list[ChatMember] = field(default_factory=list)
    payment_fees: list[PaymentFee] = field(default_factory=list)
    payment_records: list[PaymentRecord] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)
    lesson_attendance: list[Attendance] = field(default_factory=list)
    homework_assignments: list[Assignment] = field(default_factory=list)
    homework_attempts: list[Attempt] = field(default_factory=list)
    truth: list[Truth] = field(default_factory=list)


TABLE_TYPES = {
    "programs": Program,
    "chat_members": ChatMember,
    "payment_fees": PaymentFee,
    "payment_records": PaymentRecord,
    "lessons": Lesson,
    "lesson_attendance": Attendance,
    "homework_assignments": Assignment,
    "homework_attempts": Attempt,
    "truth": Truth,
}


def write_tables(tables: Tables, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for name, cls in TABLE_TYPES.items():
        cols = [f.name for f in fields(cls)]
        with open(os.path.join(out_dir, f"{name}.csv"), "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols)
            writer.writeheader()
            for row in getattr(tables, name):
                writer.writerow(asdict(row))


def read_tables(in_dir: str) -> Tables:
    tables = Tables()
    for name, cls in TABLE_TYPES.items():
        path = os.path.join(in_dir, f"{name}.csv")
        if not os.path.exists(path):
            continue
        types = {f.name: f.type for f in fields(cls)}
        rows = []
        with open(path, encoding="utf-8", newline="") as fh:
            for raw in csv.DictReader(fh):
                rows.append(cls(**{k: _cast(v, types[k]) for k, v in raw.items()}))
        setattr(tables, name, rows)
    return tables


def _cast(value: str, type_name: str):
    if value == "" and "None" in type_name:
        return None
    if type_name.startswith("int"):
        return int(value)
    return value
