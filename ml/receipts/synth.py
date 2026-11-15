"""Sintetik ödəniş mətnləri + düzgün cavab (etiket).

Real qəbz və SMS şəxsi məlumatdır, ona görə öyrətmə datası sintetikdir. Beş
«ailə» (mətn növü), hər birində bir neçə şablon:

- `bank_sms`: kartə mədaxil SMS-i (balans məbləği ÇAŞDIRICIDIR);
- `card2card`: kart-karta köçürmə bildirişi (maskalı kart nömrəsi);
- `cash_receipt`: kursun kağız qəbzi, OCR səhvləri ilə;
- `parent_message`: valideynin sərbəst mesajı («Ayselin noyabr pulunu köçürdüm»);
- `ewallet`: elektron pul kisəsi qəbzi (komissiya məbləği ÇAŞDIRICIDIR, ad maskalıdır);
- `messenger`: valideynin sərbəst, sahə adları qeyri-standart olan mesajı («Uşaq:», «Ana:»,
  «... ilə bitir»): qaydalar bu formatı tanımır.

Bank və kisə adları QƏSDƏN ümumidir (real brendin formatını təqlid etmirik).

Etiket sahələri (`FIELDS`):
- `amount`: ödənilən məbləğ, AZN (balans və komissiya YOX);
- `date`: ödəniş günü `YYYY-AA-GG`, mətndə yoxdursa `null`;
- `payer`: ödəyənin adı mətndə necə yazılıbsa (maskalıdırsa `null`);
- `card_last4`: kartın son 4 rəqəmi və ya `null`;
- `month`: hansı ay üçün (1-12), yazılmayıbsa `null`;
- `student`: şagirdin ADI (soyadsız), adlıq halda («Ayselin» → «Aysel»).

`HELD_OUT` ailələri öyrətməyə düşmür: model görmədiyi formatda da işləyirmi?
"""

from __future__ import annotations

import random
from datetime import date, timedelta

FIELDS = ["amount", "date", "payer", "card_last4", "month", "student"]
FAMILIES = ["bank_sms", "card2card", "cash_receipt", "parent_message", "ewallet", "messenger"]
# Öyrətməyə düşməyən ailələr: model (və qaydalar) bu formatları heç görməyib.
HELD_OUT = ("ewallet", "messenger")

FIRST = ["Aysel", "Murad", "Nigar", "Elvin", "Leyla", "Rauf", "Günay", "Tural", "Səbinə", "Orxan",
         "Nərmin", "Kamran", "Fidan", "Ülvi", "Aytən", "Rəşad", "Kənan", "Lalə", "Zaur", "Aynur",
         "Fərid", "Gülnar", "Emin", "Sevinc", "Vüsal", "Könül", "Nihad", "Şəbnəm", "Cavid", "Ülkər"]
LAST = ["Məmmədov", "Əliyev", "Həsənov", "Hüseynov", "Quliyev", "İsmayılov", "Abbasov", "Rzayev",
        "Kərimov", "Nəsirov", "Bağırov", "Cəfərov", "Mustafayev", "Orucov", "Səfərov"]
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avqust", "sentyabr",
          "oktyabr", "noyabr", "dekabr"]
FEES = [50, 60, 70, 80, 90, 100, 110, 120, 130, 150, 180, 200, 240]

_ASCII = str.maketrans("əƏıİöÖüÜşŞçÇğĞ", "eEiIoOuUsScCgG")
_FRONT = set("eəiöü")


def ascii_upper(name: str) -> str:
    """Bank SMS-ləri adları çox vaxt latın böyük hərflə yazır: «Məmmədov» → «MAMMADOV»."""
    return name.translate(str.maketrans("əƏ", "aA")).translate(_ASCII).upper()


def genitive(name: str) -> str:
    """«Aysel» → «Ayselin», «Lalə» → «Lalənin», «Murad» → «Muradın» (ahəng qanunu)."""
    vowels = [c for c in name.lower() if c in "aıoueəiöü"]
    last = vowels[-1] if vowels else "a"
    if last in "ou":
        suffix = "un"
    elif last in "öü":
        suffix = "ün"
    elif last in _FRONT:
        suffix = "in"
    else:
        suffix = "ın"
    return name + ("n" if name[-1].lower() in "aıoueəiöü" else "") + suffix


def _amount_text(rng: random.Random, amount: float, style: int) -> str:
    whole = f"{amount:.2f}"
    if amount != int(amount) and style % 6 in (2, 4):
        style = 0  # qəpikli məbləğ tam ədəd kimi yazılmasın: etiket mətnlə ziddiyyət təşkil edərdi
    return [f"{whole} AZN", f"{whole.replace('.', ',')} AZN", f"{int(amount)} manat",
            f"{whole} ₼", f"{int(amount)} AZN", f"AZN {whole}"][style % 6]


def _date_text(d: date, style: int) -> str:
    return [d.strftime("%d.%m.%Y"), d.isoformat(), d.strftime("%d/%m/%Y"),
            f"{d.day} {MONTHS[d.month - 1]} {d.year}"][style % 4]


def _ocr(rng: random.Random, text: str, rate: float) -> str:
    """Kağız qəbzin OCR səhvləri: oxşar hərflər, itən diakritik. Rəqəmlərə toxunmur ki,
    etiket mətnlə ziddiyyət təşkil etməsin."""
    swaps = {"ə": "e", "ı": "i", "ş": "s", "ç": "c", "ü": "u", "ö": "o", "ğ": "g", "Ə": "E", "Ş": "S"}
    return "".join(swaps[ch] if ch in swaps and rng.random() < rate else ch for ch in text)


FEMALE = {"Aysel", "Nigar", "Leyla", "Günay", "Səbinə", "Nərmin", "Fidan", "Aytən", "Lalə", "Aynur",
          "Gülnar", "Sevinc", "Könül", "Şəbnəm", "Ülkər"}


def _surname(first: str, surname: str) -> str:
    return surname + "a" if first in FEMALE else surname


def _person(rng: random.Random) -> tuple[str, str, str]:
    """(şagird adı, valideyn adı, ailə soyadı - kişi forması)."""
    return rng.choice(FIRST), rng.choice(FIRST), rng.choice(LAST)


def az_capitalize(text: str) -> str:
    """«iyul» → «İyul» (`str.capitalize` «Iyul» yazır: Azərbaycan əlifbasında i-nin böyüyü İ-dir)."""
    return ("İ" if text[:1] == "i" else text[:1].upper()) + text[1:]


def _month_phrase(rng: random.Random, month: int) -> str:
    name = MONTHS[month - 1]
    return rng.choice([f"{name} ayı", f"{name} ayı üçün", name, az_capitalize(name),
                       f"{name} ayının haqqı"])


def _bank_sms(rng, amount, d, student, parent, surname, month, card, style):
    payer = f"{ascii_upper(parent)} {ascii_upper(_surname(parent, surname))}"
    balance = round(amount + rng.uniform(20, 3000), 2)
    purpose = f"{student} {MONTHS[month - 1]}" if month else student
    variants = [
        f"Mədaxil: {_amount_text(rng, amount, style)}\nKart: *{card}\nGöndərən: {payer}\n"
        f"Təyinat: {purpose}\nTarix: {_date_text(d, 0)} {rng.randint(8, 22):02d}:{rng.randint(0, 59):02d}\n"
        f"Balans: {balance:.2f} AZN",
        f"Kartınıza *{card} {_amount_text(rng, amount, style)} daxil oldu. {payer}. "
        f"{_date_text(d, 0)}. Qalıq: {balance:.2f} AZN. Qeyd: {purpose}",
        f"BANK: +{amount:.2f} AZN | *{card} | {_date_text(d, 1)} | {payer} | {purpose} | "
        f"Mövcud balans {balance:.2f} AZN",
    ]
    return variants[style % len(variants)], {"payer": payer, "card_last4": card}


def _card2card(rng, amount, d, student, parent, surname, month, card, style):
    masked = f"{rng.randint(4000, 5599)} {rng.randint(10, 99)}** **** {card}"
    note = f"{student} {MONTHS[month - 1]}" if month else student
    variants = [
        f"Kart-karta köçürmə uğurla tamamlandı. Məbləğ {_amount_text(rng, amount, style)}, "
        f"alıcı kart {masked}, {_date_text(d, style)}. Qeyd: {note}",
        f"Köçürmə: {_amount_text(rng, amount, style)}\nAlıcı: {masked}\nTarix: {_date_text(d, style)}\n"
        f"Status: Uğurlu\nŞərh: {note}",
    ]
    return variants[style % len(variants)], {"payer": None, "card_last4": card}


def _cash_receipt(rng, amount, d, student, parent, surname, month, card, style):
    payer = f"{parent} {_surname(parent, surname)}"
    month_line = f"{_month_phrase(rng, month)} təhsil haqqı" if month else "təhsil haqqı"
    text = (f"QƏBZ № {rng.randint(100, 9999):04d}\nTarix: {_date_text(d, style)}\n"
            f"Ödəyən: {payer}\nŞagird: {student} {_surname(student, surname)}\n"
            f"Məbləğ: {_amount_text(rng, amount, style)}\nTəyinat: {month_line}\n"
            f"Kassir: {rng.choice(FIRST)} {rng.choice(LAST)[0]}.")
    text = _ocr(rng, text, rate=0.15 if style % 2 else 0.0)
    return text, {"payer": payer, "card_last4": None}


def _parent_message(rng, amount, d, student, parent, surname, month, card, style):
    gen = genitive(student)
    month_bit = f"{MONTHS[month - 1]} " if month else ""
    card_bit = rng.choice(["", f" Kartın son 4 rəqəmi {card}.", f" *{card} kartından."])
    variants = [
        f"Salam müəllim, {gen} {month_bit}pulunu köçürdüm, {_amount_text(rng, amount, style)}.{card_bit}",
        f"Salam! {student} üçün {_month_phrase(rng, month) + ' ' if month else ''}"
        f"{_amount_text(rng, amount, style)} göndərdim.{card_bit} Sağ olun",
        f"Müəllim salam, bu gün {_amount_text(rng, amount, style)} atdım, {gen} "
        f"{month_bit}haqqıdır.{card_bit}",
    ]
    return variants[style % len(variants)], {"payer": None,
                                            "card_last4": card if card_bit else None}


def _ewallet(rng, amount, d, student, parent, surname, month, card, style):
    fee = round(amount * rng.choice([0.005, 0.01, 0.015]), 2)
    masked = f"{parent[0]}*** {surname[0]}***"
    note = f"\nTəyinat: {student}, {MONTHS[month - 1]}" if month else f"\nTəyinat: {student}"
    text = (f"Ödəniş qəbzi\nƏməliyyat ID: {rng.randint(10**9, 10**10 - 1)}\n"
            f"Məbləğ: {_amount_text(rng, amount, style)}\nKomissiya: {fee:.2f} AZN\n"
            f"Tarix: {_date_text(d, style)}\nGöndərən: {masked}{note}")
    return text, {"payer": None, "card_last4": None}


def _messenger(rng, amount, d, student, parent, surname, month, card, style):
    month_bit = f"{MONTHS[month - 1]} ayının ödənişidir" if month else "kurs ödənişidir"
    if style % 2 == 0:
        text = (f"{az_capitalize(month_bit)}: {_amount_text(rng, amount, style)}. {_date_text(d, style)} "
                f"kartla keçirdim, kart {card} ilə bitir. Uşaq: {student}")
        return text, {"payer": None, "card_last4": card}
    payer = f"{parent} {_surname(parent, surname)}"
    who = "Ana" if parent in FEMALE else "Ata"
    month_name = f" ({MONTHS[month - 1]})" if month else ""
    text = (f"{student}{month_name} - {_amount_text(rng, amount, style)}, ödədim {_date_text(d, style)}. "
            f"{who}: {payer}")
    return text, {"payer": payer, "card_last4": None}


_BUILDERS = {"bank_sms": _bank_sms, "card2card": _card2card, "cash_receipt": _cash_receipt,
             "parent_message": _parent_message, "ewallet": _ewallet, "messenger": _messenger}


def sample(rng: random.Random, family: str) -> dict:
    amount = float(rng.choice(FEES)) + rng.choice([0, 0, 0, 0.5, 0.25])
    d = date(2026, 1, 1) + timedelta(days=rng.randint(0, 364))
    student, parent, surname = _person(rng)
    month = rng.choice([d.month, d.month, (d.month % 12) + 1, None])
    card = f"{rng.randint(0, 9999):04d}"
    style = rng.randint(0, 11)
    text, extra = _BUILDERS[family](rng, amount, d, student, parent, surname, month, card, style)
    has_date = family != "parent_message"
    label = {
        "amount": amount,
        "date": d.isoformat() if has_date else None,
        "payer": extra["payer"],
        "card_last4": extra["card_last4"],
        "month": month,
        "student": student,
    }
    return {"family": family, "text": text, "label": label}


def generate(n_per_family: int = 200, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    return [sample(rng, family) for family in FAMILIES for _ in range(n_per_family)]
