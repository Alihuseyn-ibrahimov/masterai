"""Dərs səsinin mətnə çevrilməsi (Classroom, gün 3).

Groq-un Whisper modeli işlədilir: Groq açarı onsuz da var və ayrıca
pullu xidmət lazım olmur (kurs dərsi #24). Brauzer dərsi 5 dəqiqəlik
müstəqil hissələrlə göndərir, ona görə hər fayl Groq-un ölçü
limitindən (25 MB) xeyli kiçikdir.
"""

from __future__ import annotations

import os


class TranscriptionError(RuntimeError):
    """Səs mətnə çevrilə bilmədi (açar yoxdur, API xətası, boş nəticə)."""


DEFAULT_WHISPER_MODEL = "whisper-large-v3"


def transcribe_audio(path: str, *, language: str = "az") -> str:
    from dotenv import load_dotenv

    load_dotenv()
    if not os.environ.get("GROQ_API_KEY"):
        raise TranscriptionError("GROQ_API_KEY yoxdur")
    import groq

    client = groq.Groq(api_key=os.environ["GROQ_API_KEY"])
    try:
        with open(path, "rb") as audio:
            result = client.audio.transcriptions.create(
                file=(os.path.basename(path), audio.read()),
                model=os.environ.get("GROQ_WHISPER_MODEL", DEFAULT_WHISPER_MODEL),
                language=language,
                response_format="text",
                temperature=0,
            )
    except Exception as exc:  # noqa: BLE001 - SDK-nın xəta iyerarxiyası geniş, mətn kifayətdir
        raise TranscriptionError(f"Whisper xətası: {exc}") from exc
    text = (result if isinstance(result, str) else getattr(result, "text", "")).strip()
    return text
