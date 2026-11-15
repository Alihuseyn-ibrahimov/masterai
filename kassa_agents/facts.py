"""Kassa agentlərinin qoruyucu qatı (LLM-siz, yalnız stdlib).

Agentlərə Kassanın xülasəsi (`GET /live/kassa`) verilir, amma üç qaydadan keçərək:

1. **Ad LLM-ə getmir** (`anonymize`): borclular «Şagird 1», «Şagird 2» olur, xərc
   qeydləri atılır. Real ad yalnız rəhbərin kompüterində, cavab gələndən SONRA
   qaytarılır (`deanonymize`).
2. **Rəqəm uydurulmur** (`ground_report`): hesabatda xülasədə olmayan rəqəm daşıyan
   cümlə atılır. Pul hesabatında «təxminən 1 800 AZN» səhv qərar deməkdir.
3. **SQL yalnız oxuyur** (`safe_query`): sorğu xülasədən qurulan yaddaşdakı surətə
   gedir (real bazaya yox), sqlite `authorizer` yalnız SELECT/oxumaya icazə verir,
   bir ifadə, sətir limiti və addım limiti var.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

STUDENT = "Şagird"
_ALIAS = re.compile(rf"\b{STUDENT} (\d+)\b")
_THOUSANDS = re.compile(r"(?<=\d)[  ](?=\d{3}\b)")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_LIST_MARKER = re.compile(r"^\s*(?:[-*]|\d{1,2}[.)])\s+")


@dataclass
class Anonymized:
    summary: dict
    names: dict[str, str] = field(default_factory=dict)   # «Şagird 1» → real ad


def anonymize(summary: dict) -> Anonymized:
    """Borcluların adını ləqəblə əvəz edir, `student_id` və xərc qeydini atır."""
    names: dict[str, str] = {}
    debtors = []
    for i, d in enumerate(summary.get("debtors", []), start=1):
        alias = f"{STUDENT} {i}"
        names[alias] = d["display_name"]
        debtors.append({k: v for k, v in d.items() if k not in ("display_name", "student_id")}
                       | {"student": alias})
    expenses = [{"month": x["month"], "category": x["category"], "amount": x["amount"]}
                for x in summary.get("expenses", [])]
    return Anonymized({**summary, "debtors": debtors, "expenses": expenses}, names)


def deanonymize(text: str, names: dict[str, str]) -> str:
    return _ALIAS.sub(lambda m: names.get(m.group(0), m.group(0)), text)


def _numbers(text: str) -> set[str]:
    flat = _THOUSANDS.sub("", text)
    return {n.replace(",", ".") for n in _NUMBER.findall(flat)}


def _canon(number: str) -> str:
    value = float(number)
    return str(int(value)) if value == int(value) else f"{value:.2f}".rstrip("0").rstrip(".")


def alias_names(text: str, names: dict[str, str]) -> str:
    """Rəhbərin sualındakı real adları ləqəbə çevirir (uzun ad əvvəl: «Əli Məmmədov» «Əli»dən qabaq)."""
    for alias, name in sorted(names.items(), key=lambda kv: -len(kv[1])):
        if name.strip():
            text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", alias, text, flags=re.IGNORECASE)
    return text


def numbers_in(text: str) -> set[str]:
    """Mətndəki rəqəmlər kanonik formada («1 200» = «1200», «12,50» = «12.5»)."""
    return {_canon(n) for n in _numbers(text)}


def allowed_numbers(summary: dict) -> set[str]:
    """Hesabatda yazıla bilən rəqəmlər: xülasədəki hər ədəd, faizlər, saylar, ay və il."""
    found: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            found.add(_canon(str(value)))
        elif isinstance(value, str):
            found.update(_canon(n) for n in _numbers(value))
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(summary)
    rate = summary.get("collection_rate")
    if rate is not None:
        found.update({_canon(str(round(rate * 100))), _canon(str(round(rate * 100, 1)))})
    for month in summary.get("trend", []):
        if month.get("expected"):
            found.add(_canon(str(round(month["collected"] / month["expected"] * 100))))
    debtors = summary.get("debtors", [])
    found.update({str(len(debtors)), str(sum(1 for d in debtors if d.get("likely_left"))),
                  str(len(summary.get("by_chat", []))), str(len(summary.get("trend", []))),
                  str(len(debtors) + summary.get("students_without_fee", 0))})
    found.update(str(i) for i in range(1, len(debtors) + 1))   # «Şagird 3» ləqəbləri
    return found


def grounded(text: str, allowed: set[str]) -> bool:
    return numbers_in(_ALIAS.sub("", _LIST_MARKER.sub("", text))) <= allowed   # «Şagird 3» rəqəm deyil


def ground_report(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    """Mənbədə olmayan rəqəm daşıyan sətir/cümləni atır: (təmiz mətn, atılanlar)."""
    kept_lines, dropped = [], []
    for line in text.splitlines():
        marker = _LIST_MARKER.match(line)                # «2. Şagird 2: ...» bölünəndə «2.» cümlə sayılmasın
        prefix = marker.group(0) if marker else ""
        parts = [p for p in re.split(r"(?<=[.!?])\s+", line[len(prefix):]) if p.strip()]
        if not parts:
            kept_lines.append(line)
            continue
        good = [p for p in parts if grounded(p, allowed)]
        dropped += [p for p in parts if p not in good]
        if good:
            kept_lines.append(prefix + " ".join(good))
    return "\n".join(kept_lines).strip(), dropped


def facts_text(anon: dict) -> str:
    """Agentlərə verilən fakt vərəqi: yalnız anonim xülasədəki rəqəmlər."""
    rate = anon.get("collection_rate")
    lines = [
        f"Ay: {anon['month']}",
        f"Gözlənilən gəlir: {anon['expected']} AZN; yığılan: {anon['collected']} AZN; "
        f"borc: {anon['outstanding']} AZN; yığım faizi: {'-' if rate is None else round(rate * 100)}%",
        f"Xərclər: {anon['expenses_total']} AZN; xalis qalıq: {anon['net']} AZN",
        f"Aylıq məbləği təyin olunmamış tələbə: {anon.get('students_without_fee', 0)}",
        "Qruplar: " + "; ".join(f"{c['chat_name']}: {c['students']} tələbə, {c['collected']}/{c['expected']} AZN"
                                for c in anon.get("by_chat", [])),
        "Xərc kateqoriyaları: " + "; ".join(f"{c['category']} {c['amount']} AZN"
                                             for c in anon.get("expenses_by_category", [])),
        "Son aylar (ay: yığılan/gözlənilən, xərc, xalis): " + "; ".join(
            f"{t['month']}: {t['collected']}/{t['expected']}, {t['expenses']}, {t['net']}"
            for t in anon.get("trend", [])),
        f"Borclular ({len(anon.get('debtors', []))}):",
    ]
    for d in anon.get("debtors", []):
        lines.append(f"- {d['student']} ({d['chat_name']}): {d['amount']} AZN, {d['days_overdue']} gün gecikir, "
                     f"{d['unpaid_months']} aydır ödəmir, son ödəniş {d['last_paid_month'] or 'yoxdur'}"
                     + (", ehtimal ki, kursu tərk edib" if d.get("likely_left") else ""))
    return "\n".join(lines)


# ---------- yalnız oxuyan SQL ----------

SCHEMA = """
summary(month, expected, collected, outstanding, collection_rate, expenses_total, net, students_without_fee)
groups(grup, students, expected, collected)
debtors(student, grup, amount, days_overdue, unpaid_months, last_paid_month, likely_left)
months(month, expected, collected, expenses, net)
expenses(month, category, amount)
Pul AZN ilə tam ədəddir, ay 'YYYY-AA' mətnidir, likely_left 0/1.
""".strip()

MAX_ROWS = 200
MAX_STEPS = 200_000


class QueryRejected(ValueError):
    pass


def snapshot_db(anon: dict) -> sqlite3.Connection:
    """Anonim xülasədən yaddaşda cədvəllər. Real bazaya heç bir bağlantı yoxdur."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript("""
        CREATE TABLE summary(month TEXT, expected INT, collected INT, outstanding INT, collection_rate REAL,
                             expenses_total INT, net INT, students_without_fee INT);
        CREATE TABLE groups(grup TEXT, students INT, expected INT, collected INT);
        CREATE TABLE debtors(student TEXT, grup TEXT, amount INT, days_overdue INT, unpaid_months INT,
                             last_paid_month TEXT, likely_left INT);
        CREATE TABLE months(month TEXT, expected INT, collected INT, expenses INT, net INT);
        CREATE TABLE expenses(month TEXT, category TEXT, amount INT);
    """)
    conn.execute("INSERT INTO summary VALUES (?,?,?,?,?,?,?,?)", (
        anon["month"], anon["expected"], anon["collected"], anon["outstanding"], anon.get("collection_rate"),
        anon["expenses_total"], anon["net"], anon.get("students_without_fee", 0)))
    conn.executemany("INSERT INTO groups VALUES (?,?,?,?)", [
        (c["chat_name"], c["students"], c["expected"], c["collected"]) for c in anon.get("by_chat", [])])
    conn.executemany("INSERT INTO debtors VALUES (?,?,?,?,?,?,?)", [
        (d["student"], d["chat_name"], d["amount"], d["days_overdue"], d["unpaid_months"], d["last_paid_month"],
         int(bool(d.get("likely_left")))) for d in anon.get("debtors", [])])
    conn.executemany("INSERT INTO months VALUES (?,?,?,?,?)", [
        (t["month"], t["expected"], t["collected"], t["expenses"], t["net"]) for t in anon.get("trend", [])])
    conn.executemany("INSERT INTO expenses VALUES (?,?,?)", [
        (x["month"], x["category"], x["amount"]) for x in anon.get("expenses", [])])
    conn.commit()
    return conn


_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
_ALLOWED_ACTIONS |= {getattr(sqlite3, "SQLITE_RECURSIVE", 33)}   # WITH RECURSIVE


def _authorizer(action, *_args):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def safe_query(conn: sqlite3.Connection, sql: str, *, max_rows: int = MAX_ROWS) -> tuple[list[str], list[tuple], bool]:
    """(sütunlar, sətirlər, kəsildimi). Yazma, ATTACH, PRAGMA, çox ifadə → `QueryRejected`."""
    statement = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", statement):
        raise QueryRejected("Yalnız SELECT sorğusu icazəlidir")
    if ";" in statement:
        raise QueryRejected("Bir sorğuda yalnız bir ifadə ola bilər")
    steps = {"n": 0}

    def progress() -> int:
        steps["n"] += 1
        return 1 if steps["n"] * 1000 > MAX_STEPS else 0

    conn.set_authorizer(_authorizer)
    conn.set_progress_handler(progress, 1000)
    try:
        cursor = conn.execute(statement)
        rows = cursor.fetchmany(max_rows + 1)
        columns = [c[0] for c in cursor.description or []]
    except sqlite3.DatabaseError as exc:
        raise QueryRejected(f"Sorğu icra olunmadı: {exc}") from exc
    finally:
        conn.set_authorizer(None)
        conn.set_progress_handler(None, 0)
    return columns, rows[:max_rows], len(rows) > max_rows


def format_rows(columns: list[str], rows: list[tuple], truncated: bool) -> str:
    if not rows:
        return "(nəticə boşdur)"
    lines = [" | ".join(columns)] + [" | ".join("" if v is None else str(v) for v in row) for row in rows]
    return "\n".join(lines) + (f"\n(ilk {len(rows)} sətir)" if truncated else "")
