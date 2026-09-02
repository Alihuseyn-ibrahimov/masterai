from pathlib import Path

import pytesseract
from PIL import Image, UnidentifiedImageError

from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource, RawMaterial

_OCR_LANGUAGES = "aze+eng"


def extract(source: MaterialSource) -> RawMaterial:
    path = Path(source.location)
    if not path.exists():
        raise IngestionError(f"Şəkil fayl tapılmadı: {source.location}")

    try:
        image = Image.open(path)
        text = pytesseract.image_to_string(image, lang=_OCR_LANGUAGES)
    except UnidentifiedImageError as exc:
        raise IngestionError(f"Şəkil oxuna bilmədi: {source.location}") from exc
    except pytesseract.TesseractError as exc:
        raise IngestionError(f"OCR uğursuz oldu: {source.location}") from exc

    text = text.strip()
    if not text:
        raise IngestionError(f"Şəkildən mətn tanınmadı: {source.location}")

    return RawMaterial(text=text, metadata={"ocr_lang": _OCR_LANGUAGES})
