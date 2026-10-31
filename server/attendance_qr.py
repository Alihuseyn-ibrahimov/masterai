"""Sinifdə QR davamiyyəti (MasterAI Classroom, gün 6).

Müəllimin ekranındakı QR kod hər `WINDOW_SECONDS`-dan bir dəyişir. Kod
dərsin ID-si və vaxt pəncərəsindən HMAC ilə törənir, bazada saxlanmır.
Cari və əvvəlki pəncərə qəbul olunur: skan anında kod dəyişsə tələbə
yenə keçir, amma şəkli dostuna göndərmək bir dəqiqədən sonra işləmir.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import time

import segno

WINDOW_SECONDS = 30
DEFAULT_SITE_URL = "https://masterai.prdostu.com"


def site_url() -> str:
    return os.environ.get("SITE_URL", DEFAULT_SITE_URL).rstrip("/")


def _window(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // WINDOW_SECONDS)


def make_code(secret: str, lesson_id: int, *, now: float | None = None) -> str:
    return _code(secret, lesson_id, _window(now))


def _code(secret: str, lesson_id: int, window: int) -> str:
    digest = hmac.new(secret.encode(), f"lesson-qr:{lesson_id}:{window}".encode(), hashlib.sha256).digest()
    return base64.b32encode(digest).decode()[:10]


def verify_code(secret: str, lesson_id: int, code: str, *, now: float | None = None) -> bool:
    code = (code or "").strip().upper()
    if not code:
        return False
    window = _window(now)
    return any(hmac.compare_digest(code, _code(secret, lesson_id, w)) for w in (window, window - 1))


def seconds_left(now: float | None = None) -> int:
    now = time.time() if now is None else now
    return max(1, int(WINDOW_SECONDS - now % WINDOW_SECONDS))


def join_url(lesson_id: int, code: str) -> str:
    return f"{site_url()}/dersim.html?id={lesson_id}&qr={code}"


def qr_svg(data: str) -> str:
    buffer = io.BytesIO()
    segno.make(data, error="m").save(buffer, kind="svg", scale=1, border=2, xmldecl=False,
                                     svgns=True, omitsize=True, dark="#000", light="#fff")
    return buffer.getvalue().decode()
