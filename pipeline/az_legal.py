"""Azərbaycan qanunvericilik mətnlərinin ortaq naxışları.

Bir yerdə saxlanılır ki, iki fərqli məqsəd (mətn təmizləmə və sual
auditi) eyni tərifdən istifadə etsin və vaxtla bir-birindən ayrılmasın.
"""

from __future__ import annotations

import re

# Qanun düzəlişinin nömrəsi: «504-IIIQD», «420‑IIIQD», «1234-VQD».
#
# DİQQƏT: e-qanun.az adi defis (U+002D) YOX, U+2011 (non-breaking
# hyphen) işlədir. Digər tire variantları da ehtimal olunur, ona görə
# hamısı qəbul edilir. Bunu nəzərə almasaq naxış sükutla keçib gedir —
# real sualda məhz belə olmuşdu.
AMENDMENT_NUMBER_RE = re.compile(
    r"\d{2,4}\s*[-‐‑‒–—]?\s*[IVX]{1,5}\s*Q[DK]",
    re.IGNORECASE,
)
