"""Riyazi addımları sympy ilə modeldən ASILI OLMAYARAQ yoxlamaq.

Səhv Detektivi reposundan (`sehv/hybrid.py` + `verify.to_expr`, v3) köçürülüb, məntiq
dəyişməyib. Niyə? Kiçik model hesabda səhv edə bilər (7·8 = 54-ü düz sayar), sympy yox.
Golden dəstdə sympy 46/100 nümunəni oxuyur və hamısında etiketlə üst-üstə düşür
(`tests/test_sehv_detektivi.py` bunu qoruyur).

Bu qat həm də MODEL OLMAYANDA ehtiyat yoldur: adapter qoşulmayıbsa, riyazi zəncir
oxunursa cavabı sympy verir, oxunmursa nəticə «yoxlanmadı»dır, «düzgündür» YOX.

check_math_steps(steps) -> dict | None
    None: addımlar riyazi kimi oxunmadı (söz məsələsi, məntiq və s.), qərar modeldədir.
"""

from __future__ import annotations

import re

_MATH = re.compile(r"^[0-9x\s+\-−–*/·×:÷().,%²³^=]+$")
_PREFIX = re.compile(r"^\s*(cavab|deməli|yəni|onda|nəticə)\s*:?\s*", re.I)
_UNIT = re.compile(r"\s*(manat|gün|dəqiqə|saniyə|m|sm|kq|ədəd|səhifə)\.?\s*$", re.I)
_SUBS = {"·": "*", "×": "*", "÷": "/", "−": "-", "–": "-", ",": ".", "^": "**"}


def _sympy():
    """sympy serverdə olmasa (köhnə venv) yoxlama sadəcə söndürülür, servis sınmır."""
    try:
        import sympy
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )
    except ImportError:
        return None
    return sympy, parse_expr, standard_transformations + (implicit_multiplication_application,)


def to_expr(s, local=None):
    sp, parse_expr, transformations = _sympy()
    if isinstance(s, (int, float)):
        return sp.nsimplify(s)
    s = str(s).strip()
    for a, b in _SUBS.items():
        s = s.replace(a, b)
    s = s.replace("%", "/100")
    return parse_expr(s, transformations=transformations, local_dict=local or {})


def _clean(step: str) -> str | None:
    s = _PREFIX.sub("", step.strip())
    s = _UNIT.sub("", s).replace("²", "**2").replace("³", "**3")
    s = re.sub(r"(?<=[\d)])\s*:\s*(\d+/\d+)", r"/(\1)", s)  # kəsrə bölmə: 1/3 : 5/4 → 1/3/(5/4)
    s = re.sub(r"(?<=[\d)])\s*:\s*(?=[\d(−-])", "/", s)  # 12 : 4, (8 + 4) : 2 → /
    s = re.sub(r"(\d+)\s+(\d+/\d+)", r"(\1+\2)", s)  # qarışıq kəsr: 2 1/3 → (2+1/3)
    return s if s and _MATH.match(s) else None


def check_math_steps(steps: list[str], domain: str = "riyaziyyat") -> dict | None:
    if domain != "riyaziyyat" or _sympy() is None:
        return None
    sp = _sympy()[0]

    def val(s):
        return sp.nsimplify(to_expr(s), rational=True)

    clean = [_clean(s) for s in steps]
    parsed = [c for c in clean if c]
    if len(parsed) < 2 or clean[0] is None:
        return None
    x = sp.Symbol("x")
    try:
        if "x" in clean[0] and "=" in clean[0]:  # tənlik: hər addımın həlli eyni olmalıdır
            def sol(c):
                if "=" not in c:
                    return None
                left, right = c.split("=", 1)
                return frozenset(sp.solve(sp.Eq(to_expr(left, {"x": x}), to_expr(right, {"x": x})), x))
            ref = sol(clean[0])
            for i, c in enumerate(clean[1:], start=2):
                if c and "x" in c and sol(c) != ref:
                    return {"wrong_step": i, "mode": "equation", "reference": [str(v) for v in ref]}
            return {"wrong_step": None, "mode": "equation", "reference": [str(v) for v in ref]}
        if "=" in clean[0]:
            # Söz məsələsi: addımlar fərqli kəmiyyətlərdir, yalnız "a = b" hesablarını yoxlaya bilərik.
            # Hamısı doğrudursa belə məntiqi səhv (məs. faiz bazası) ola bilər → qərar modeldə qalır.
            for i, c in enumerate(clean, start=1):
                if c and "=" in c:
                    parts = [p for p in c.split("=") if p.strip()]
                    if len(parts) >= 2 and any(sp.simplify(val(a) - val(b)) != 0 for a, b in zip(parts, parts[1:])):
                        return {"wrong_step": i, "mode": "claims", "reference": None}
            return None
        # İfadə zənciri: hər addımdakı hər hissə ilkin ifadənin qiymətinə bərabər olmalıdır.
        ref = val(clean[0])
        for i, c in enumerate(clean, start=1):
            if not c:
                continue
            for part in (p for p in c.split("=") if p.strip()):
                if sp.simplify(val(part) - ref) != 0:
                    return {"wrong_step": i, "mode": "value", "reference": str(ref)}
        return {"wrong_step": None, "mode": "value", "reference": str(ref)}
    except Exception:
        return None
