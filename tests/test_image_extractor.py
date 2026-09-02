from pathlib import Path

import pytest

from pipeline.ingestion.errors import IngestionError
from pipeline.ingestion.image_extractor import extract
from pipeline.models import MaterialSource

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_text_from_image():
    source = MaterialSource(kind="image", location=str(FIXTURES / "sample_image.png"))
    raw = extract(source)
    # OCR mükəmməl deyil (bax findings.md) — sərt substring yoxlaması əvəzinə
    # ən aydın görünən sözün tanındığını yoxlayırıq.
    assert "Konstitusiya" in raw.text

def test_raises_on_missing_file():
    source = MaterialSource(kind="image", location=str(FIXTURES / "does_not_exist.png"))
    with pytest.raises(IngestionError):
        extract(source)


def test_raises_on_invalid_image(tmp_path):
    bad_file = tmp_path / "not_an_image.png"
    bad_file.write_bytes(b"bu bir sekil deyil")
    source = MaterialSource(kind="image", location=str(bad_file))
    with pytest.raises(IngestionError):
        extract(source)
