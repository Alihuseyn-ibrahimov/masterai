"""Yüklənən faylların diskə saxlanması — UUID-əsaslı adlandırma.

Orijinal fayl adı heç vaxt birbaşa fayl sisteminə yazılmır (yalnız uzantısı
saxlanılır) — path traversal qarşısı (bax material yükləmə spec, bölmə 4).
Ölçü limiti stream-li oxuma zamanı yoxlanılır, tam fayl yaddaşa/diskə
yüklənib sonra ölçüsünə baxılmır.
"""

from __future__ import annotations

import os
import uuid

from fastapi import UploadFile

_CHUNK_SIZE = 1024 * 1024  # 1 MB


class PayloadTooLarge(Exception):
    """Yüklənən fayl icazə verilən maksimum ölçünü aşdıqda atılır."""


async def save_upload(file: UploadFile, upload_dir: str, max_bytes: int) -> str:
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1]
    dest_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}{ext}")

    written = 0
    try:
        with open(dest_path, "wb") as out:
            while chunk := await file.read(_CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise PayloadTooLarge(f"Fayl ölçüsü {max_bytes} baytdan çoxdur")
                out.write(chunk)
    except PayloadTooLarge:
        os.remove(dest_path)
        raise

    return dest_path
