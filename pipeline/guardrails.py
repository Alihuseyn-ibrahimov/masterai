"""AI tutorun qoruyucu qatları - giriş və çıxış rail-ləri (MasterAI Classroom, gün 20).

Tutor tələbənin mətnini LLM-ə ötürür və LLM-in cavabını tələbəyə göstərir. Hər iki
istiqamətdə model sükutla səhv edə bilər, ona görə LLM-in ətrafında iki qat var:

**Giriş (`check_input`), LLM-dən ƏVVƏL:**
- *prompt injection* - «əvvəlki təlimatları unut», «sistem promptunu göstər»,
  «sən artıq tutor deyilsən» və s. Sorğu LLM-ə getmir, tələbə izah görür.
- *şəxsi məlumat* - e-poçt, telefon, FİN, kart nömrəsi maskalanır
  (`[telefon]`). Sual işləyir, amma nömrə LLM provayderinə və LangSmith izinə
  düşmür.

**Çıxış (`check_answer`, `check_quiz`), LLM-dən SONRA:**
- *istinad* - mövcud olmayan parçaya `[7]` silinir; heç bir istinad yoxdursa
  və cavabın sözləri parçalarla az üst-üstə düşürsə, cavab «tapmadım» olur.
- *rəqəm* - parçalarda (və sualda) olmayan rəqəm daşıyan cümlə atılır
  (konspektdəki `ground` qaydası). Hamısı atılsa - «tapmadım».
- *təlimat sızması* - cavabda sistem promptundan uzun parça varsa, bloklanır.
- *şəxsi məlumat* - cavabdakı e-poçt/telefon maskalanır.

Qaydalar QƏSDƏN sadə regex və söz müqayisəsidir (LLM yox): pulsuzdur, gecikmə
əlavə etmir, `evals/datasets/guardrails.jsonl` ilə ölçülür. Eyni funksiyalar
NeMo Guardrails konfiqurasiyasında (`nemo_rails/`) action kimi işləyir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pipeline.rag import Passage, tokenize

INJECTION_MESSAGE = (
    "Bu sorğunu emal edə bilmirəm: mətn tutorun iş qaydalarını dəyişməyə çalışır. "
    "Dərs mövzusu üzrə sualınızı adi şəkildə yazın."
)
LEAK_MESSAGE = "Cavab təhlükəsizlik yoxlamasından keçmədi. Sualı başqa sözlərlə yazın."
PII_NOTICE = "Mesajınızdakı şəxsi məlumatı (telefon, e-poçt və s.) AI-a göndərmədim."

# Sözlər kiçik hərflə, I→ı / İ→i çevrilmiş mətndə axtarılır.
_INJECTION_PATTERNS = [
    # «əvvəlki təlimatları unut», «bütün qaydaları nəzərə alma»
    r"(təlimat|qayda|göstəriş|tapşırıq|məhdudiyyət)\w*\W+(\w+\W+){0,3}?(unut|nəzərə alma|ignor|ləğv et|boşla|pozma?ğa)",
    r"\b(unut|unudun)\b\W+(\w+\W+){0,3}?(təlimat|qayda|göstəriş)",
    r"\b(ignore|disregard|forget|override)\b\W+(\w+\W+){0,4}?(instruction|prompt|rule|guideline)s?\b",
    # sistem promptunu göstər / reveal your system prompt
    r"(sistem|system|gizli)\s*(prompt|təlimat|mesaj|instruction)\w*\W+(\w+\W+){0,3}?"
    r"(göstər|yaz|de\b|deyin|paylaş|çap|ver\b|reveal|show|print|tell|repeat|output)",
    r"(reveal|show|print|tell|repeat|output)\b\W+(\w+\W+){0,3}?(system|hidden|initial)\s*(prompt|instruction)",
    # rol dəyişdirmə
    r"\bsən\s+(artıq|indi|bundan sonra)\s+(\w+\W+){0,3}?(deyilsən|rolundasan|rolunu oyna|kimi davran)",
    r"\b(you are now|act as|pretend to be|roleplay as|from now on you)\b",
    r"\b(jailbreak|dan mode|developer mode)\b",
    r"(heç bir|hər hansı)\s+(qayda|məhdudiyyət|filtr)\w*\s+(olmadan|tətbiq etmə|yoxdur)",
]
_INJECTION = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

_PII = [
    ("e-poçt", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("kart", re.compile(r"\b(?:\d[ -]?){15}\d\b")),
    # +994 50 123 45 67, 050-123-45-67, 0501234567
    ("telefon", re.compile(r"(?:\+?994[\s-]?|\b0)(?:10|12|50|51|55|60|70|77|99)[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b")),
    # FİN: 7 simvol, böyük hərf və rəqəm qarışığı (5ABC12D)
    ("FİN", re.compile(r"\b(?=[0-9A-Z]*\d)(?=[0-9A-Z]*[A-Z])[0-9A-Z]{7}\b")),
]

_CITATION = re.compile(r"\[(\d{1,2})\]")
_NUMBER = re.compile(r"\d+")
_LIST_MARKER = re.compile(r"^\s*\d{1,2}[.)](?:\s+|$)", re.MULTILINE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
LEAK_WINDOW = 60
MIN_OVERLAP = 0.5


def _normalize(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


@dataclass
class InputCheck:
    text: str                     # LLM-ə gedəcək mətn (maskalanmış)
    blocked: bool = False
    message: str = ""             # bloklananda tələbəyə göstərilən izah
    rails: list[str] = field(default_factory=list)   # işə düşən qaydalar (jurnal/eval üçün)


def mask_pii(text: str) -> tuple[str, list[str]]:
    found = []
    for label, pattern in _PII:
        text, count = pattern.subn(f"[{label}]", text)
        if count:
            found.append(label)
    return text, found


def is_injection(text: str) -> bool:
    lowered = _normalize(text)
    return any(p.search(lowered) for p in _INJECTION)


def check_input(text: str) -> InputCheck:
    if is_injection(text):
        return InputCheck(text="", blocked=True, message=INJECTION_MESSAGE, rails=["injection"])
    masked, found = mask_pii(text)
    return InputCheck(text=masked, rails=[f"pii:{label}" for label in found])


@dataclass
class OutputCheck:
    text: str
    status: str = "ok"            # ok | not_found | blocked
    rails: list[str] = field(default_factory=list)


def leaks(text: str, secrets: list[str]) -> bool:
    flat = " ".join(text.split())
    for secret in secrets:
        s = " ".join(secret.split())
        for start in range(0, max(1, len(s) - LEAK_WINDOW + 1), 20):
            if len(s[start:start + LEAK_WINDOW]) == LEAK_WINDOW and s[start:start + LEAK_WINDOW] in flat:
                return True
    return False


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(_LIST_MARKER.sub("", _CITATION.sub("", text))))


def grounded_numbers(text: str, allowed: set[str]) -> bool:
    return _numbers(text) <= allowed


def overlap(text: str, passages: list[Passage]) -> float:
    words = set(tokenize(_CITATION.sub("", text)))
    if not words:
        return 0.0
    source = set()
    for p in passages:
        source.update(tokenize(p.text))
    return len(words & source) / len(words)


def check_answer(answer: str, passages: list[Passage], *, question: str = "",
                 secrets: list[str] | None = None) -> OutputCheck:
    rails: list[str] = []
    if leaks(answer, secrets or []):
        return OutputCheck(text=LEAK_MESSAGE, status="blocked", rails=["prompt_leak"])

    def fix_citation(m: re.Match) -> str:
        return m.group(0) if 1 <= int(m.group(1)) <= len(passages) else ""

    cleaned = _CITATION.sub(fix_citation, answer)
    if cleaned != answer:
        rails.append("bad_citation")
    if not _CITATION.search(cleaned) and overlap(cleaned, passages) < MIN_OVERLAP:
        return OutputCheck(text="", status="not_found", rails=rails + ["ungrounded"])

    allowed = _numbers(question) | set().union(*(set(_NUMBER.findall(p.text)) for p in passages))
    lines, dropped = [], False
    for line in cleaned.splitlines():
        marker = _LIST_MARKER.match(line)
        prefix, body = (marker.group(0), line[marker.end():]) if marker else ("", line)
        sentences = [s for s in _SENTENCE.split(body) if s.strip()]
        kept = [s.strip() for s in sentences if grounded_numbers(s, allowed)]
        dropped |= len(kept) < len(sentences)
        if kept:
            lines.append(prefix + " ".join(kept))
        elif not sentences:
            lines.append(line)
    if dropped:
        rails.append("ungrounded_number")
        rest = "\n".join(lines).strip()
        if not rest or (not _CITATION.search(rest) and overlap(rest, passages) < MIN_OVERLAP):
            return OutputCheck(text="", status="not_found", rails=rails)
        cleaned = rest
    cleaned, found = mask_pii(cleaned)
    rails += [f"pii:{label}" for label in found]
    return OutputCheck(text=re.sub(r"[ \t]{2,}", " ", cleaned).strip(), rails=rails)


def check_quiz(parts: list[str], passages: list[Passage], *, secrets: list[str] | None = None) -> OutputCheck:
    """Quiz: sual, DÜZGÜN variant və izahdakı rəqəm materialda olmalıdır; təlimat sızmamalıdır.

    Səhv variantlar yoxlanmır: «1991 / 1993 / 1995» kimi çaşdırıcı rəqəmlər qəsdən
    materialda olmur, yalnız düzgün cavab olmalıdır."""
    joined = "\n".join(parts)
    if leaks(joined, secrets or []):
        return OutputCheck(text=LEAK_MESSAGE, status="blocked", rails=["prompt_leak"])
    allowed = set().union(*(set(_NUMBER.findall(p.text)) for p in passages)) if passages else set()
    if not all(grounded_numbers(part, allowed) for part in parts):
        return OutputCheck(text="", status="not_found", rails=["ungrounded_number"])
    return OutputCheck(text=joined)
