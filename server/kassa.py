"""Kurs Kassası: bir ayın pul mənzərəsi (saf funksiyalar, baza yoxdur).

Spec: docs/superpowers/specs/2026-11-15-kurs-kassasi-design.md (addım 2).

Girişlər `app.py`-də store-lardan yığılır, burada yalnız hesablanır, ona görə
hər qayda kiçik testlə yoxlanır:

- **Gözlənilən gəlir** = ay bitməzdən ƏVVƏL qoşulmuş və aylıq məbləği təyin
  olunmuş hər (qrup, tələbə) cütünün məbləği. Məbləği olmayan tələbə borca
  düşmür: uydurma borc göstərmək yanlış olardı (`PaymentRow` ilə eyni qayda).
- **Yığılan** = bu ay üçün qeyd olunmuş ödənişlərin cəmi (`month`-a görə,
  çünki kassa «oktyabrın pulu gəldimi?» sualına cavab verir).
- **Borc** = ödənməmiş cütlər. Hər biri üçün neçə gün gecikib və ardıcıl neçə
  aydır ödəmir. 2+ ay ödəməyən tələbə çox vaxt artıq gedib: bunu panel ayrıca
  işarələyir (churn modeli sonra bunu ƏVVƏLCƏDƏN deyəcək).
- **Xalis** = yığılan - xərclər.

Məlum sadələşdirmə: məbləğ dəyişibsə, keçmiş ayların «gözlənilən» dəyəri
cari məbləğlə hesablanır (`payment_fees` tarixçə saxlamır). Ödəniş qeydləri
özləri dəyişmir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

EXPENSE_CATEGORIES = ("Müəllim maaşı", "İcarə", "Reklam", "Kommunal", "Digər")
TREND_MONTHS = 6
LIKELY_LEFT_MONTHS = 2


@dataclass(frozen=True)
class Enrollment:
    chat_id: int
    chat_name: str
    student_id: int
    display_name: str
    joined_at: str
    monthly_amount: int | None


def month_start(month: str) -> datetime:
    year, mon = month.split("-")
    return datetime(int(year), int(mon), 1, tzinfo=timezone.utc)


def next_month(month: str) -> str:
    start = month_start(month)
    nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt.strftime("%Y-%m")


def prev_month(month: str) -> str:
    return (month_start(month) - timedelta(days=1)).strftime("%Y-%m")


def months_back(month: str, count: int) -> list[str]:
    """`count` ay, köhnədən yeniyə, sonuncusu `month`."""
    out = [month]
    while len(out) < count:
        out.insert(0, prev_month(out[0]))
    return out


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _billable(e: Enrollment, month: str) -> bool:
    return e.monthly_amount is not None and _parse(e.joined_at) < month_start(next_month(month))


def summarize(
    month: str,
    now: datetime,
    enrollments: list[Enrollment],
    records: list[dict],
    expenses: list[dict],
) -> dict:
    """`records` və `expenses` ən azı son `TREND_MONTHS` ayı əhatə etməlidir."""
    paid: dict[tuple[int, int, str], dict] = {
        (r["chat_id"], r["student_id"], r["month"]): r for r in records
    }
    trend_months = months_back(month, TREND_MONTHS)

    def month_totals(m: str) -> dict:
        billable = [e for e in enrollments if _billable(e, m)]
        expected = sum(e.monthly_amount for e in billable)
        collected = sum(r["amount"] for r in records if r["month"] == m)
        spent = sum(x["amount"] for x in expenses if x["month"] == m)
        return {"month": m, "expected": expected, "collected": collected, "expenses": spent,
                "net": collected - spent}

    debtors = []
    by_chat: dict[int, dict] = {}
    end_of_month = month_start(next_month(month))
    as_of = min(now, end_of_month)
    for e in enrollments:
        if not _billable(e, month):
            continue
        chat = by_chat.setdefault(e.chat_id, {"chat_id": e.chat_id, "chat_name": e.chat_name,
                                              "students": 0, "expected": 0, "collected": 0})
        chat["students"] += 1
        chat["expected"] += e.monthly_amount
        record = paid.get((e.chat_id, e.student_id, month))
        if record:
            chat["collected"] += record["amount"]
            continue
        due_from = max(month_start(month), _parse(e.joined_at))
        streak, m = 0, month
        while _billable(e, m) and (e.chat_id, e.student_id, m) not in paid:
            streak += 1
            m = prev_month(m)
            if streak >= 12:
                break
        last_paid = max((r["month"] for r in records
                         if r["chat_id"] == e.chat_id and r["student_id"] == e.student_id), default=None)
        debtors.append({
            "chat_id": e.chat_id, "chat_name": e.chat_name, "student_id": e.student_id,
            "display_name": e.display_name, "amount": e.monthly_amount,
            "days_overdue": max(0, (as_of - due_from).days),
            "unpaid_months": streak,
            "last_paid_month": last_paid,
            "likely_left": streak >= LIKELY_LEFT_MONTHS,
        })
    debtors.sort(key=lambda d: (-d["unpaid_months"], -d["days_overdue"], d["display_name"]))

    totals = month_totals(month)
    by_category: dict[str, int] = defaultdict(int)
    for x in expenses:
        if x["month"] == month:
            by_category[x["category"]] += x["amount"]
    rate = round(totals["collected"] / totals["expected"], 4) if totals["expected"] else None
    return {
        "month": month,
        "expected": totals["expected"],
        "collected": totals["collected"],
        "outstanding": sum(d["amount"] for d in debtors),
        "collection_rate": rate,
        "expenses_total": totals["expenses"],
        "net": totals["net"],
        "debtors": debtors,
        "by_chat": sorted(by_chat.values(), key=lambda c: c["chat_name"] or ""),
        "expenses_by_category": [{"category": k, "amount": v} for k, v in sorted(by_category.items())],
        "expenses": [x for x in expenses if x["month"] == month],
        "trend": [month_totals(m) for m in trend_months],
        "students_without_fee": sum(1 for e in enrollments if e.monthly_amount is None),
    }


# ---- Qəbz oxuyucusu (addım 5): oxunmuş qəbzi qeydiyyatdakı şagirdə bağla ----

_ASCII = str.maketrans("əƏıİöÖüÜşŞçÇğĞ", "eEiIoOuUsScCgG")


def _norm(text: str) -> str:
    return " ".join(str(text).translate(_ASCII).lower().split())


def _family(name: str) -> str:
    """Soyadın kişi/qadın formasını eyniləşdirir: «Əliyeva» → «eliyev»."""
    token = _norm(name).split()[-1] if _norm(name) else ""
    return token[:-1] if token.endswith(("ova", "eva", "yeva")) else token


def match_receipt(student: str | None, payer: str | None,
                  enrollments: list[Enrollment], limit: int = 5) -> list[Enrollment]:
    """Qəbzdəki şagird adına uyğun qeydiyyatlar, ən ehtimallısı əvvəl.

    Ad (ilk söz) üst-üstə düşməlidir; ödəyənin soyadı da şagirdinki ilə eynidirsə
    (valideyn) yuxarı qalxır. Ad yoxdursa namizəd YOXDUR: rəhbər özü seçir, sistem
    pulu təxmini birinə yazmır.
    """
    if not student:
        return []
    first = _norm(student).split()[0]
    family = _family(payer) if payer else ""
    scored = []
    for e in enrollments:
        tokens = _norm(e.display_name).split()
        if not tokens or tokens[0] != first:
            continue
        bonus = 1 if family and len(tokens) > 1 and _family(e.display_name) == family else 0
        scored.append((-bonus, e.display_name, e.chat_id, e))
    scored.sort(key=lambda item: item[:3])
    return [item[3] for item in scored[:limit]]


def receipt_month(month: int | None, paid_on: str | None, today: str) -> str:
    """Qəbzin aid olduğu ay «YYYY-AA». İl ödəniş tarixindən (yoxdursa bu gündən)
    götürülür, ilin sonu/başı keçidi düzəldilir: 28 dekabrda «yanvar» gələn il,
    3 yanvarda «dekabr» keçən ildir."""
    anchor = paid_on or today
    year, anchor_month = int(anchor[:4]), int(anchor[5:7])
    if month is None:
        return f"{year:04d}-{anchor_month:02d}"
    if month - anchor_month > 6:
        year -= 1
    elif anchor_month - month > 6:
        year += 1
    return f"{year:04d}-{month:02d}"
