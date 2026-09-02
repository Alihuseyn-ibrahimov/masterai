"""Şifrə hash-ləməsi və JWT token məntiqi — təmiz funksiyalar (şəbəkəsiz).

Endpoint-lərdən ayrıdır ki, ayrıca test oluna bilsin. Naxış
dildostu/server/dildostu_server/auth.py-dən demək olar dəyişmədən
köçürülüb.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

_ALGORITHM = "HS256"

# Token ömrü — mobil tətbiq üçün uzun (istifadəçi hər dəfə giriş etməsin).
DEFAULT_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 90  # 90 gün


class InvalidToken(Exception):
    """Token etibarsız, vaxtı keçib və ya yanlış açarla imzalanıb."""


def hash_password(password: str) -> str:
    """bcrypt hash (öz duzu ilə). Nəticə saxlanmağa hazır sətrdir."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Şifrə hash-ə uyğundurmu. Xarab hash halında `False` (istisna atmır)."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def token_secret() -> str:
    """İmzalama açarı — `.env`-dəki `JWT_SECRET`.

    Təyin olunmayıbsa istisna atılır: təsadüfi/sabit defolt açar bütün
    tokenləri saxtalaşdırıla bilən edərdi.
    """
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET təyin olunmalıdır (ən azı 32 simvol) — bax .env.example")
    return secret


def create_token(
    user_id: int,
    *,
    secret: str,
    expires_in_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in_seconds),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_token(token: str, *, secret: str) -> int:
    """Tokeni doğrula və `user_id` qaytar. Etibarsızdırsa `InvalidToken`.

    `algorithms` açıq verilir — "alg: none" hücumunun qarşısını alır.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc

    subject = payload.get("sub")
    if subject is None:
        raise InvalidToken("token-də 'sub' yoxdur")
    try:
        return int(subject)
    except (TypeError, ValueError) as exc:
        raise InvalidToken("'sub' rəqəm deyil") from exc
