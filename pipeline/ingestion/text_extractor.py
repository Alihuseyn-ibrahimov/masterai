"""Hazır mətn faylı (Classroom, gün 4): dərsin Whisper transkripti.

Mətn onsuz da var, çıxarmaq lazım deyil - fayldan oxunur ki, sual və
xülasə pipeline-ı link/PDF/şəkil ilə EYNİ yoldan getsin.
"""

from pathlib import Path

from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource, RawMaterial


def extract(source: MaterialSource) -> RawMaterial:
    path = Path(source.location)
    if not path.exists():
        raise IngestionError(f"Mətn faylı tapılmadı: {source.location}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise IngestionError(f"Mətn faylı boşdur: {source.location}")
    return RawMaterial(text=text, metadata={"chars": len(text)})
