"""Sintetik kurs datası: realistik ödəniş, davamiyyət və şagird itkisi naxışları.

Niyə sintetik: real masterai-də ödəniş tarixçəsi hələ azdır (Kassa yenidir).
Generator masterai cədvəllərinin EYNİ sütunlarını yazır (`schema.py`), ona görə
dataset və model kodu sonra real dataya dəyişmədən keçir.

Model (spec: docs/superpowers/specs/2026-11-15-kurs-kassasi-design.md):
- Hər şagirdin gizli MARAĞI (engagement, 0-1) var, həftədən həftəyə təsadüfi
  dəyişir, bəzən şəxsi problemlə qəfil düşür. Davamiyyət, tapşırıq və bal ona bağlıdır.
- Ödəniş vərdişi: vaxtında / gec / borclu. Maraq azalanda ödəniş də gecikir.
- Getmə iki yolla: (1) maraq aşağı + gecikmə + sezon (yanvar, mart) riski artırır,
  siqnal əvvəlcədən görünür; (2) qəfil (köçmə, pul problemi), siqnalsız.
- Abituriyent qrupu iyunda, magistr mayda bitir: proqramın bitməsi itki deyil.

Eyni `seed` = eyni nəticə (testlə qorunur).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .schema import (
    Assignment,
    Attempt,
    Attendance,
    ChatMember,
    Lesson,
    PaymentFee,
    PaymentRecord,
    Program,
    Tables,
    Truth,
    iso,
)

UTC = timezone.utc
START = datetime(2025, 9, 1, tzinfo=UTC)
END = datetime(2026, 7, 1, tzinfo=UTC)  # müstəsna son: iyunun sonu

# (növ, aylıq haqq AZN, bitmə ayı, şagird payı). Rəqəmlər bazar araşdırmasındakı
# orientirlərdən götürülüb, pilotda real data ilə dəyişdirilməlidir.
PROGRAMS = [
    ("abituriyent", 120, 6, 0.45),
    ("magistr", 90, 5, 0.25),
    ("ingilis", 70, None, 0.30),
]
LESSON_WEEKDAYS = (1, 3)  # çərşənbə axşamı, cümə axşamı
LESSON_HOUR = 10  # 10:00 UTC = 14:00 Bakı
QUESTIONS_PER_HW = 10

# Getmə riski (həftəlik). Ayda ~4-12% itki verəcək şəkildə seçilib, testlə qorunur.
SUDDEN_WEEKLY = 0.004
SEASON_BOOST = {1: 0.9, 3: 0.6}  # yanvar: tətildən sonra, mart: sınaq nəticələri


@dataclass
class _Student:
    id: int
    chat_id: int
    joined: datetime
    engagement: float
    ability: float
    habit: str  # on_time | late | debtor
    discount: float
    left_at: datetime | None = None
    left_reason: str | None = None


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(dt: datetime) -> datetime:
    return (dt.replace(day=28) + timedelta(days=4)).replace(day=1)


def program_end(program: Program) -> datetime:
    """Proqramın son anı (müstəsna). Il boyu proqram simulyasiyanın sonuna qədər gedir."""
    if program.ends_at:
        dt = datetime.fromisoformat(program.ends_at)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    if program.end_month is None:
        return END
    year = 2026 if program.end_month < 9 else 2025
    return _next_month(datetime(year, program.end_month, 1, tzinfo=UTC))


def _pay_delay_days(rng: random.Random, habit: str, engagement: float) -> float | None:
    """Ayın başından (və ya qoşulmadan) ödənişə qədər gün. None = bu ay ödəmir."""
    if habit == "on_time":
        delay = rng.uniform(0, 5)
    elif habit == "late":
        delay = rng.uniform(4, 20)
    else:  # debtor
        if rng.random() < 0.3:
            return None
        delay = rng.uniform(15, 45)
    if engagement < 0.35:  # marağı itən şagird pulu da gecikdirir
        delay += rng.uniform(5, 15)
    return delay


def generate(n_students: int = 400, seed: int = 7) -> Tables:
    rng = random.Random(seed)
    t = Tables()

    for chat_id, (kind, fee, end_month, _) in enumerate(PROGRAMS, start=1):
        t.programs.append(Program(chat_id, kind, fee, end_month))
    programs = {p.chat_id: p for p in t.programs}

    # --- dərslər və tapşırıqlar (hər qrup üçün eyni cədvəl) ---
    lessons_by_chat: dict[int, list[tuple[int, datetime]]] = {p.chat_id: [] for p in t.programs}
    hw_by_chat: dict[int, list[tuple[int, datetime]]] = {p.chat_id: [] for p in t.programs}
    lesson_id = hw_id = 0
    day = START
    while day < END:
        for p in t.programs:
            if day >= program_end(p):
                continue
            if day.weekday() in LESSON_WEEKDAYS:
                lesson_id += 1
                when = day.replace(hour=LESSON_HOUR)
                t.lessons.append(Lesson(lesson_id, p.chat_id, iso(when)))
                lessons_by_chat[p.chat_id].append((lesson_id, when))
            if day.weekday() == 6:  # bazar günü son tarix
                hw_id += 1
                due = day.replace(hour=20)
                t.homework_assignments.append(Assignment(hw_id, p.chat_id, iso(due), QUESTIONS_PER_HW))
                hw_by_chat[p.chat_id].append((hw_id, due))
        day += timedelta(days=1)

    # --- şagirdlər ---
    weights = [w for *_, w in PROGRAMS]
    students: list[_Student] = []
    for sid in range(1, n_students + 1):
        chat_id = rng.choices([p.chat_id for p in t.programs], weights)[0]
        end = program_end(programs[chat_id])
        if rng.random() < 0.75:  # əsas qəbul: sentyabr - oktyabrın ortası
            joined = START + timedelta(days=rng.uniform(0, 45))
        else:  # il boyu az sayda yeni şagird, bitməyə 2 ay qalana qədər
            latest = end - timedelta(days=60)
            joined = START + timedelta(days=rng.uniform(45, max(46.0, (latest - START).days)))
        joined = joined.replace(microsecond=0)
        habit = rng.choices(["on_time", "late", "debtor"], [0.65, 0.25, 0.10])[0]
        students.append(
            _Student(
                id=sid,
                chat_id=chat_id,
                joined=joined,
                engagement=rng.betavariate(5, 2),
                ability=rng.betavariate(4, 3),
                habit=habit,
                discount=0.9 if rng.random() < 0.12 else 1.0,  # qardaş/bacı endirimi
            )
        )

    for s in students:
        p = programs[s.chat_id]
        fee = int(round(p.monthly_fee * s.discount))
        t.chat_members.append(ChatMember(s.chat_id, s.id, iso(s.joined)))
        t.payment_fees.append(PaymentFee(s.chat_id, s.id, fee))
        _simulate_student(rng, s, p, fee, lessons_by_chat[s.chat_id], hw_by_chat[s.chat_id], t)
        t.truth.append(
            Truth(s.id, s.chat_id, iso(s.left_at) if s.left_at else None, s.left_reason)
        )
    return t


def _simulate_student(
    rng: random.Random,
    s: _Student,
    p: Program,
    fee: int,
    lessons: list[tuple[int, datetime]],
    homeworks: list[tuple[int, datetime]],
    t: Tables,
) -> None:
    end = program_end(p)
    # Həftə-həftə: əvvəlcə maraq dəyişir, sonra getmə qərarı, sonra o həftənin hadisələri.
    week = s.joined
    late_streak = 0
    engagement_by_week: list[tuple[datetime, float]] = []
    while week < end and s.left_at is None:
        s.engagement += rng.gauss(0, 0.05)
        if rng.random() < 0.012:  # şəxsi problem: maraq qəfil düşür
            s.engagement -= rng.uniform(0.2, 0.4)
        s.engagement = min(1.0, max(0.03, s.engagement))
        engagement_by_week.append((week, s.engagement))

        weeks_in = (week - s.joined).days / 7
        hazard = _sigmoid(
            -5.2
            + 5.0 * (0.55 - s.engagement)
            + 0.5 * late_streak
            + SEASON_BOOST.get(week.month, 0.0)
            + (0.5 if weeks_in < 4 else 0.0)  # ilk ay: «bu kurs mənə uyğun deyil»
        )
        if rng.random() < hazard:
            s.left_at, s.left_reason = week + timedelta(days=rng.uniform(0, 7)), "signal"
        elif rng.random() < SUDDEN_WEEKLY:
            s.left_at, s.left_reason = week + timedelta(days=rng.uniform(0, 7)), "sudden"
        week += timedelta(days=7)
        late_streak = _late_streak(s, week)

    stop = min(end, s.left_at) if s.left_at else end

    def engagement_at(when: datetime) -> float:
        value = engagement_by_week[0][1] if engagement_by_week else s.engagement
        for start, e in engagement_by_week:
            if start > when:
                break
            value = e
        return value

    for lid, when in lessons:
        if s.joined <= when < stop and rng.random() < 0.2 + 0.75 * engagement_at(when):
            t.lesson_attendance.append(Attendance(lid, s.id, iso(when + timedelta(minutes=rng.randint(0, 10)))))

    for hid, due in homeworks:
        if not (s.joined <= due < stop):
            continue
        e = engagement_at(due)
        if rng.random() < 0.1 + 0.85 * e:
            p_correct = min(0.97, 0.25 + 0.65 * s.ability * (0.6 + 0.4 * e))
            score = sum(rng.random() < p_correct for _ in range(QUESTIONS_PER_HW))
            done = due - timedelta(hours=rng.uniform(1, 72))
            if done >= s.joined:
                t.homework_attempts.append(Attempt(hid, s.id, score, iso(done)))

    month = _month_start(s.joined)
    while month < end:
        anchor = max(month, s.joined)
        delay = _pay_delay_days(rng, s.habit, engagement_at(anchor))
        if delay is not None:
            paid = (anchor + timedelta(days=delay)).replace(microsecond=0)
            # Getmiş şagird ödəmir; aid olduğu ay bitəndən çox sonra da ödəniş olmur.
            if paid < stop and paid < END:
                t.payment_records.append(PaymentRecord(s.chat_id, s.id, month.strftime("%Y-%m"), fee, iso(paid)))
        month = _next_month(month)


def _late_streak(s: _Student, now: datetime) -> int:
    """Getmə riski üçün kobud siqnal: şagird borclu/gec vərdişlidirsə ay keçdikcə artır.

    Simulyasiyada ödənişlər sonradan yazıldığı üçün burada vərdişə görə təxmin edilir:
    bu, YALNIZ gizli modelin daxili dəyişənidir, datasetə düşmür.
    """
    months_in = max(0, (now - s.joined).days // 30)
    if s.habit == "debtor":
        return min(3, months_in)
    if s.habit == "late":
        return min(1, months_in)
    return 0
