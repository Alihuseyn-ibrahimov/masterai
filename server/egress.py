"""Dərs videosunun yazılması (Faza 4 PR 2, 2026-11-07).

LiveKit Cloud-un Egress xidməti dərsi S3-uyğun bir "bucket"ə yazır -
LiveKit Cloud-un özü yerli diskə yaza bilmir (gün 2-nin video otağından
fərqli olaraq). `S3Upload`-un `endpoint`+`force_path_style` sahələri
DigitalOcean Spaces (və Minio/R2) kimi S3-uyğun xidmətlər üçündür, VPS
artıq DigitalOcean-dadır.

Açarlar `.env`-dədir: `EGRESS_S3_BUCKET`, `_REGION`, `_ACCESS_KEY`,
`_SECRET` (`_ENDPOINT`/`_FORCE_PATH_STYLE` DO Spaces üçün). Biri
yoxdursa video yazısı söndürülmüş sayılır - LiveKit video otağının
özü (`video.py::livekit_config`) kimi.

Server yalnız Egress-i başladır/dayandırır; faktiki fayl LiveKit-dən
birbaşa bucket-ə gedir, bizim 2 GB-lıq maşından keçmir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from livekit.api import TokenVerifier, WebhookReceiver
from livekit.protocol.egress import (
    EncodedFileOutput,
    EncodedFileType,
    RoomCompositeEgressRequest,
    S3Upload,
    StopEgressRequest,
)
from livekit.protocol.webhook import WebhookEvent

from .video import LiveKitConfig


@dataclass(frozen=True)
class EgressConfig:
    bucket: str
    region: str
    access_key: str
    secret: str
    endpoint: str = ""
    force_path_style: bool = True


def egress_config(env=os.environ) -> EgressConfig | None:
    bucket = env.get("EGRESS_S3_BUCKET", "").strip()
    region = env.get("EGRESS_S3_REGION", "").strip()
    access_key = env.get("EGRESS_S3_ACCESS_KEY", "").strip()
    secret = env.get("EGRESS_S3_SECRET", "").strip()
    if not (bucket and region and access_key and secret):
        return None
    return EgressConfig(
        bucket=bucket,
        region=region,
        access_key=access_key,
        secret=secret,
        endpoint=env.get("EGRESS_S3_ENDPOINT", "").strip(),
        force_path_style=env.get("EGRESS_S3_FORCE_PATH_STYLE", "true").strip().lower() != "false",
    )


def recording_filepath(lesson_id: int, started_at_seq: int) -> str:
    return f"lessons/{lesson_id}/{started_at_seq}.mp4"


async def start_recording(client, *, room: str, filepath: str, egress: EgressConfig) -> str:
    """Egress-i başladır, `egress_id` qaytarır (sonra dayandırmaq üçün).
    `client` LiveKit-in `LiveKitAPI` instansıdır (və ya testdə saxta)."""
    info = await client.egress.start_room_composite_egress(
        RoomCompositeEgressRequest(
            room_name=room,
            layout="speaker",
            file_outputs=[
                EncodedFileOutput(
                    file_type=EncodedFileType.MP4,
                    filepath=filepath,
                    s3=S3Upload(
                        access_key=egress.access_key,
                        secret=egress.secret,
                        region=egress.region,
                        bucket=egress.bucket,
                        endpoint=egress.endpoint,
                        force_path_style=egress.force_path_style,
                    ),
                )
            ],
        )
    )
    return info.egress_id


async def stop_recording(client, egress_id: str) -> None:
    await client.egress.stop_egress(StopEgressRequest(egress_id=egress_id))


def verify_webhook(livekit: LiveKitConfig, body: str, auth_header: str) -> WebhookEvent:
    """LiveKit-in Egress bildirişinin imzasını yoxlayır - imza səhvdirsə atır,
    yəni bu, kənardan saxta bildiriş göndərməyə qarşı qoruyur."""
    receiver = WebhookReceiver(TokenVerifier(livekit.api_key, livekit.api_secret))
    return receiver.receive(body, auth_header)
