"""Canlı video dərs üçün LiveKit giriş tokeni (Classroom, gün 2).

Video LiveKit Cloud-dadır: serverimiz yalnız qısaömürlü giriş tokeni
imzalayır, media trafiki bizim 2 GB-lıq maşından keçmir. Token LiveKit-in
öz formatıdır (HS256 JWT, `video` qrantı) - ayrıca SDK paketinə ehtiyac
yoxdur, `PyJWT` onsuz da asılılıqdadır.

Açarlar `.env`-dədir: `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
`LIVEKIT_API_SECRET`. Biri yoxdursa video söndürülmüş sayılır.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import jwt


@dataclass(frozen=True)
class LiveKitConfig:
    url: str
    api_key: str
    api_secret: str


def livekit_config(env=os.environ) -> LiveKitConfig | None:
    url = env.get("LIVEKIT_URL", "").strip()
    key = env.get("LIVEKIT_API_KEY", "").strip()
    secret = env.get("LIVEKIT_API_SECRET", "").strip()
    if not (url and key and secret):
        return None
    return LiveKitConfig(url=url, api_key=key, api_secret=secret)


def lesson_room(lesson_id: int) -> str:
    return f"masterai-lesson-{lesson_id}"


def make_join_token(
    config: LiveKitConfig,
    *,
    room: str,
    identity: str,
    name: str,
    is_host: bool,
    ttl_seconds: int,
    now: float | None = None,
) -> str:
    """Müəllim otağın idarəçisidir (tələbənin mikrofonunu bağlaya bilər).
    Tələbə də yayımlaya bilir: sual vermək üçün mikrofon lazımdır."""
    issued = int(now if now is not None else time.time())
    claims = {
        "iss": config.api_key,
        "sub": identity,
        "name": name,
        "nbf": issued - 10,
        "exp": issued + ttl_seconds,
        "video": {
            "room": room,
            "roomJoin": True,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
            "roomAdmin": is_host,
        },
        "metadata": '{"role": "%s"}' % ("teacher" if is_host else "student"),
    }
    return jwt.encode(claims, config.api_secret, algorithm="HS256")
