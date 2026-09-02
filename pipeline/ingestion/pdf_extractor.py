from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource, RawMaterial


def extract(source: MaterialSource) -> RawMaterial:
    path = Path(source.location)
    if not path.exists():
        raise IngestionError(f"PDF fayl tapılmadı: {source.location}")

    try:
        reader = PdfReader(str(path))
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise IngestionError(f"PDF oxuna bilmədi (sınıq fayl?): {source.location}") from exc

    text = "\n".join(pages_text).strip()
    if not text:
        raise IngestionError(f"PDF-dən mətn çıxarıla bilmədi: {source.location}")

    return RawMaterial(text=text, metadata={"pages": len(reader.pages)})
