"""Kurs Kassası, addım 5: ödəniş mətnindən (bank SMS-i, qəbz, valideyn mesajı) strukturlu JSON.

Axın: `read_receipt(text, complete)` əvvəl LLM-ə verir (produksiyada fine-tune
olunmuş Qwen2.5-1.5B vLLM-də, bax `ml/qlora_receipts.ipynb`), cavabı yoxlayır,
alınmasa qaydalı oxuyucuya (`rule_based`) düşür.

**Uydurmaya qarşı (`grounded`):** hər sahə mətndə olmalıdır. Məbləğ mətndə yoxdursa
LLM cavabı tamamilə rədd olunur (pul məsələsində təxmin olmaz); ad, kart, tarix
mətndə tapılmırsa həmin sahə `null` edilir. Ayın adı və şagird adı sərbəst
yazıla bilər, ona görə onlar normallaşdırılmış mətndə axtarılır.

Nəticə HEÇ VAXT avtomatik «ödədi» yazmır: Kassa onu rəhbərə təklif kimi göstərir
(açıq cavabın AI balı ilə eyni prinsip).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avqust", "sentyabr",
          "oktyabr", "noyabr", "dekabr"]

SYSTEM_PROMPT = (
    "Sən hazırlıq kursunun kassa köməkçisisən. Sənə ödəniş haqqında mətn verilir: bank SMS-i, "
    "köçürmə bildirişi, kağız qəbzin OCR mətni və ya valideynin mesajı. YALNIZ bir JSON obyekti "
    "qaytar, başqa heç nə yazma:\n"
    '{"amount": ödənilən məbləğ (ədəd, AZN), "date": "YYYY-AA-GG" və ya null, '
    '"payer": ödəyənin adı mətndə necə yazılıbsa və ya null, "card_last4": "4 rəqəm" və ya null, '
    '"month": hansı ay üçün (1-12) və ya null, "student": şagirdin adı adlıq halda (soyadsız) '
    "və ya null}\n"
    "Qaydalar: balans, qalıq və komissiya ödəniş məbləği DEYİL. Maskalı ad (A*** B***) null-dur. "
    "Mətndə olmayan heç nəyi uydurma, bilmədiyin sahəyə null yaz."
)


def user_prompt(text: str) -> str:
    return f"<mətn>\n{text.strip()}\n</mətn>"


class Receipt(BaseModel):
    amount: float = Field(gt=0, le=100000)
    date: str | None = None
    payer: str | None = None
    card_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    month: int | None = Field(default=None, ge=1, le=12)
    student: str | None = None

    @field_validator("date")
    @classmethod
    def _iso_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        date.fromisoformat(value)  # səhv tarix ValidationError olur
        return value

    @field_validator("payer", "student")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None


class ReceiptError(ValueError):
    pass


_ASCII = str.maketrans("əƏıİöÖüÜşŞçÇğĞ", "eEiIoOuUsScCgG")


def normalize(text: str) -> str:
    """Müqayisə üçün: kiçik hərf, Azərbaycan hərfləri latın qarşılığına (OCR və bank SMS-i
    diakritiki itirir), artıq boşluqlar silinir."""
    return " ".join(text.translate(_ASCII).lower().split())


def parse_reply(reply: str) -> Receipt:
    """Model cavabından JSON obyekti (```json bloku və ətrafındakı mətn atılır)."""
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if not match:
        raise ReceiptError("cavabda JSON yoxdur")
    try:
        return Receipt.model_validate(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ReceiptError(f"JSON oxunmadı: {exc.__class__.__name__}") from exc


def _amount_forms(amount: float) -> list[str]:
    forms = [f"{amount:.2f}", f"{amount:.2f}".replace(".", ",")]
    if amount == int(amount):
        forms.append(str(int(amount)))
    return forms


def _date_forms(iso: str) -> list[str]:
    d = date.fromisoformat(iso)
    return [d.strftime("%d.%m.%Y"), iso, d.strftime("%d/%m/%Y"), f"{d.day} {MONTHS[d.month - 1]} {d.year}"]


def grounded(receipt: Receipt, text: str) -> tuple[Receipt | None, list[str]]:
    """Mətndə olmayan sahələri atır. Məbləğ yoxdursa bütün cavab rədd olunur (`None`)."""
    norm = normalize(text)
    numbers = set(re.findall(r"\d+(?:[.,]\d+)?", text))
    problems = []
    if not any(f in numbers for f in _amount_forms(receipt.amount)):
        return None, ["amount"]
    data = receipt.model_dump()
    if receipt.date and not any(f in text for f in _date_forms(receipt.date)):
        data["date"], _ = None, problems.append("date")
    if receipt.card_last4 and receipt.card_last4 not in text:
        data["card_last4"], _ = None, problems.append("card_last4")
    for field in ("payer", "student"):
        value = data[field]
        if value and normalize(value) not in norm and normalize(value)[:4] not in norm:
            data[field], _ = None, problems.append(field)
    if receipt.month and MONTHS[receipt.month - 1][:3] not in norm:
        data["month"], _ = None, problems.append("month")
    return Receipt.model_validate(data), problems


# ---------- qaydalı oxuyucu (LLM-siz baza və ehtiyat yol) ----------

_CURRENCY = r"(?:AZN|manat|₼)"
_AMOUNT_RE = re.compile(rf"(?:{_CURRENCY}\s*(\d+(?:[.,]\d{{1,2}})?))|(?:(\d+(?:[.,]\d{{1,2}})?)\s*{_CURRENCY})")
_DISTRACTOR = re.compile(r"(balans|qalıq|qaliq|komissiya)", re.IGNORECASE)
_DATE_RES = [
    (re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b"), lambda m: (m[3], m[2], m[1])),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: (m[1], m[2], m[3])),
    (re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"), lambda m: (m[3], m[2], m[1])),
]
_WORD_DATE = re.compile(rf"\b(\d{{1,2}}) ({'|'.join(MONTHS)}) (\d{{4}})\b", re.IGNORECASE)
_CARD_RES = [re.compile(r"\*\s?(\d{4})\b"), re.compile(r"son 4 rəqəmi (\d{4})"),
             re.compile(r"\*{4} (\d{4})\b")]
_PAYER_RE = re.compile(r"(?:G[öo]nd[əe]r[əe]n|[ÖO]d[əe]y[əe]n):\s*([^\n|]+)", re.IGNORECASE)
_STUDENT_RES = [re.compile(r"(?:Şagird|Sagird):\s*(\S+)", re.IGNORECASE),
                re.compile(r"(?:Təyinat|Teyinat|Qeyd|Şərh|Serh):\s*([A-ZƏÖÜİŞÇĞ][^\s,|]+)")]
_GENITIVE = re.compile(r"\b([A-ZƏÖÜİŞÇĞ][a-zəöüışçğ]+(?:ın|in|un|ün))\b")
_VOWELS = "aıoueəiöü"


def _nominative(word: str) -> str:
    """«Ayselin» → «Aysel», «Lalənin» → «Lalə», «Kamranın» → «Kamran» (n saitdən sonra
    bitişdiricidir, samitdən sonra adın öz hərfidir)."""
    stem = word[:-2]
    if len(stem) > 2 and stem[-1] == "n" and stem[-2] in _VOWELS:
        return stem[:-1]
    return stem
_FOR = re.compile(r"\b([A-ZƏÖÜİŞÇĞ][a-zəöüışçğ]+) üçün")


def _amount(text: str) -> float | None:
    for line in text.replace("|", "\n").replace(". ", "\n").splitlines():
        if _DISTRACTOR.search(line):
            continue
        for m in _AMOUNT_RE.finditer(line):
            return float((m[1] or m[2]).replace(",", "."))
    return None


def _date(text: str) -> tuple[str | None, str]:
    for pattern, parts in _DATE_RES:
        m = pattern.search(text)
        if m:
            y, mo, d = parts(m)
            try:
                return date(int(y), int(mo), int(d)).isoformat(), text.replace(m[0], " ")
            except ValueError:
                continue
    m = _WORD_DATE.search(text)
    if m:
        d = date(int(m[3]), MONTHS.index(m[2].lower()) + 1, int(m[1]))
        return d.isoformat(), text.replace(m[0], " ")
    return None, text


def rule_based(text: str) -> Receipt | None:
    amount = _amount(text)
    if amount is None or amount <= 0:
        return None
    iso, rest = _date(text)
    card = next((m[1] for p in _CARD_RES if (m := p.search(rest))), None)
    payer = None
    if m := _PAYER_RE.search(text):
        candidate = m[1].strip()
        payer = None if "*" in candidate else candidate
    elif m := re.search(r"daxil oldu\. ([A-Z][A-Z ]+[A-Z])\.", text):
        payer = m[1]
    elif "|" in text:
        parts = [p.strip() for p in text.split("|")]
        for i, part in enumerate(parts):
            if re.fullmatch(r"[A-Z]+ [A-Z]+", part):
                payer = part
                if i + 1 < len(parts) and re.match(r"[A-ZƏÖÜİŞÇĞ][a-zəöüışçğ]+", parts[i + 1]):
                    student_hint = parts[i + 1].split()[0]
                    text = text + f"\nŞagird: {student_hint}"
                break
    norm_rest = normalize(rest)
    month = next((i + 1 for i, name in enumerate(MONTHS) if re.search(rf"\b{name}", norm_rest)), None)
    student = None
    for pattern in _STUDENT_RES:
        if m := pattern.search(text):
            student = m[1].strip(",.")
            break
    if student is None and (m := _GENITIVE.search(text)):
        student = _nominative(m[1])
    if student is None and (m := _FOR.search(text)):
        student = m[1]
    if student and student.lower() in MONTHS:
        student = None
    return Receipt(amount=amount, date=iso, payer=payer, card_last4=card, month=month, student=student)


Complete = Callable[[str, str], str]


def production_complete() -> Complete | None:
    """Produksiya LLM-i, yoxdursa `None` (qaydalı oxuyucu işləyir).

    Qəbzdə ad, kartın son rəqəmləri var. Ona görə defolt olaraq YALNIZ öz vLLM
    serverimiz (`VLLM_BASE_URL` + `VLLM_RECEIPT_MODEL`, məs. multi-LoRA adapteri
    `receipts`) çağırılır: mətn bizim GPU-dan kənara çıxmır. Groq/Claude yalnız
    `RECEIPT_ALLOW_EXTERNAL_LLM=true` olanda qoşulur.
    """
    from pipeline.providers import DEFAULT_ORDER, build_completers, complete_with_fallback
    from pipeline.providers import openai_compatible_completer

    completers: dict = {}
    base_url = os.environ.get("VLLM_BASE_URL", "").rstrip("/")
    model = os.environ.get("VLLM_RECEIPT_MODEL", "")
    if base_url and model:
        completers["vllm"] = openai_compatible_completer(
            base_url, model, api_key=os.environ.get("VLLM_API_KEY", ""), timeout=30, max_tokens=256)
    if os.environ.get("RECEIPT_ALLOW_EXTERNAL_LLM", "").lower() == "true":
        completers = {**{k: v for k, v in build_completers().items() if k != "vllm"}, **completers}
    if not completers:
        return None
    order = ["vllm"] + [name for name in DEFAULT_ORDER if name != "vllm"]
    return lambda system, user: complete_with_fallback(system, user, order, completers)


def read_receipt(text: str, complete: Complete | None = None) -> tuple[Receipt | None, str, list[str]]:
    """(nəticə, mənbə: `llm` | `rules` | `none`, atılan sahələr)."""
    if complete is not None:
        try:
            parsed = parse_reply(complete(SYSTEM_PROMPT, user_prompt(text)))
            checked, problems = grounded(parsed, text)
            if checked is not None:
                return checked, "llm", problems
        except ReceiptError:
            pass
        except Exception:  # provayder xətası: qaydalı yola düş, Kassa işləməyə davam etsin
            pass
    result = rule_based(text)
    return result, ("rules" if result else "none"), []
