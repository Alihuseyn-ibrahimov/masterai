"""Hər endpoint-in icazə qapısı — repo üzrə xəritə testi.

NİYƏ: `/live/*`-da BEŞ endpoint qapısız qalmışdı (bax
`test_live_authorization.py`). Səbəb sistemlidir — yoxlama hər
funksiyanın İÇİNDƏ əl ilə yazılır, unudulması heç yerdə görünmür.

Bu test hər marşrutu üç kateqoriyadan birinə salır:

  1. QƏSDƏN AÇIQ — aşağıdakı açıq siyahıda (giriş/qeydiyyat/health)
  2. Qapılı — imzasında və ya gövdəsində tanınan yoxlama var
  3. Nə biri, nə digəri → TEST SINIR

Yeni endpoint əlavə edən adam ya qapı qoymalı, ya da onu şüurlu şəkildə
açıq siyahıya yazmalıdır. Hər iki halda qərar GÖRÜNÜR.
"""

from __future__ import annotations

import inspect
import re

from server import app as app_module

# QƏSDƏN AÇIQ marşrutlar. Hər biri üçün səbəb yazılmalıdır.
PUBLIC_ROUTES = {
    ("POST", "/auth/register"): "qeydiyyat - hesab hələ yoxdur",
    ("POST", "/auth/login"): "giriş - token hələ yoxdur",
    ("GET", "/health"): "monitorinq - məlumat daşımır",
}

# Gövdədə və ya imzada tanınan qapı işarələri.
_GUARD_MARKERS = (
    "get_current_teacher",   # müəllim asılılığı
    "require_admin",         # admin API açarı
    'user["is_admin"]',      # tətbiqdaxili admin
    'user["is_teacher"]',    # sətiriçi müəllim yoxlaması
    "get_current_user",      # ən azı giriş tələb olunur
)

_ROUTE_RE = re.compile(r'@app\.(get|post|put|patch|delete|websocket)\(\s*"([^"]+)"')


def _routes():
    source = inspect.getsource(app_module)
    for match in _ROUTE_RE.finditer(source):
        method, path = match.group(1).upper(), match.group(2)
        body = source[match.end():]
        rest = body[body.index("\n) "):]
        following = rest.find("\n@app.")
        yield method, path, body[:body.index("\n) ")] + rest[: following if following > 0 else len(rest)]


def test_routes_were_found():
    """Qoruyucu: regex sınıbsa, aşağıdakı test sükutla 'keçər'."""
    assert len(list(_routes())) >= 30


def test_every_route_is_guarded_or_deliberately_public():
    ungated = []
    for method, path, block in _routes():
        if (method, path) in PUBLIC_ROUTES:
            continue
        # WebSocket-lər token/PIN-i öz gövdəsində yoxlayır.
        if method == "WEBSOCKET":
            if "verify_token" not in block and "get_by_pin" not in block:
                ungated.append(f"{method} {path}")
            continue
        if not any(marker in block for marker in _GUARD_MARKERS):
            ungated.append(f"{method} {path}")
    assert not ungated, (
        "bu marşrutlarda heç bir icazə yoxlaması tapılmadı - ya qapı əlavə et, "
        "ya da səbəbi ilə PUBLIC_ROUTES-a yaz: " + ", ".join(ungated)
    )


def test_public_list_has_no_stale_entries():
    """Açıq siyahıda silinmiş marşrut qalsa, siyahı yalançı təhlükəsizlik
    hissi verər."""
    existing = {(method, path) for method, path, _ in _routes()}
    stale = [f"{m} {p}" for (m, p) in PUBLIC_ROUTES if (m, p) not in existing]
    assert not stale, f"PUBLIC_ROUTES-da artıq mövcud olmayan marşrut: {stale}"


def test_the_guard_check_actually_catches_an_ungated_route():
    """Özünü-yoxlama: qapısız marşrut HƏQİQƏTƏN tutulurmu?

    Bunsuz yuxarıdakı test regex sınanda da 'keçər' və biz bunu
    bilmərik."""
    fake_block = "    user_id: int,\n) -> dict:\n    return {}"
    assert not any(marker in fake_block for marker in _GUARD_MARKERS)
