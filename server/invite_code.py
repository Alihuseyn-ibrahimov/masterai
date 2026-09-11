"""Çat dəvət kodu — generator və normallaşdırma.

NİYƏ AYRICA MODUL: kodun əlifbası və uzunluğu təhlükəsizlik qərarıdır,
`ChatStore`-un CRUD məntiqinə qarışmamalıdır. Burada saf funksiyalardır
— DOM, DB və şəbəkə yoxdur, ona görə birbaşa test edilir.

NİYƏ KOD ÜMUMİYYƏTLƏ LAZIMDIR: əvvəl çata `POST /chats/{id}/join` ilə
qoşulurdular və çat ID-ləri `AUTOINCREMENT`, yəni ARDICIL. Təxmin də
lazım deyildi — 1-dən saymaqla sistemdəki bütün qrup çatlarına girmək
olurdu. Təsdiq tək başına bunu bağlamır: ardıcıl ID hər çata istək spam
etməyə imkan verir.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence

# Oxşar simvollar QƏSDƏN yoxdur: `0/O` və `1/I/L`. Müəllim kodu sinifə
# SƏSLƏ deyir — «sıfır yoxsa O» sualı olmamalıdır.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

CODE_LENGTH = 6

# Göstərişdə iki qrupa bölünür (`K7M-3QX`): səslə deyiləndə və əl ilə
# yazılanda qrup ayrımı səhvi azaldır. Saxlanan dəyər DEFİSSİZDİR.
_GROUP_SIZE = 3


def generate_code(choose: Callable[[Sequence[str]], str] = secrets.choice) -> str:
    """Təsadüfi kod.

    `choose` yalnız test üçün inyeksiya olunur; real istifadədə
    `secrets.choice` — `random` DEYİL, çünki kod təhlükəsizlik
    elementidir.
    """
    return "".join(choose(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def format_code(code: str) -> str:
    """Göstəriş üçün: `K7M3QX` → `K7M-3QX`."""
    return f"{code[:_GROUP_SIZE]}-{code[_GROUP_SIZE:]}"


def normalize_code(raw: str | None) -> str:
    """İstifadəçinin yazdığını saxlanan formata gətirir.

    Tələbə kodu kiçik hərflə, defislə və ya boşluqlarla yaza bilər —
    bunların heç biri səhv sayılmamalıdır. Boş dəyər BOŞ SƏTİR qaytarır
    ki, çağıran onu «kod verilməyib» kimi ayırd etsin (boş sətirlə
    axtarış heç bir çatı tapmamalıdır).
    """
    if not raw:
        return ""
    return raw.strip().replace("-", "").replace(" ", "").upper()
