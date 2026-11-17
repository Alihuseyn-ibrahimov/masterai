"""Pilot üçün REAL KURSA BƏNZƏYƏN sintetik data (Kurs Kassası, Master NR 1 əvəzinə).

Niyə: Master NR 1-in ödəniş cədvəli hələ yoxdur, istifadəçi pilotu sintetik datayla
aparmağı seçdi (2026-11-17). `synth.py` model öyrətmək üçün sadə bir il idi
(3 qrup, adsız, ödəniş həmişə tam). Bu modul kurs sahibinin Kassada görəcəyi
mənzərəni verir və eyni `Tables` formasını yazır, yəni `dataset.py`, churn modeli
və `deploy/kassa_demo.py` onu dəyişmədən oxuyur.

Nə real kursdakı kimidir (hər biri aşağıda sabit kimi yazılıb, pilotda dəyişdirilir):

- **İki tədris ili.** 2025/26 qrupları (abituriyent iyunun sonunda, magistratura
  mayın sonunda bitir) + sentyabr 2026-da yeni axın, yeni qiymətlə. İl boyu
  qruplar (ingilis, IELTS, dövlət qulluğu) yayda da gedir, davamiyyət düşür,
  bir hissə yayda «ara verir», çoxu sentyabrda qayıdır.
- **Təqvim.** Bayram günləri dərs yoxdur (Yeni il, Novruz, Ramazan və Qurban,
  dövlət bayramları, təxmini tarixlər). Dərslər Bakı vaxtı ilə axşamdır.
- **Qəbul dalğaları.** Əsas qəbul sentyabr-oktyabr, ikinci dalğa yanvar, il
  boyu az sayda yeni şagird. Bəziləri dostu ilə birlikdə gəlir: dostu gedəndə
  getmə ehtimalı artır (modelin görmədiyi səbəb).
- **Ödəniş vərdişləri.** Vaxtında / gec / iki hissəyə bölən / borclu (ay buraxıb
  sonra iki ayı birdən ödəyir) / qabaqcadan 3 ay ödəyən. Nağd ödəyən pulu
  dərs günü gətirir, kartla ödəyəni rəhbər 0-2 gün sonra qeyd edir.
- **Qismən ödəniş.** Bir hissəsi ay ərzində qalanını gətirir, bir hissəsi borc qalır
  (`payment_records.amount < monthly_amount`, Kassa qalığı borc göstərir).
- **İtki.** Maraq aşağı + borc + mövsüm (yanvar, mart) riski artırır, siqnal
  əvvəlcədən görünür; bir hissəsi qəfildir (köçmə, pul). Abituriyent imtahana az
  qalanda nadir hallarda gedir. Getmiş şagirdlərin çoxunu rəhbər 3+ həftə sonra
  qrupdan çıxarır, bəzilərini unudur (Kassa onları «2+ aydır ödəmir» göstərir).
- **Səs-küy.** Endirimlər (bacı-qardaş, xüsusi), məbləği yazılmamış yeni şagird,
  QR-u unudulmuş dərs (davamiyyət yoxdur), qiymət artımı yalnız yeni şagirdlərə.
- **Xərclər.** Müəllim maaşı (qrup gəlirinin payı), icarə, qışda baha kommunal,
  qəbul aylarında çox reklam, dəftərxana.

Bütün adlar uydurmadır. Eyni `seed` + `as_of` = eyni kurs (testlə qorunur).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .schema import (
    Assignment,
    Attempt,
    Attendance,
    ChatMember,
    Expense,
    Lesson,
    PaymentFee,
    PaymentRecord,
    Program,
    Student,
    Tables,
    Truth,
    iso,
)

UTC = timezone.utc
START = datetime(2025, 9, 1, tzinfo=UTC)
DEFAULT_AS_OF = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
NEW_YEAR = datetime(2026, 9, 1, tzinfo=UTC)
FAR = datetime(2027, 9, 1, tzinfo=UTC)  # il boyu qruplar: simulyasiyadan kənar
QUESTIONS_PER_HW = 10
PRICE_RISE = 10  # sentyabr 2026: yeni şagird üçün +10 AZN, köhnələr köhnə qiymətlə


@dataclass(frozen=True)
class GroupSpec:
    name: str
    kind: str  # abituriyent | magistr | dovlet | ingilis
    fee: int  # AZN/ay
    starts: datetime
    ends: datetime | None  # müstəsna son an, None = il boyu
    size: int  # təxmini şagird sayı (`scale` ilə vurulur)
    weekdays: tuple[int, ...]
    hour_utc: int  # 14 = 18:00 Bakı
    teacher: float  # müəllimin təsiri: maraq həftədə bu qədər dəyişir


def _d(y: int, m: int, d: int = 1) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


# Haqlar bazar araşdırmasındakı orientirlərdir (Bakı, 2025-26), pilotda dəyişdirilir.
GROUPS = [
    GroupSpec("Abituriyent I qrup - A", "abituriyent", 140, START, _d(2026, 7), 22, (0, 2, 4), 13, 0.004),
    GroupSpec("Abituriyent I qrup - B", "abituriyent", 140, START, _d(2026, 7), 20, (1, 3, 5), 13, -0.004),
    GroupSpec("Abituriyent III qrup", "abituriyent", 120, START, _d(2026, 7), 18, (1, 3, 5), 10, 0.0),
    GroupSpec("Magistratura hazırlığı", "magistr", 110, START, _d(2026, 6), 20, (1, 3), 15, 0.0),
    GroupSpec("Dövlət qulluğu", "dovlet", 80, START, None, 18, (5, 6), 7, -0.002),
    GroupSpec("İngilis dili B1", "ingilis", 90, START, None, 18, (0, 3), 14, 0.002),
    GroupSpec("IELTS hazırlığı", "ingilis", 150, START, None, 12, (1, 4), 15, 0.0),
    GroupSpec("Abituriyent I qrup (2026/27)", "abituriyent", 150, NEW_YEAR, _d(2027, 7), 24, (0, 2, 4), 13, 0.002),
    GroupSpec("Abituriyent III qrup (2026/27)", "abituriyent", 130, NEW_YEAR, _d(2027, 7), 18, (1, 3, 5), 10, 0.0),
    GroupSpec("Magistratura hazırlığı (2026/27)", "magistr", 120, NEW_YEAR, _d(2027, 6), 20, (1, 3), 15, 0.0),
]

# Dərs olmayan günlər (təxmini; dini bayramlar Ay təqvimi ilə dəyişir).
HOLIDAYS: set[date] = set()
for _lo, _hi in [
    ((2025, 11, 8), (2025, 11, 10)),   # Zəfər günü, Dövlət bayrağı günü
    ((2025, 12, 31), (2026, 1, 7)),    # Yeni il tətili
    ((2026, 1, 20), (2026, 1, 20)),    # Ümumxalq hüzn günü
    ((2026, 3, 8), (2026, 3, 9)),
    ((2026, 3, 19), (2026, 3, 25)),    # Novruz + Ramazan bayramı
    ((2026, 5, 9), (2026, 5, 9)),
    ((2026, 5, 26), (2026, 5, 28)),    # Qurban bayramı, Müstəqillik günü
    ((2026, 6, 15), (2026, 6, 15)),
    ((2026, 6, 26), (2026, 6, 26)),
    ((2026, 11, 8), (2026, 11, 9)),
]:
    _day = date(*_lo)
    while _day <= date(*_hi):
        HOLIDAYS.add(_day)
        _day += timedelta(days=1)

# Ödəniş vərdişi: (ad, pay).
HABITS = [("on_time", 0.52), ("late", 0.24), ("split", 0.09), ("debtor", 0.08), ("prepay", 0.07)]
CASH_SHARE = 0.55
SIBLING_SHARE, SIBLING_DISCOUNT = 0.08, 0.10
SPECIAL_SHARE, SPECIAL_DISCOUNT = 0.04, 0.20
FRIEND_SHARE = 0.18  # dostu ilə birlikdə qoşulan
NO_FEE_RECENT = 2  # son 3 həftədə qoşulub, məbləği hələ yazılmayıb
MISSED_QR = 0.03  # müəllim QR-u unudub: dərsdə heç kimin davamiyyəti yoxdur
SUMMER_PAUSE, PAUSE_RETURN = 0.15, 0.6
REMOVE_AFTER_DAYS, REMOVE_SHARE = 21, 0.75
SUDDEN_WEEKLY = 0.0025
TRIAL_FROM_DAY = 22  # ayın 22-sindən sonra qoşulan o ayı ödəmir, pulu növbəti aydan

MALE = ["Elvin", "Kamran", "Murad", "Rauf", "Tural", "Orxan", "Nicat", "Fərid", "Ramil", "Səbuhi",
        "Emil", "Ülvi", "Rəşad", "Vüsal", "Cavid", "Anar", "Elnur", "Ruslan", "Toğrul", "Rəsul",
        "Hüseyn", "Əli", "Məhəmməd", "Ayxan", "Nihad", "Kənan", "İlkin", "Samir", "Pərviz", "Zaur",
        "Fuad", "Şahin", "Elşən", "Coşqun", "Yusif", "Ömər"]
FEMALE = ["Aysel", "Leyla", "Nərmin", "Günay", "Səbinə", "Aytən", "Lalə", "Nigar", "Fidan", "Ülkər",
          "Xədicə", "Şəbnəm", "Könül", "Aynur", "Gülnar", "Zəhra", "Fatimə", "Mədinə", "Səidə",
          "Arzu", "Nurlana", "Aygün", "Sevinc", "Türkan", "Rəna", "Gülay", "Jalə", "İlahə", "Ləman",
          "Narıngül", "Pərvanə", "Samirə", "Elmira", "Kəmalə", "Şəlalə", "Vəfa"]
SURNAMES = ["Əliyev", "Quliyev", "Həsənov", "Məmmədov", "İsmayılov", "Hüseynov", "Abbasov", "Cəfərov",
            "Rəhimov", "Kərimov", "Nəsirov", "Bağırov", "Orucov", "Səfərov", "Vəliyev", "Zeynalov",
            "Mustafayev", "Novruzov", "Qasımov", "Babayev", "Paşayev", "Əsgərov", "Rzayev", "Sadıqov",
            "Mirzəyev", "Allahverdiyev", "Hacıyev", "Tağıyev", "Əhmədov", "Süleymanov"]
UNISEX = ["Əlizadə", "Hüseynli", "Qurbanlı", "Məmmədli", "Kazımzadə", "Rəsulzadə"]  # qadında da eyni


@dataclass
class _Student:
    id: int
    group: int  # chat_id
    name: str
    joined: datetime
    fee: int
    engagement: float
    ability: float
    habit: str
    cash: bool
    friend: int | None = None
    left_at: datetime | None = None
    reason: str | None = None
    pause: tuple[datetime, datetime] | None = None  # yay arası [başla, qayıt)
    plans: dict[str, dict] = field(default_factory=dict)
    engagement_log: list[tuple[datetime, float]] = field(default_factory=list)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(dt: datetime) -> datetime:
    return (dt.replace(day=28) + timedelta(days=4)).replace(day=1)


def _mkey(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _names(rng: random.Random, count: int) -> list[str]:
    seen: set[str] = set()
    out = []
    while len(out) < count:
        if rng.random() < 0.5:
            first, family = rng.choice(MALE), rng.choice(SURNAMES + UNISEX)
        else:
            first, family = rng.choice(FEMALE), rng.choice(SURNAMES + UNISEX)
            if family in SURNAMES:
                family += "a"
        name = f"{first} {family}"
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def group_end(g: GroupSpec) -> datetime:
    return g.ends or FAR


def _lesson_days(g: GroupSpec, as_of: datetime) -> list[datetime]:
    out, day = [], g.starts
    end = min(group_end(g), as_of)
    while day < end:
        when = day.replace(hour=g.hour_utc)
        if day.weekday() in g.weekdays and day.date() not in HOLIDAYS and when < as_of:
            out.append(when)
        day += timedelta(days=1)
    return out


def _season(kind: str, when: datetime) -> float:
    """Mövsümün getmə riskinə əlavəsi (logit)."""
    m = when.month
    if kind == "abituriyent":
        return {11: 0.3, 1: 0.9, 3: 0.6, 4: -0.6, 5: -1.2, 6: -2.0}.get(m, 0.0)
    if kind == "magistr":
        return {11: 0.3, 1: 0.8, 3: 0.5, 4: -0.6, 5: -1.5}.get(m, 0.0)
    return {12: 0.4, 1: 0.6, 6: 0.5, 7: 0.3, 8: 0.3}.get(m, 0.0)


def _attend_factor(kind: str, when: datetime) -> float:
    if kind in ("ingilis", "dovlet") and when.month in (7, 8):
        return 0.75  # yay
    if kind == "abituriyent" and when.month in (4, 5, 6):
        return 1.08  # imtahan yaxınlaşır
    return 1.0


def _join_time(rng: random.Random, g: GroupSpec, as_of: datetime) -> datetime:
    end = min(group_end(g), as_of)
    roll = rng.random()
    if g.ends is not None:  # bir illik axın
        if roll < 0.72:
            lo, hi = g.starts - timedelta(days=10), g.starts + timedelta(days=24)
        elif roll < 0.88:
            lo, hi = g.starts + timedelta(days=24), g.starts + timedelta(days=80)
        else:  # yanvar dalğası (imtahana ≥4 ay qalırsa)
            jan = _d(g.starts.year + 1, 1, 8)
            lo, hi = (jan, jan + timedelta(days=35)) if jan + timedelta(days=120) < g.ends else \
                (g.starts, g.starts + timedelta(days=60))
    else:  # il boyu
        if roll < 0.50:
            lo, hi = START - timedelta(days=7), START + timedelta(days=30)
        elif roll < 0.62:
            lo, hi = _d(2026, 1, 8), _d(2026, 2, 10)
        elif roll < 0.80:
            lo, hi = NEW_YEAR - timedelta(days=5), NEW_YEAR + timedelta(days=30)
        else:
            lo, hi = START + timedelta(days=30), end - timedelta(days=10)
    hi = min(hi, end - timedelta(days=1))
    lo = min(lo, hi)
    t = lo + timedelta(seconds=rng.uniform(0, max(1.0, (hi - lo).total_seconds())))
    return t.replace(hour=rng.randint(6, 15), minute=rng.randint(0, 59), second=0, microsecond=0)


def _next_lesson(lessons: list[datetime], after: datetime) -> datetime | None:
    for when in lessons:
        if when >= after:
            return when
    return None


def _paid_moment(rng: random.Random, s: _Student, lessons: list[datetime], target: datetime) -> datetime:
    """Pulun KASSADA QEYD OLUNDUĞU an: nağd dərs günü, kart 0-2 gün sonra."""
    if s.cash:
        lesson = _next_lesson(lessons, target)
        if lesson is not None and lesson - target < timedelta(days=8):
            return lesson + timedelta(minutes=rng.randint(-20, 100))
    lag = timedelta(days=rng.choice([0, 0, 0, 1, 2]), hours=rng.uniform(0, 10))
    return (target + lag).replace(hour=rng.randint(5, 19), minute=rng.randint(0, 59), second=0, microsecond=0)


def _plan_month(rng: random.Random, s: _Student, month: datetime, lessons: list[datetime]) -> dict:
    """Bu ay necə ödəyəcək. `pays` = [(an, ümumi məbləğ)], sonuncu qeydə yazılan vəziyyətdir."""
    anchor = max(month, s.joined)
    low = s.engagement < 0.35  # marağı itən pulu da gecikdirir
    extra = rng.uniform(4, 14) if low else 0.0
    habit = s.habit
    if anchor == s.joined and habit != "prepay":
        days = rng.uniform(0, 3)  # yeni şagird ilk ayı qoşulanda ödəyir
        return {"pays": [(_paid_moment(rng, s, lessons, anchor + timedelta(days=days)), s.fee)]}
    if habit == "on_time":
        days = rng.uniform(0, 6) + extra
    elif habit == "late":
        days = rng.triangular(5, 26, 12) + extra
    elif habit == "debtor":
        if rng.random() < 0.3:
            return {"pays": [], "skip": True}  # bu ayı buraxır, sonra birlikdə ödəyə bilər
        days = rng.uniform(12, 40) + extra
    elif habit == "split":
        first = anchor + timedelta(days=rng.uniform(0, 8) + extra)
        part = _round5(s.fee * rng.choice([0.4, 0.5, 0.5, 0.6]))
        pays = [(_paid_moment(rng, s, lessons, first), part)]
        if rng.random() < 0.72:  # qalanını gətirir
            second = first + timedelta(days=rng.uniform(7, 24))
            pays.append((_paid_moment(rng, s, lessons, second), s.fee))
        return {"pays": pays}
    else:  # prepay: sentyabr/dekabr/mart/iyun 3 ay birdən, qalan aylar artıq ödənib
        return {"pays": [], "prepaid": True}
    return {"pays": [(_paid_moment(rng, s, lessons, anchor + timedelta(days=days)), s.fee)]}


AS_OF_RANGE = (datetime(2026, 9, 20, tzinfo=UTC), datetime(2027, 6, 1, tzinfo=UTC))


def generate(seed: int = 26, as_of: datetime = DEFAULT_AS_OF, scale: float = 1.0) -> Tables:
    """`as_of` = «bu gün»: ondan sonrakı heç bir hadisə yazılmır (cari ay yarımçıqdır)."""
    if not AS_OF_RANGE[0] <= as_of < AS_OF_RANGE[1]:
        raise ValueError(f"as_of {AS_OF_RANGE[0]:%Y-%m-%d} .. {AS_OF_RANGE[1]:%Y-%m-%d} arasında olmalıdır: "
                         "qrup cədvəli 2025/26 və 2026/27 tədris illəri üçün yazılıb")
    rng = random.Random(seed)
    t = Tables()
    for chat_id, g in enumerate(GROUPS, start=1):
        end_month = g.ends.month - 1 if g.ends is not None else None
        t.programs.append(Program(chat_id, g.kind, g.fee, end_month or None, g.name,
                                  iso(group_end(g))))
    lessons = {cid: _lesson_days(g, as_of) for cid, g in enumerate(GROUPS, start=1)}

    lesson_id = 0
    lesson_ids: dict[int, list[tuple[int, datetime]]] = {}
    for cid in lessons:
        lesson_ids[cid] = []
        for when in lessons[cid]:
            lesson_id += 1
            t.lessons.append(Lesson(lesson_id, cid, iso(when)))
            lesson_ids[cid].append((lesson_id, when))
    missed_qr = {lid for cid in lesson_ids for lid, _ in lesson_ids[cid] if rng.random() < MISSED_QR}

    hw_id = 0
    homework: dict[int, list[tuple[int, datetime]]] = {}
    for cid, g in enumerate(GROUPS, start=1):
        homework[cid] = []
        day = g.starts
        while day < min(group_end(g), as_of):
            if day.weekday() == 6 and day.date() not in HOLIDAYS and day.replace(hour=16) < as_of and not (
                    g.kind != "abituriyent" and day.month == 8):
                hw_id += 1
                due = day.replace(hour=16)
                t.homework_assignments.append(Assignment(hw_id, cid, iso(due), QUESTIONS_PER_HW))
                homework[cid].append((hw_id, due))
            day += timedelta(days=1)

    # --- şagirdlər ---
    sizes = [max(3, round(g.size * scale * rng.uniform(0.9, 1.1))) for g in GROUPS]
    names = _names(rng, sum(sizes))
    students: list[_Student] = []
    sid = 0
    for cid, (g, size) in enumerate(zip(GROUPS, sizes), start=1):
        for _ in range(size):
            sid += 1
            joined = _join_time(rng, g, as_of)
            friend = None
            mates = [x for x in students if x.group == cid and x.friend is None]
            if mates and rng.random() < FRIEND_SHARE:  # dostu ilə eyni gün gəlir
                buddy = rng.choice(mates)
                friend, joined = buddy.id, buddy.joined + timedelta(minutes=rng.randint(1, 30))
            base = g.fee + (PRICE_RISE if g.ends is None and joined >= NEW_YEAR else 0)
            roll = rng.random()
            if roll < SIBLING_SHARE:
                fee = _round5(base * (1 - SIBLING_DISCOUNT))
            elif roll < SIBLING_SHARE + SPECIAL_SHARE:
                fee = _round5(base * (1 - SPECIAL_DISCOUNT))
            else:
                fee = base
            habit = rng.choices([h for h, _ in HABITS], [w for _, w in HABITS])[0]
            students.append(_Student(
                id=sid, group=cid, name=names[sid - 1], joined=joined, fee=fee,
                engagement=rng.betavariate(5, 2), ability=rng.betavariate(4, 3), habit=habit,
                cash=rng.random() < CASH_SHARE, friend=friend,
            ))

    by_id = {s.id: s for s in students}
    for s in students:  # dost həmişə əvvəl simulyasiya olunur (id kiçikdir)
        g = GROUPS[s.group - 1]
        _simulate(rng, s, g, lessons[s.group], by_id, as_of)
        _emit(rng, s, g, lessons[s.group], lesson_ids[s.group], homework[s.group], missed_qr, as_of, t)

    # Səs-küy: son günlərdə qoşulan bir neçə şagirdin məbləği hələ yazılmayıb.
    recent = [s for s in students if as_of - timedelta(days=21) <= s.joined < as_of and s.left_at is None]
    no_fee = {s.id for s in rng.sample(recent, min(NO_FEE_RECENT, len(recent)))}
    for s in students:
        removed = None
        g = GROUPS[s.group - 1]
        if g.ends is not None and g.ends <= as_of:  # bitmiş axın: rəhbər qrupu boşaldır
            removed = g.ends + timedelta(days=rng.uniform(3, 20))
        elif s.left_at is not None and as_of - s.left_at > timedelta(days=REMOVE_AFTER_DAYS) \
                and rng.random() < REMOVE_SHARE:
            removed = s.left_at + timedelta(days=rng.uniform(REMOVE_AFTER_DAYS, 45))
        if removed is not None and removed >= as_of:
            removed = None
        t.students.append(Student(s.id, s.name))
        t.chat_members.append(ChatMember(s.group, s.id, iso(s.joined), iso(removed) if removed else None))
        if s.id in no_fee:
            t.payment_records = [p for p in t.payment_records if p.student_id != s.id]
        else:
            t.payment_fees.append(PaymentFee(s.group, s.id, s.fee))
        t.truth.append(Truth(s.id, s.group, iso(s.left_at) if s.left_at else None, s.reason))

    t.expenses = _expenses(rng, t, as_of)
    return t


def _unpaid_months(s: _Student, now: datetime) -> int:
    """Hazırkı ana qədər ödənməmiş (7 gündən çox gecikmiş) aylar: getmə riskinə girir."""
    count = 0
    for key, plan in s.plans.items():
        due = datetime.strptime(key, "%Y-%m").replace(tzinfo=UTC) + timedelta(days=7)
        if due > now or plan.get("prepaid_by") or plan.get("paused") or plan.get("trial"):
            continue
        if not plan["pays"] or plan["pays"][0][0] > now:
            count += 1
    return count


def _simulate(rng: random.Random, s: _Student, g: GroupSpec, lessons: list[datetime],
              by_id: dict[int, _Student], as_of: datetime) -> None:
    end = min(group_end(g), as_of)
    base = s.engagement
    week = s.joined
    month = _month_start(s.joined)
    prev_skipped: str | None = None
    prepaid_until: datetime | None = None
    pause_decided: set[int] = set()
    while week < end and s.left_at is None:
        # Yay arası: il boyu qrupda iyulun ilk həftəsində bir hissə ara verir (ildə bir qərar).
        if g.ends is None and week.month == 7 and week.year not in pause_decided:
            pause_decided.add(week.year)
            take = s.joined < _d(week.year, 6, 1) and rng.random() < SUMMER_PAUSE
        else:
            take = False
        if take:
            back = _d(week.year, 9, 1) + timedelta(days=rng.uniform(0, 12))
            if rng.random() < PAUSE_RETURN:
                s.pause = (week, back)
            else:  # «sentyabrda gələrəm» deyib gəlmədi
                s.left_at, s.reason = week + timedelta(days=rng.uniform(0, 5)), "pause"
                break
        paused = s.pause is not None and s.pause[0] <= week < s.pause[1]

        # Bu həftəyə düşən ayların ödəniş planı.
        while month <= week and month < end:
            key = _mkey(month)
            if key in s.plans:  # qabaqcadan ödənib
                pass
            elif s.pause and _month_start(s.pause[0]) <= month < s.pause[1] - timedelta(days=12):
                s.plans[key] = {"pays": [], "paused": True}
            elif prepaid_until is not None and month < prepaid_until:
                s.plans[key] = {"pays": [], "prepaid_by": True}
            elif s.habit == "prepay" and month >= _month_start(s.joined):
                n = min(3, max(1, (end.year - month.year) * 12 + end.month - month.month))
                anchor = max(month, s.joined) + timedelta(days=rng.uniform(0, 5))
                paid = _paid_moment(rng, s, lessons, anchor)
                for k in range(n):
                    m_k = month
                    for _ in range(k):
                        m_k = _next_month(m_k)
                    s.plans[_mkey(m_k)] = {"pays": [(paid, s.fee)], "prepaid_by": k > 0}
                prepaid_until = month
                for _ in range(n):
                    prepaid_until = _next_month(prepaid_until)
            elif month == _month_start(s.joined) and s.joined.day >= TRIAL_FROM_DAY and s.habit != "prepay":
                s.plans[key] = {"pays": [], "trial": True}  # ayın sonunda gəldi: ilk günlər sınaqdır
            else:
                plan = _plan_month(rng, s, month, lessons)
                s.plans[key] = plan
                # Borclu buraxdığı ayı növbəti ödənişlə birlikdə gətirir.
                if prev_skipped and plan["pays"] and rng.random() < 0.7:
                    s.plans[prev_skipped] = {"pays": [plan["pays"][-1]]}
                prev_skipped = key if plan.get("skip") else None
            month = _next_month(month)

        if not paused:
            s.engagement += rng.gauss(0, 0.045) + g.teacher + 0.03 * (base - s.engagement)
            if rng.random() < 0.010:  # şəxsi problem: maraq qəfil düşür
                s.engagement -= rng.uniform(0.2, 0.4)
            s.engagement = min(1.0, max(0.03, s.engagement))
            friend_left = (s.friend is not None and by_id[s.friend].left_at is not None
                           and by_id[s.friend].left_at < week)
            weeks_in = (week - s.joined).days / 7
            hazard = _sigmoid(
                -4.9
                + 5.0 * (0.55 - s.engagement)
                + 0.55 * min(3, _unpaid_months(s, week))
                + _season(g.kind, week)
                + (0.6 if weeks_in < 4 else 0.0)  # «bu kurs mənə uyğun deyil»
                + (0.9 if friend_left else 0.0)
            )
            if rng.random() < hazard:
                s.left_at, s.reason = week + timedelta(days=rng.uniform(0, 7)), "signal"
            elif rng.random() < SUDDEN_WEEKLY:
                s.left_at, s.reason = week + timedelta(days=rng.uniform(0, 7)), "sudden"
        s.engagement_log.append((week, s.engagement))
        week += timedelta(days=7)


def _engagement_at(s: _Student, when: datetime) -> float:
    log = s.engagement_log
    value = log[0][1] if log else s.engagement
    for start, e in log:
        if start > when:
            break
        value = e
    return value


def _emit(rng: random.Random, s: _Student, g: GroupSpec, lessons: list[datetime],
          lesson_ids: list[tuple[int, datetime]], homework: list[tuple[int, datetime]],
          missed_qr: set[int], as_of: datetime, t: Tables) -> None:
    end = min(group_end(g), as_of)
    stop = min(end, s.left_at) if s.left_at else end

    def away(when: datetime) -> bool:
        return s.pause is not None and s.pause[0] <= when < s.pause[1]

    for lid, when in lesson_ids:
        if not (s.joined <= when < stop) or away(when) or lid in missed_qr:
            continue
        e = _engagement_at(s, when)
        if s.reason == "signal" and s.left_at and s.left_at - when < timedelta(days=21):
            e *= 0.6  # getməzdən əvvəlki həftələr: sönmə görünür
        if rng.random() < min(0.97, (0.2 + 0.75 * e) * _attend_factor(g.kind, when)):
            seen = when + timedelta(minutes=rng.randint(-5, 12))
            if seen < as_of:
                t.lesson_attendance.append(Attendance(lid, s.id, iso(seen)))

    for hid, due in homework:
        if not (s.joined <= due < stop) or away(due):
            continue
        e = _engagement_at(s, due)
        if rng.random() < 0.08 + 0.85 * e:
            p_correct = min(0.97, 0.25 + 0.65 * s.ability * (0.6 + 0.4 * e))
            score = sum(rng.random() < p_correct for _ in range(QUESTIONS_PER_HW))
            done = due - timedelta(hours=rng.uniform(1, 72))
            if done >= s.joined:
                t.homework_attempts.append(Attempt(hid, s.id, score, iso(done)))

    for key, plan in sorted(s.plans.items()):
        # Getmiş şagird sonradan ödəmir; qabaqcadan ödədiyi pul geri qaytarılmır.
        done = [(when, amount) for when, amount in plan["pays"] if when < stop and when < as_of]
        if done:
            when, amount = done[-1]  # bazada bir sətir: son qeyd köhnəni əvəz edir
            t.payment_records.append(PaymentRecord(s.group, s.id, key, amount, iso(when)))


def _expenses(rng: random.Random, t: Tables, as_of: datetime) -> list[Expense]:
    out: list[Expense] = []
    month = _month_start(START)
    while month <= as_of:
        key = _mkey(month)
        payroll = 0
        for p in t.programs:
            if datetime.fromisoformat(p.ends_at) <= month:
                continue
            g = GROUPS[p.chat_id - 1]
            if g.starts > month:
                continue
            members = [m for m in t.chat_members if m.chat_id == p.chat_id
                       and datetime.fromisoformat(m.joined_at) < _next_month(month)]
            if members:  # müəllimə qrup başına sabit + şagird başına (orientir)
                payroll += 250 + 12 * len(members)
        if payroll:
            out.append(Expense(key, "Müəllim maaşı", 10 * round(payroll / 10), "qrup başına sabit + şagird"))
        out.append(Expense(key, "İcarə", 900 if month < NEW_YEAR else 1000, "2 otaq, Nərimanov"))
        heating = 70 if month.month in (12, 1, 2) else (30 if month.month in (7, 8) else 0)
        out.append(Expense(key, "Kommunal", 110 + heating + rng.randint(0, 4) * 10, "işıq, qaz, internet"))
        ads = {8: (400, 600), 9: (350, 550), 1: (200, 300)}.get(month.month, (80, 160))
        out.append(Expense(key, "Reklam", 10 * round(rng.uniform(*ads) / 10), "Instagram, TikTok"))
        if month.month in (9, 1):
            out.append(Expense(key, "Digər", 10 * round(rng.uniform(80, 160) / 10), "dəftərxana, çap"))
        month = _next_month(month)
    return out


def summary_line(t: Tables, as_of: datetime = DEFAULT_AS_OF) -> dict:
    """Generatorun yoxlanması üçün qısa rəqəmlər (CLI və testlər)."""
    left = [x for x in t.truth if x.left_at]
    fees = {(f.chat_id, f.student_id): f.monthly_amount for f in t.payment_fees}
    partial = sum(1 for p in t.payment_records if p.amount < fees.get((p.chat_id, p.student_id), 0))
    return {
        "groups": len(t.programs),
        "students": len(t.students),
        "active_now": sum(1 for m in t.chat_members if m.removed_at is None),
        "left": len(left),
        "left_by_reason": {r: sum(1 for x in left if x.left_reason == r) for r in ("signal", "sudden", "pause")},
        "payments": len(t.payment_records),
        "partial_payments": partial,
        "lessons": len(t.lessons),
        "attendance": len(t.lesson_attendance),
        "homework_attempts": len(t.homework_attempts),
        "expenses": len(t.expenses),
        "as_of": iso(as_of),
    }
