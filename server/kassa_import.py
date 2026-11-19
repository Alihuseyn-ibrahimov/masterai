"""Kurs Kassası: CSV / Excel faylından şagird, aylıq məbləğ və ödəniş importu.

Kursun real datası çox vaxt Excel cədvəlindədir: hər sətir bir şagirdin bir
ayıdır. Bu modul faylı oxuyur, sütunları tanıyır, hər sətri yoxlayır və bazaya
yazmazdan ƏVVƏL nə olacağını göstərir (`plan_import`). Rəhbər nəticəni görüb
təsdiqləyəndən sonra eyni plan yazılır (`apply_plan`).

Format (bir cədvəl, başlıq birinci sətirdə; sütun adları əl ilə yazıla bilər,
böyük/kiçik hərf, «ə/e», boşluq/alt xətt fərqi nəzərə alınmır):

    qrup | şagird | email | aylıq məbləğ | qoşulma tarixi | ay | ödənilən | ödəniş tarixi | borc

- `qrup`, `şagird` məcburidir. Qrup kursda adla tapılır, yoxdursa yaradılır.
- Şagird əvvəl `email` ilə (kurs daxilində), sonra qrupdakı adla tapılır; yoxdursa
  hesabı yaradılır (giriş şifrəsi YOXDUR, yalnız kassa üçün). Qrupda eyni adlı iki
  şagird varsa sətir rədd olunur: hansı olduğunu təxmin etmirik, email lazımdır.
- `ay` + `ödənilən` ödəniş qeydidir. `ödənilən` boş və ya 0 = o ay ödəməyib, yəni
  BORC. Borc ayrıca yazılmır: Kassa onu aylıq məbləğ - ödənilən kimi özü hesablayır.
  `borc` sütunu varsa yalnız yoxlama üçündür (fərq = xəbərdarlıq).
- `qoşulma tarixi` yoxdursa yeni üzv faylda gördüyümüz ilk ayın 1-də qoşulmuş sayılır,
  yoxsa keçmiş aylar Kassada «hələ qoşulmamışdı» kimi borca düşməzdi.

Təkrar import təhlükəsizdir: məbləğ və ödəniş eyni (qrup, şagird, ay) üçün üstünə
yazılır, şagird və qrup ikinci dəfə yaradılmır. Faylda 0 olan, bazada isə ödənmiş
ay SİLİNMİR (yalnız xəbərdarlıq): fayl köhnə ola bilər, pulu itirmək olmaz.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
MAX_AMOUNT = 100_000
UNUSABLE_PASSWORD = "!"  # bcrypt hash deyil: verify_password həmişə False qaytarır
IMPORT_EMAIL_DOMAIN = "kassa-import.invalid"

COLUMNS = ("qrup", "şagird", "email", "aylıq məbləğ", "qoşulma tarixi",
           "ay", "ödənilən", "ödəniş tarixi", "borc")
REQUIRED = ("qrup", "şagird")

_FOLD = str.maketrans("əƏıİöÖüÜşŞçÇğĞ", "eeiioouussccgg")

# Normallaşdırılmış başlıq -> sütun. Real cədvəllərdə rast gəlinən adlar.
_ALIASES = {
    "qrup": "qrup", "grup": "qrup", "group": "qrup", "sinif": "qrup", "qrupadi": "qrup",
    "sagird": "şagird", "telebe": "şagird", "student": "şagird", "ad": "şagird",
    "adsoyad": "şagird", "soyadad": "şagird", "sagirdinadi": "şagird", "name": "şagird",
    "email": "email", "epoct": "email", "mail": "email",
    "ayliqmebleg": "aylıq məbləğ", "ayliq": "aylıq məbləğ",
    "aidat": "aylıq məbləğ", "fee": "aylıq məbləğ", "monthlyfee": "aylıq məbləğ",
    "qosulmatarixi": "qoşulma tarixi", "qosulub": "qoşulma tarixi", "joined": "qoşulma tarixi",
    "baslama": "qoşulma tarixi", "baslamatarixi": "qoşulma tarixi",
    "ay": "ay", "month": "ay", "odenisayi": "ay",
    "odenilen": "ödənilən", "odenib": "ödənilən", "odenis": "ödənilən", "paid": "ödənilən",
    "mebleg": "ödənilən", "odenilenmebleg": "ödənilən",
    "odenistarixi": "ödəniş tarixi", "paidat": "ödəniş tarixi", "tarix": "ödəniş tarixi",
    "borc": "borc", "qaliq": "borc", "debt": "borc",
}

_MONTH_NAMES = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avqust": 8, "sentyabr": 9, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
}


class ImportFileError(ValueError):
    """Fayl ümumiyyətlə oxunmur (format, ölçü, başlıq) - sətir xətası deyil."""


def _fold(text: str) -> str:
    return str(text).translate(_FOLD).lower()


def normalize_header(text: str) -> str | None:
    key = re.sub(r"[\s_.()\-]+", "", _fold(text).strip())
    return _ALIASES.get(key)


def name_key(text: str) -> str:
    """Ad müqayisəsi: «Əliyeva  Aysel» = «eliyeva aysel»."""
    return " ".join(_fold(text).split())


# ---------- faylın oxunması ----------

def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_csv(data: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "cp1254", "cp1251"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1251 hər baytı açır
        raise ImportFileError("Faylın kodlaşdırması tanınmadı, UTF-8 ilə saxlayın")
    first = text.split("\n", 1)[0]
    # Azərbaycan dilli Excel CSV-ni «;» ilə saxlayır (vergül onluq ayırıcıdır).
    delimiter = max((";", ",", "\t"), key=first.count)
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _read_xlsx(data: bytes) -> list[list[str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - requirements.txt-dədir
        raise ImportFileError("Serverdə Excel oxuyucusu yoxdur, CSV yükləyin") from exc
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # zip deyil, xarab fayl və s.
        raise ImportFileError("Excel faylı açılmadı. .xlsx olduğuna əmin olun (köhnə .xls oxunmur)") from exc
    try:
        sheet = book.worksheets[0]
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append([_cell_text(v) for v in row])
            if len(rows) > MAX_ROWS + 1:
                break
        return rows
    finally:
        book.close()


def read_table(filename: str, data: bytes) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    """(tanınmış sütunlar, [(fayldakı sətir nömrəsi, {sütun: mətn})])."""
    if not data:
        raise ImportFileError("Fayl boşdur")
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError("Fayl 2 MB-dan böyükdür")
    lower = (filename or "").lower()
    if lower.endswith(".xlsx"):
        raw = _read_xlsx(data)
    elif lower.endswith((".csv", ".txt")):
        raw = _read_csv(data)
    elif lower.endswith(".xls"):
        raise ImportFileError("Köhnə .xls formatı oxunmur: Excel-də «Fərqli saxla» → .xlsx və ya .csv")
    else:
        raise ImportFileError("Yalnız .csv və .xlsx faylı qəbul olunur")

    # Başlıqdan əvvəlki boş sətirləri keç.
    start = next((i for i, r in enumerate(raw) if any(c for c in r)), None)
    if start is None:
        raise ImportFileError("Faylda heç bir sətir yoxdur")
    header = raw[start]
    mapping: dict[int, str] = {}
    unknown = []
    for idx, title in enumerate(header):
        if not title:
            continue
        col = normalize_header(title)
        if col is None:
            unknown.append(title)
        elif col in mapping.values():
            raise ImportFileError(f"«{col}» sütunu iki dəfə var")
        else:
            mapping[idx] = col
    missing = [c for c in REQUIRED if c not in mapping.values()]
    if missing:
        hint = f" Tanınmayan başlıqlar: {', '.join(unknown)}." if unknown else ""
        raise ImportFileError(
            f"Məcburi sütun tapılmadı: {', '.join(missing)}.{hint} Nümunə şablona baxın.")

    rows = []
    for offset, row in enumerate(raw[start + 1:], start=start + 2):
        values = {col: (row[idx] if idx < len(row) else "").strip() for idx, col in mapping.items()}
        if not any(values.values()):
            continue
        rows.append((offset, values))
    if not rows:
        raise ImportFileError("Başlıqdan sonra data sətri yoxdur")
    if len(rows) > MAX_ROWS:
        raise ImportFileError(f"Fayl {MAX_ROWS} sətirdən çoxdur, hissələrə bölün")
    return sorted(set(mapping.values()), key=COLUMNS.index), rows


# ---------- dəyərlərin yoxlanması ----------

def parse_amount(text: str) -> int | None:
    """«120», «120.00», «120,00», «1 200 AZN», «₼120» -> tam AZN. Səhvdə ValueError."""
    cleaned = re.sub(r"(?i)azn|manat|₼|\s", "", text)
    if not cleaned:
        return None
    if re.fullmatch(r"\d+[.,]\d{1,2}", cleaned):
        value = float(cleaned.replace(",", "."))
    elif re.fullmatch(r"\d+", cleaned):
        value = float(cleaned)
    else:
        raise ValueError("rəqəm deyil")
    if not value.is_integer():
        raise ValueError("qəpiklə məbləğ qəbul olunmur, tam AZN yazın")
    if value > MAX_AMOUNT:
        raise ValueError(f"{MAX_AMOUNT} AZN-dən çoxdur")
    return int(value)


def parse_date(text: str) -> date | None:
    """«2026-11-03», «03.11.2026», «3/11/2026» (gün əvvəl), Excel tarixi."""
    t = text.strip()
    if not t:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", t)
        if not m:
            raise ValueError("tarix «2026-11-03» və ya «03.11.2026» kimi olmalıdır")
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError as exc:
        raise ValueError("belə tarix yoxdur") from exc


def parse_month(text: str) -> str | None:
    """«2026-11», «11.2026», «2026-11-01», «noyabr 2026» -> «2026-11»."""
    t = text.strip()
    if not t:
        return None
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})", t) or None
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
    elif (m := re.fullmatch(r"(\d{1,2})[./-](\d{4})", t)):
        mo, y = int(m.group(1)), int(m.group(2))
    elif (m := re.fullmatch(r"([^\d\s]+)\s+(\d{4})", t)):
        mo = _MONTH_NAMES.get(_fold(m.group(1)))
        if mo is None:
            raise ValueError("ay adı tanınmadı")
        y = int(m.group(2))
    else:
        try:
            parsed = parse_date(t)
        except ValueError as exc:
            raise ValueError("ay «2026-11» kimi olmalıdır") from exc
        y, mo = parsed.year, parsed.month
    if not 1 <= mo <= 12 or not 2000 <= y <= 2100:
        raise ValueError("ay «2026-11» kimi olmalıdır")
    return f"{y:04d}-{mo:02d}"


@dataclass
class RowError:
    row: int
    column: str | None
    message: str

    def as_dict(self) -> dict:
        return {"row": self.row, "column": self.column, "message": self.message}


@dataclass
class ImportRow:
    row: int
    group: str
    student: str
    email: str | None
    fee: int | None
    joined: date | None
    month: str | None
    paid: int | None
    paid_on: date | None
    debt: int | None


_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def validate_rows(rows: list[tuple[int, dict[str, str]]]) -> tuple[list[ImportRow], list[RowError]]:
    """Hər sətri ayrı yoxlayır. Xətalı sətir nəticəyə düşmür, amma bütün xətalar toplanır."""
    out: list[ImportRow] = []
    errors: list[RowError] = []
    for number, v in rows:
        row_errors: list[RowError] = []

        def get(col, parser, number=number, v=v, row_errors=row_errors):
            try:
                return parser(v.get(col, ""))
            except ValueError as exc:
                row_errors.append(RowError(number, col, f"«{v.get(col, '')}»: {exc}"))
                return None

        group = " ".join(v.get("qrup", "").split())
        student = " ".join(v.get("şagird", "").split())
        if not group:
            row_errors.append(RowError(number, "qrup", "boşdur"))
        if not student:
            row_errors.append(RowError(number, "şagird", "boşdur"))
        if len(group) > 100:
            row_errors.append(RowError(number, "qrup", "100 simvoldan uzundur"))
        if len(student) > 100:
            row_errors.append(RowError(number, "şagird", "100 simvoldan uzundur"))
        email = v.get("email", "").strip().lower() or None
        if email and not _EMAIL.fullmatch(email):
            row_errors.append(RowError(number, "email", f"«{email}»: email deyil"))
        fee = get("aylıq məbləğ", parse_amount)
        if fee == 0:
            row_errors.append(RowError(number, "aylıq məbləğ", "0 ola bilməz (pulsuz şagirdi boş saxlayın)"))
        joined = get("qoşulma tarixi", parse_date)
        month = get("ay", parse_month)
        paid = get("ödənilən", parse_amount)
        paid_on = get("ödəniş tarixi", parse_date)
        debt = get("borc", parse_amount)
        if paid and month is None and "ay" not in {e.column for e in row_errors}:
            row_errors.append(RowError(number, "ay", "ödəniş var, amma hansı aya aid olduğu yazılmayıb"))
        if (paid_on or v.get("borc")) and month is None and not paid:
            if "ay" not in {e.column for e in row_errors}:
                row_errors.append(RowError(number, "ay", "ödəniş/borc məlumatı var, amma ay yazılmayıb"))
        if row_errors:
            errors.extend(row_errors)
            continue
        out.append(ImportRow(number, group, student, email, fee, joined, month, paid, paid_on, debt))
    return out, errors


# ---------- plan: bazaya nə yazılacaq ----------

@dataclass
class StudentPlan:
    key: tuple[str, str]           # (qrup açarı, şagird açarı və ya email)
    group_key: str
    display_name: str
    email: str | None
    user_id: int | None            # None = yaradılacaq
    member: bool                   # artıq bu qrupun üzvüdür
    joined_at: str | None          # mövcud üzvlük tarixi
    fee: int | None
    fee_row: int | None
    current_fee: int | None
    new_joined: str | None = None  # yazılacaq qoşulma tarixi
    first_row: int = 0
    months: dict[str, ImportRow] = field(default_factory=dict)


@dataclass
class ImportPlan:
    groups: dict[str, dict]        # açar -> {"name", "chat_id" | None}
    students: list[StudentPlan]
    errors: list[RowError]
    warnings: list[RowError]
    rows: int

    def summary(self) -> dict:
        payments = [r for s in self.students for r in s.months.values() if r.paid]
        unpaid = [r for s in self.students for r in s.months.values() if not r.paid]
        return {
            "rows": self.rows,
            "groups_new": sorted(g["name"] for g in self.groups.values() if g["chat_id"] is None),
            "groups_existing": sorted(g["name"] for g in self.groups.values() if g["chat_id"] is not None),
            "students_new": sum(1 for s in self.students if s.user_id is None),
            "students_matched": sum(1 for s in self.students if s.user_id is not None),
            "fees": sum(1 for s in self.students if s.fee is not None and s.fee != s.current_fee),
            "payments": len(payments),
            "paid_total": sum(r.paid for r in payments),
            "unpaid_months": len(unpaid),
            "debt_total": sum(max(0, (s.fee if s.fee is not None else s.current_fee or 0) - (r.paid or 0))
                              for s in self.students for r in s.months.values()),
            "errors": [e.as_dict() for e in sorted(self.errors, key=lambda e: e.row)],
            "warnings": [w.as_dict() for w in sorted(self.warnings, key=lambda w: w.row)],
        }


def _month_iso(month: str) -> str:
    return f"{month}-01T00:00:00+00:00"


def plan_import(rows: list[ImportRow], row_errors: list[RowError], *, course_id: int,
                chats, users, payments, total_rows: int) -> ImportPlan:
    """Bazanı OXUYUR, heç nə yazmır."""
    errors = list(row_errors)
    warnings: list[RowError] = []

    # Kursun mövcud qrupları (adla).
    groups: dict[str, dict] = {}
    existing: dict[str, dict] = {}
    for chat_id in chats.list_ids_by_course(course_id):
        chat = chats.get(chat_id)
        if chat and chat["kind"] == "group" and chat["name"]:
            existing.setdefault(name_key(chat["name"]), chat)

    members_cache: dict[int, dict[int, str]] = {}
    people: dict[int, dict | None] = {}

    def person(uid: int) -> dict | None:
        if uid not in people:
            people[uid] = users.get_by_id(uid)
        return people[uid]

    def members(chat_id: int) -> dict[int, str]:
        if chat_id not in members_cache:
            members_cache[chat_id] = chats.list_members_joined(chat_id)
        return members_cache[chat_id]

    fees_cache: dict[int, dict[int, int]] = {}

    def fee_of(chat_id: int | None, uid: int | None) -> int | None:
        if chat_id is None or uid is None:
            return None
        if chat_id not in fees_cache:
            fees_cache[chat_id] = payments.list_fees_for_chat(chat_id)
        return fees_cache[chat_id].get(uid)

    students: dict[tuple[str, str], StudentPlan] = {}
    for r in rows:
        gkey = name_key(r.group)
        group = groups.get(gkey)
        if group is None:
            chat = existing.get(gkey)
            group = groups[gkey] = {"name": chat["name"] if chat else r.group,
                                    "chat_id": chat["id"] if chat else None}
        chat_id = group["chat_id"]
        skey = (gkey, r.email or name_key(r.student))
        plan = students.get(skey)
        if plan is None:
            user_id, member, joined_at = None, False, None
            if r.email:
                found = users.get_by_email(r.email)
                if found is not None:
                    if found["course_id"] != course_id:
                        errors.append(RowError(r.row, "email", "bu email başqa kursun istifadəçisidir"))
                        continue
                    if found["is_teacher"]:
                        errors.append(RowError(r.row, "email", "bu email müəllimindir, şagird deyil"))
                        continue
                    user_id = found["id"]
            if user_id is None and chat_id is not None:
                same = [uid for uid in members(chat_id)
                        if (p := person(uid)) and not p["is_teacher"]
                        and name_key(p["display_name"]) == name_key(r.student)]
                if len(same) > 1:
                    errors.append(RowError(r.row, "şagird",
                                           f"«{r.group}» qrupunda «{r.student}» adlı {len(same)} şagird var, "
                                           "hansı olduğunu bilmək üçün email sütunu doldurun"))
                    continue
                if same:
                    user_id = same[0]
            if user_id is not None and chat_id is not None:
                member = user_id in members(chat_id)
                joined_at = members(chat_id).get(user_id)
            plan = students[skey] = StudentPlan(
                key=skey, group_key=gkey, display_name=r.student, email=r.email,
                user_id=user_id, member=member, joined_at=joined_at,
                fee=None, fee_row=None, current_fee=fee_of(chat_id, user_id), first_row=r.row)
        if r.fee is not None:
            if plan.fee is not None and plan.fee != r.fee:
                errors.append(RowError(r.row, "aylıq məbləğ",
                                       f"eyni şagird üçün {plan.fee_row}-ci sətirdə {plan.fee} AZN yazılıb, "
                                       f"burada {r.fee} AZN"))
                continue
            plan.fee, plan.fee_row = r.fee, r.row
        if r.joined is not None:
            plan.new_joined = datetime(r.joined.year, r.joined.month, r.joined.day,
                                       tzinfo=timezone.utc).isoformat()
        if r.month is not None:
            if r.month in plan.months:
                errors.append(RowError(r.row, "ay", f"{r.month} ayı bu şagird üçün "
                                       f"{plan.months[r.month].row}-ci sətirdə artıq var"))
                continue
            plan.months[r.month] = r

    # Sətirlərarası yoxlamalar.
    for plan in students.values():
        fee = plan.fee if plan.fee is not None else plan.current_fee
        for month, r in sorted(plan.months.items()):
            if fee is None:
                errors.append(RowError(r.row, "aylıq məbləğ",
                                       "şagirdin aylıq məbləği yoxdur: ödəniş və borc ona görə hesablanır"))
                break
            if r.paid and r.paid > fee:
                warnings.append(RowError(r.row, "ödənilən",
                                         f"{r.paid} AZN aylıq məbləğdən ({fee} AZN) çoxdur"))
            if r.debt is not None and r.debt != max(0, fee - (r.paid or 0)):
                warnings.append(RowError(r.row, "borc",
                                         f"faylda {r.debt} AZN, hesablanan {max(0, fee - (r.paid or 0))} AZN "
                                         "(aylıq məbləğ - ödənilən). Kassa hesablananı göstərəcək"))
            if not r.paid and plan.user_id is not None and groups[plan.group_key]["chat_id"] is not None:
                done = payments.list_payments_for_chat(groups[plan.group_key]["chat_id"], month)
                if plan.user_id in done:
                    warnings.append(RowError(r.row, "ödənilən",
                                             f"faylda ödənməyib, amma bazada {month} üçün "
                                             f"{done[plan.user_id]['amount']} AZN ödəniş var: toxunulmayacaq"))
        # Qoşulma tarixi: yoxdursa faylın ilk ayı, mövcud üzvlükdə yalnız ERKƏNƏ çəkilir.
        if plan.new_joined is None and plan.months:
            first = _month_iso(min(plan.months))
            if not plan.member or (plan.joined_at and first < plan.joined_at):
                plan.new_joined = first
        if plan.new_joined and plan.months and min(plan.months) < plan.new_joined[:7]:
            r = plan.months[min(plan.months)]
            warnings.append(RowError(r.row, "qoşulma tarixi",
                                     f"{min(plan.months)} ayı qoşulma tarixindən əvvəldir: "
                                     "Kassa o ayın məbləğini gözləmir"))

    # Kursun yer limiti: yeni şagirdlər yerləşirmi?
    new_count = len({s.email or id(s) for s in students.values() if s.user_id is None})
    course = users.courses.get(course_id)
    seat_limit = course.get("seat_limit") if course else None
    if seat_limit is not None and new_count:
        free = seat_limit - users.count_active_students(course_id)
        if new_count > free:
            errors.append(RowError(0, None,
                                   f"{new_count} yeni şagird yaradılmalıdır, kursun yer limitində "
                                   f"{max(0, free)} boş yer var (limit {seat_limit}). Sahibdən limiti artırmağı istəyin"))

    return ImportPlan(groups=groups, students=list(students.values()), errors=errors,
                      warnings=warnings, rows=total_rows)


def apply_plan(plan: ImportPlan, *, course_id: int, admin_id: int, chats, users, payments) -> None:
    """Xətasız planı yazır. Xəta varsa çağırılmamalıdır (ValueError)."""
    if plan.errors:
        raise ValueError("plan xətalıdır")
    for group in plan.groups.values():
        if group["chat_id"] is None:
            chat = chats.create("group", admin_id, group["name"], course_id=course_id)
            group["chat_id"] = chat["id"]
    created_by_identity: dict[str, int] = {}
    for s in plan.students:
        chat_id = plan.groups[s.group_key]["chat_id"]
        if s.user_id is None:
            # Eyni şagird iki qrupdadırsa (eyni email və ya ad) bir hesab yaradılır.
            # Adla tapılan şagird qrupdan-qrupa birləşdirilmir: iki «Aysel» iki adam ola bilər.
            identity = s.email
            if identity and identity in created_by_identity:
                s.user_id = created_by_identity[identity]
            else:
                email = s.email or f"sagird-{secrets.token_hex(6)}@{IMPORT_EMAIL_DOMAIN}"
                user = users.create_student(email, UNUSABLE_PASSWORD, s.display_name, course_id=course_id)
                s.user_id = user["id"]
                if identity:
                    created_by_identity[identity] = s.user_id
        chats.add_member(chat_id, s.user_id)
        if s.new_joined:
            chats.set_member_joined_at(chat_id, s.user_id, s.new_joined)
        if s.fee is not None and s.fee != s.current_fee:
            payments.set_fee(chat_id, s.user_id, s.fee)
        for month, r in s.months.items():
            if not r.paid:
                continue
            paid_on = r.paid_on or date.fromisoformat(f"{month}-01")
            payments.mark_paid(chat_id, s.user_id, month, r.paid, marked_by=admin_id,
                               paid_at=datetime(paid_on.year, paid_on.month, paid_on.day, 12,
                                                tzinfo=timezone.utc).isoformat())


# ---------- nümunə şablon ----------

TEMPLATE_ROWS = [
    ("Abituriyent A", "Aysel Məmmədova", "", "120", "2026-09-01", "2026-09", "120", "2026-09-03", ""),
    ("Abituriyent A", "Aysel Məmmədova", "", "120", "", "2026-10", "120", "2026-10-02", ""),
    ("Abituriyent A", "Aysel Məmmədova", "", "120", "", "2026-11", "60", "2026-11-05", "60"),
    ("Abituriyent A", "Murad Əliyev", "murad@example.com", "120", "2026-10-01", "2026-10", "120", "", ""),
    ("Abituriyent A", "Murad Əliyev", "murad@example.com", "120", "", "2026-11", "", "", "120"),
    ("Magistratura B", "Nigar Həsənova", "", "150", "", "2026-11", "150", "2026-11-01", ""),
]


TEMPLATE_DIR = "web/assets/templates"  # statik: brauzer tokensiz endirir
TEMPLATE_NAME = "kassa-import-sablon"


def template_csv() -> str:
    """BOM ilə: Excel UTF-8 CSV-ni yalnız BOM olanda düzgün açır (yoxsa «ə» pozulur)."""
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(TEMPLATE_ROWS)
    return buf.getvalue()


def template_xlsx() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    sheet = book.active
    sheet.title = "Ödənişlər"
    sheet.append(list(COLUMNS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in TEMPLATE_ROWS:
        sheet.append([int(v) if v.isdigit() else v for v in row])
    for letter, width in zip("ABCDEFGHI", (18, 20, 22, 14, 16, 10, 11, 15, 8)):
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = "A2"
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


def write_templates(root: str = ".") -> list[str]:
    """`python -m server.kassa_import` statik şablonları yenidən yazır."""
    import os

    folder = os.path.join(root, TEMPLATE_DIR)
    os.makedirs(folder, exist_ok=True)
    csv_path = os.path.join(folder, f"{TEMPLATE_NAME}.csv")
    xlsx_path = os.path.join(folder, f"{TEMPLATE_NAME}.xlsx")
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(template_csv())
    with open(xlsx_path, "wb") as fh:
        fh.write(template_xlsx())
    return [csv_path, xlsx_path]


if __name__ == "__main__":
    for path in write_templates():
        print(path)
