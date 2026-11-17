"""Kurs Kassası demosu / pilotu: TƏZƏ qovluqda sintetik kurs qurur.

İki rejim:

- **pilot** (defolt, 2026-11-17): `ml/churn/realistic.py` - real kursa bənzəyən iki
  tədris ili: 10 qrup (3-ü bitib və boşaldılıb), ~190 şagird, mövsümi qəbul və itki,
  gecikən, iki hissəyə bölən, qabaqcadan ödəyən, borclu şagirdlər, bayramlar, xərclər.
  Master NR 1-in real datası yoxdur, pilot bu datayla aparılır. Bazalardan əlavə
  `tables/` qovluğuna eyni datanın CSV-ləri yazılır (`ml.churn` onları oxuyur).
- **--simple** (addım 8): 3 qrup, 40 şagird, 6 ay. Görüşdə hekayəni bir baxışda izah
  etmək üçün: 3 nəfər ödəməyi kəsib, Kassa onları «yəqin gedib» işarələyir.

Hər iki rejim BOŞ qovluğa yazır (qovluqda `.db` varsa heç nə yazmadan çıxır) və
lokal serveri o bazalarla işə salmaq üçün `demo.env` yazır.

    .venv/bin/python deploy/kassa_demo.py --data-dir /tmp/kassa-pilot
    set -a; . /tmp/kassa-pilot/demo.env; set +a
    .venv/bin/uvicorn server.app:app --port 8125
    # ayrı terminalda: web/ statik server, config.js lokal backend-ə
    # brauzerdə giriş (skript e-poçt və şifrəni çap edir) → Hesabatlar → Kassa

Bütün adlar uydurmadır. Eyni `--seed` (+ pilotda eyni gün) = eyni kurs.
"""

from __future__ import annotations

import argparse
import random
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.churn import realistic  # noqa: E402
from ml.churn.schema import Tables, write_tables  # noqa: E402
from server.auth import hash_password  # noqa: E402
from server.chat_store import ChatStore  # noqa: E402
from server.course_store import DEFAULT_COURSE_ID  # noqa: E402
from server.kassa import month_start, months_back, next_month  # noqa: E402
from server.payment_store import PaymentStore  # noqa: E402
from server.user_store import UserStore  # noqa: E402

UTC = timezone.utc
HISTORY_MONTHS = 6

# (qrup adı, aylıq haqq AZN, şagird sayı). Haqlar bazar araşdırmasındakı
# orientirlərdir, pilotda kursun öz rəqəmləri ilə əvəz olunur.
GROUPS = [
    ("Abituriyent - riyaziyyat", 120, 16),
    ("Magistratura hazırlığı", 90, 13),
    ("İngilis dili B1", 70, 11),
]

# Ödəniş vərdişi: (ad, pay, ayın hansı günləri ödəyir).
HABITS = [
    ("vaxtında", 0.62, (1, 7)),
    ("gec", 0.26, (8, 24)),
    ("qeyri-sabit", 0.12, (5, 28)),
]
STOPPED_PAYING = 3  # 2+ ay ödəməyən: Kassa «yəqin gedib» deyir
IRREGULAR_SKIP = 0.35

MALE = ["Elvin", "Kamran", "Murad", "Rauf", "Tural", "Orxan", "Nicat", "Fərid",
        "Ramil", "Səbuhi", "Emil", "Ülvi", "Rəşad", "Vüsal", "Cavid", "Anar"]
FEMALE = ["Aysel", "Leyla", "Nərmin", "Günay", "Səbinə", "Aytən", "Lalə", "Nigar",
          "Fidan", "Ülkər", "Xədicə", "Şəbnəm", "Könül", "Aynur", "Gülnar", "Zəhra"]
SURNAMES = ["Əliyev", "Quliyev", "Həsənov", "Məmmədov", "İsmayılov", "Hüseynov",
            "Abbasov", "Cəfərov", "Rəhimov", "Kərimov", "Nəsirov", "Bağırov",
            "Orucov", "Səfərov", "Vəliyev", "Zeynalov"]

FIXED_EXPENSES = [("İcarə", 650, ""), ("Kommunal", 90, "işıq, internet")]


@dataclass
class DemoResult:
    data_dir: Path
    month: str
    email: str
    password: str
    students: int
    stopped: list[str]


def _feminine(surname: str) -> str:
    return surname + "a"


def _names(rng: random.Random, count: int) -> list[str]:
    seen: set[str] = set()
    out = []
    while len(out) < count:
        if rng.random() < 0.5:
            name = f"{rng.choice(MALE)} {rng.choice(SURNAMES)}"
        else:
            name = f"{rng.choice(FEMALE)} {_feminine(rng.choice(SURNAMES))}"
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _habit(rng: random.Random) -> tuple[str, tuple[int, int]]:
    roll, acc = rng.random(), 0.0
    for name, share, days in HABITS:
        acc += share
        if roll < acc:
            return name, days
    return HABITS[-1][0], HABITS[-1][2]


# Server HƏR bazanı bu qovluqdan oxusun: yoxsa qalan bazalar iş qovluğunda yaranar.
SERVER_DBS = ["users", "chats", "chat_join_requests", "messages", "materials", "questions",
              "quiz_sessions", "quiz_attempts", "friendships", "question_sets", "homework",
              "lessons", "live_sessions", "badges", "summaries", "payments"]


def _env_key(name: str) -> str:
    return "HOMEWORK_DB_PATH" if name == "homework" else f"{name.upper()}_DB_PATH"


def _env_text(paths: dict[str, Path]) -> str:
    # Lokal demo server üçün öz JWT açarı: yoxsa giriş 500 verir (server açarsız başlamır).
    # Yükləmələr də demo qovluğuna: defolt `server/uploads/` kod qovluğudur, serverdə
    # demo kodun checkout-una fayl yazardı (deploy/DEPLOY_KASSA.md).
    uploads = next(iter(paths.values())).parent / "uploads"
    return ("".join(f"{key}={path}\n" for key, path in paths.items())
            + f"MATERIAL_UPLOAD_DIR={uploads}\n" + f"JWT_SECRET={secrets.token_urlsafe(48)}\n")


def db_paths(data_dir: Path) -> dict[str, Path]:
    return {_env_key(name): data_dir / f"{name}.db" for name in SERVER_DBS}


def build(data_dir: Path, month: str, *, now: datetime, seed: int = 15,
          password: str | None = None, hasher=hash_password) -> DemoResult:
    data_dir.mkdir(parents=True, exist_ok=True)
    if any(data_dir.glob("*.db")):
        raise FileExistsError(f"{data_dir} artıq baza saxlayır - demo yalnız BOŞ qovluğa yazılır")
    rng = random.Random(seed)
    paths = db_paths(data_dir)
    users = UserStore(str(paths["USERS_DB_PATH"]))
    chats = ChatStore(str(paths["CHATS_DB_PATH"]))
    payments = PaymentStore(str(paths["PAYMENTS_DB_PATH"]))

    password = password or secrets.token_urlsafe(9)
    email = "rehber@kassa-demo.example.com"
    owner = users.create(email, hasher(password), "Kurs rəhbəri (demo)",
                         course_id=DEFAULT_COURSE_ID)
    users.set_teacher(owner["id"], True)
    users.set_admin(owner["id"], True)

    months = months_back(month, HISTORY_MONTHS)
    first_day = month_start(months[0])
    total = sum(g[2] for g in GROUPS)
    names = _names(rng, total)
    stop_idx = set(rng.sample(range(total), STOPPED_PAYING))
    stopped: list[str] = []
    idx = 0

    for group_name, fee, size in GROUPS:
        chat = chats.create("group", owner["id"], group_name, course_id=DEFAULT_COURSE_ID)
        chats.add_member(chat["id"], owner["id"])
        _backdate_member(chats, chat["id"], owner["id"], first_day)
        for _ in range(size):
            name = names[idx]
            student = users.create(f"sagird{idx + 1}@kassa-demo.example.com",
                                   hasher(secrets.token_urlsafe(12)), name,
                                   course_id=DEFAULT_COURSE_ID)
            # Çoxu kursun əvvəlindən, bəziləri sonradan qoşulub.
            joined_month = 0 if rng.random() < 0.8 else rng.randint(1, HISTORY_MONTHS - 2)
            joined = month_start(months[joined_month]) + timedelta(days=rng.randint(0, 9),
                                                                   hours=rng.randint(9, 17))
            chats.add_member(chat["id"], student["id"])
            _backdate_member(chats, chat["id"], student["id"], joined)
            payments.set_fee(chat["id"], student["id"], fee)

            habit, (lo, hi) = _habit(rng)
            # Ödəməni kəsən: son 2-3 ayı ödəmir.
            stop_from = (len(months) - rng.randint(2, 3)) if idx in stop_idx else None
            if stop_from is not None:
                stopped.append(name)
            for m_i, m in enumerate(months):
                if m_i < joined_month:
                    continue
                if stop_from is not None and m_i >= stop_from:
                    continue
                if habit == "qeyri-sabit" and m_i < len(months) - 1 and rng.random() < IRREGULAR_SKIP:
                    continue
                paid_at = month_start(m) + timedelta(days=rng.randint(lo, hi) - 1,
                                                     hours=rng.randint(9, 20))
                if paid_at > now:
                    continue  # cari ayda hələ ödəməyib
                payments.mark_paid(chat["id"], student["id"], m, fee, owner["id"])
                _backdate_payment(payments, chat["id"], student["id"], m, paid_at)
            idx += 1

    for m in months:
        if month_start(m) > now:
            continue
        expected = sum(fee * size for _, fee, size in GROUPS)
        payroll = round(expected * rng.uniform(0.36, 0.42) / 10) * 10
        payments.add_expense(DEFAULT_COURSE_ID, m, "Müəllim maaşı", payroll, "3 müəllim", owner["id"])
        for category, amount, note in FIXED_EXPENSES:
            payments.add_expense(DEFAULT_COURSE_ID, m, category,
                                 amount + rng.randint(0, 3) * 10 if category == "Kommunal" else amount,
                                 note, owner["id"])
        payments.add_expense(DEFAULT_COURSE_ID, m, "Reklam", rng.choice([120, 150, 200, 250]),
                             "Instagram", owner["id"])

    env = _env_text(paths)
    (data_dir / "demo.env").write_text(env, encoding="utf-8")
    return DemoResult(data_dir, month, email, password, total, stopped)


@dataclass
class PilotResult:
    data_dir: Path
    month: str
    email: str
    password: str
    tables: Tables
    summary: dict


def build_pilot(data_dir: Path, *, now: datetime, seed: int = 26, scale: float = 1.0,
                password: str | None = None, hasher=hash_password) -> PilotResult:
    """Realist generatorun kursunu server bazalarına yazır (`now` = generatorun «bu gün»ü)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    if any(data_dir.glob("*.db")):
        raise FileExistsError(f"{data_dir} artıq baza saxlayır - demo yalnız BOŞ qovluğa yazılır")
    tables = realistic.generate(seed, as_of=now, scale=scale)
    paths = db_paths(data_dir)
    users = UserStore(str(paths["USERS_DB_PATH"]))
    chats = ChatStore(str(paths["CHATS_DB_PATH"]))
    payments = PaymentStore(str(paths["PAYMENTS_DB_PATH"]))

    password = password or secrets.token_urlsafe(9)
    email = "rehber@kassa-demo.example.com"
    owner = users.create(email, hasher(password), "Kurs rəhbəri (demo)", course_id=DEFAULT_COURSE_ID)
    users.set_teacher(owner["id"], True)
    users.set_admin(owner["id"], True)

    chat_ids: dict[int, int] = {}  # generatorun chat_id-si -> bazadakı
    for program in tables.programs:
        chat = chats.create("group", owner["id"], program.name, course_id=DEFAULT_COURSE_ID)
        chat_ids[program.chat_id] = chat["id"]
        chats.add_member(chat["id"], owner["id"])
        spec = realistic.GROUPS[program.chat_id - 1]
        _backdate_member(chats, chat["id"], owner["id"], spec.starts - timedelta(days=14))

    # Şagirdlər daxil olmur: bir bcrypt hamısı üçün (190 dəfə hash 40 saniyə çəkərdi).
    student_hash = hasher(secrets.token_urlsafe(16))
    user_ids: dict[int, int] = {}
    for student in tables.students:
        created = users.create(f"sagird{student.user_id}@kassa-demo.example.com", student_hash,
                               student.display_name, course_id=DEFAULT_COURSE_ID)
        user_ids[student.user_id] = created["id"]
    for m in tables.chat_members:
        if m.removed_at is not None:  # rəhbər qrupdan çıxarıb: bazada üzvlük yoxdur
            continue
        chats.add_member(chat_ids[m.chat_id], user_ids[m.user_id])
        _backdate_member(chats, chat_ids[m.chat_id], user_ids[m.user_id], datetime.fromisoformat(m.joined_at))
    for f in tables.payment_fees:
        payments.set_fee(chat_ids[f.chat_id], user_ids[f.student_id], f.monthly_amount)
    with payments._lock:  # 1000+ qeyd: bir tranzaksiya (store-un mark_paid-i hər dəfə commit edir)
        payments._conn.executemany(
            "INSERT INTO payment_records (chat_id, student_id, month, amount, marked_by, paid_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(chat_ids[p.chat_id], user_ids[p.student_id], p.month, p.amount, owner["id"], p.paid_at)
             for p in tables.payment_records])
        payments._conn.commit()
    for x in tables.expenses:
        payments.add_expense(DEFAULT_COURSE_ID, x.month, x.category, x.amount, x.note, owner["id"])

    write_tables(tables, str(data_dir / "tables"))
    env = _env_text(paths)
    (data_dir / "demo.env").write_text(env, encoding="utf-8")
    return PilotResult(data_dir, now.strftime("%Y-%m"), email, password, tables,
                       realistic.summary_line(tables, now))


def _backdate_member(chats: ChatStore, chat_id: int, user_id: int, when: datetime) -> None:
    with chats._lock:
        chats._conn.execute("UPDATE chat_members SET joined_at = ? WHERE chat_id = ? AND user_id = ?",
                            (when.isoformat(), chat_id, user_id))
        chats._conn.commit()


def _backdate_payment(payments: PaymentStore, chat_id: int, student_id: int, month: str,
                      when: datetime) -> None:
    with payments._lock:
        payments._conn.execute(
            "UPDATE payment_records SET paid_at = ? WHERE chat_id = ? AND student_id = ? AND month = ?",
            (when.isoformat(), chat_id, student_id, month))
        payments._conn.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kurs Kassası üçün sintetik demo/pilot kursu")
    parser.add_argument("--data-dir", required=True, help="BOŞ qovluq (yoxdursa yaradılır)")
    parser.add_argument("--simple", action="store_true", help="kiçik hekayə: 3 qrup, 40 şagird")
    parser.add_argument("--month", help="yalnız --simple: göstəriləcək ay YYYY-AA (defolt: cari ay)")
    parser.add_argument("--as-of", help="yalnız pilot: «bu gün» YYYY-AA-GG (defolt: bu gün)")
    parser.add_argument("--seed", type=int, help="defolt: pilot 26, --simple 15")
    parser.add_argument("--scale", type=float, default=1.0, help="yalnız pilot: qrup ölçüsü vurğusu")
    args = parser.parse_args(argv)
    now = datetime.now(UTC)
    data_dir = Path(args.data_dir).resolve()
    if not args.simple:
        as_of = (datetime.fromisoformat(args.as_of).replace(hour=12, tzinfo=UTC) if args.as_of
                 else now.replace(microsecond=0))
        try:
            result = build_pilot(data_dir, now=as_of, seed=26 if args.seed is None else args.seed,
                                 scale=args.scale)
        except (FileExistsError, ValueError) as exc:
            print(exc)
            return 1
        s = result.summary
        print(f"Pilot kursu hazırdır: {result.data_dir} (bu gün: {as_of:%Y-%m-%d})")
        print(f"  {s['groups']} qrup, {s['students']} şagird (indi qrupda {s['active_now']}), "
              f"getmiş {s['left']} {s['left_by_reason']}")
        print(f"  {s['payments']} ödəniş ({s['partial_payments']} qismən), {s['attendance']} davamiyyət, "
              f"{s['expenses']} xərc qeydi; CSV: {result.data_dir / 'tables'}")
        print(f"  giriş: {result.email} / {result.password}")
        print(f"  server: set -a; . {result.data_dir / 'demo.env'}; set +a; "
              ".venv/bin/uvicorn server.app:app --port 8125")
        return 0

    month = args.month or now.strftime("%Y-%m")
    if month_start(month) > now:
        print(f"{month} hələ başlamayıb")
        return 1
    try:
        result = build(data_dir, month, now=min(now, month_start(next_month(month))),
                       seed=15 if args.seed is None else args.seed)
    except FileExistsError as exc:
        print(exc)
        return 1
    print(f"Demo kursu hazırdır: {result.data_dir}")
    print(f"  {len(GROUPS)} qrup, {result.students} şagird, {HISTORY_MONTHS} ay, ay: {result.month}")
    print(f"  ödəməni kəsənlər: {', '.join(result.stopped)}")
    print(f"  giriş: {result.email} / {result.password}")
    print(f"  server: set -a; . {result.data_dir / 'demo.env'}; set +a; "
          ".venv/bin/uvicorn server.app:app --port 8125")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
