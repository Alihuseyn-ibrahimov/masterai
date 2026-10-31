"""Test sualının ədədi əlamətləri - çətinlik modeli üçün (MasterAI Classroom, gün 15).

AI hər suala «asan/orta/çətin» yazır, amma bu, modelin TƏXMİNİDİR. Əsl çətinlik
tələbələrin cavablarındadır: sualı neçə faiz düzgün cavablayıb. Çətinlik modeli
(`difficulty_model.py`) sualın mətnindən bu faizi proqnozlaşdırır; bu modul
mətni modelin oxuya biləcəyi rəqəmlərə çevirir.

Əlamətlər QƏSDƏN sadə və izah oluna biləndir (embedding yox): server 1 nüvəlidir,
müəllim isə «niyə çətin?» sualına cavab görməlidir. Ardıcıllıq `FEATURES`-dədir və
dəyişməməlidir - köhnə model faylı yeni sıranı oxuya bilməz (`difficulty_model`
fayldakı siyahını yoxlayır).
"""

from __future__ import annotations

import math
import re

from pipeline.models import MCQQuestion

FEATURES = [
    "stem_chars_log",        # sual mətninin uzunluğu (log)
    "stem_words",            # söz sayı / 10
    "option_chars_log",      # variantların orta uzunluğu (log)
    "option_len_cv",         # variant uzunluqlarının dəyişkənliyi (std / orta)
    "correct_len_ratio",     # düzgün variant / səhvlərin ortası (uzun = özünü verir)
    "stem_has_number",       # sualda rəqəm var
    "numeric_options",       # variantların neçə hissəsi rəqəmdir (tarix, say)
    "negation",              # «deyil», «olmayan», «istisna» - tələbələr tez-tez səhv oxuyur
    "stem_correct_overlap",  # sual və düzgün cavabın ortaq sözləri (ipucu)
    "stem_distractor_overlap",  # sual və ən yaxın səhv variantın ortaq sözləri
    "explanation_chars_log",
    "ai_asan",               # AI-nın öz qiyməti (one-hot; heç biri = qiymətsiz)
    "ai_orta",
    "ai_cetin",
]

_WORD = re.compile(r"\w+", re.UNICODE)
_NUMERIC = re.compile(r"^[\d\s.,%/:-]+(il|ildə|ci|cı|cu|cü|-ci|-cı|-cu|-cü)?$", re.IGNORECASE)
_NEGATION = re.compile(r"\b(deyil|olmayan|olmayıb|yoxdur|istisna|aid deyil|düzgün olmayan|səhv olan)\b",
                       re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    lowered = text.replace("I", "ı").replace("İ", "i").lower()
    return {w[:6] for w in _WORD.findall(lowered) if len(w) > 2}


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(b) if b else 0.0


def extract(question: MCQQuestion) -> list[float]:
    """`FEATURES` sırası ilə əlamətlər."""
    stem = question.question.strip()
    options = [o.strip() for o in question.options]
    lengths = [len(o) for o in options]
    mean_len = sum(lengths) / len(lengths)
    std_len = math.sqrt(sum((n - mean_len) ** 2 for n in lengths) / len(lengths))
    correct = lengths[question.correct_index]
    others = [n for i, n in enumerate(lengths) if i != question.correct_index]
    others_mean = sum(others) / len(others) if others else 0.0
    stem_tokens = _tokens(stem)
    option_tokens = [_tokens(o) for o in options]
    distractors = [t for i, t in enumerate(option_tokens) if i != question.correct_index]
    level = question.difficulty
    return [
        math.log1p(len(stem)),
        len(_WORD.findall(stem)) / 10,
        math.log1p(mean_len),
        std_len / mean_len if mean_len else 0.0,
        correct / others_mean if others_mean else 1.0,
        1.0 if re.search(r"\d", stem) else 0.0,
        sum(bool(_NUMERIC.match(o)) for o in options) / len(options),
        1.0 if _NEGATION.search(stem) else 0.0,
        _overlap(stem_tokens, option_tokens[question.correct_index]),
        max((_overlap(stem_tokens, t) for t in distractors), default=0.0),
        math.log1p(len(question.explanation or "")),
        1.0 if level == "asan" else 0.0,
        1.0 if level == "orta" else 0.0,
        1.0 if level == "çətin" else 0.0,
    ]
