"""Sinif lövhəsinin şəkli → mətn (MasterAI Classroom, gün 7).

Material yükləmədəki OCR-dan fərqi telefon şəklinə uyğunlaşmasıdır:
- EXIF istiqaməti tətbiq olunur: telefon şəkli çox vaxt «yan» saxlanır,
  tesseract döndərilmiş mətni oxumur;
- boz rəngə keçirilir və ~2400 px-ə kiçildilir: 12 MP şəkil 1 nüvəli
  serverdə dəqiqələrlə emal olunardı, bu ölçüdə lövhə yazısı oxunaqlı qalır.
"""

from __future__ import annotations

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from pipeline.ingestion.errors import IngestionError

OCR_LANGUAGES = "aze+eng"
MAX_SIDE = 2400


def prepare(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    return image


def read_board(path: str) -> str:
    try:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(prepare(image), lang=OCR_LANGUAGES)
    except UnidentifiedImageError as exc:
        raise IngestionError("Şəkil oxuna bilmədi") from exc
    except pytesseract.TesseractError as exc:
        raise IngestionError("OCR uğursuz oldu") from exc
    text = text.strip()
    if not text:
        raise IngestionError("Şəkildə yazı tanınmadı. Lövhəni yaxından və düz çəkin.")
    return text
