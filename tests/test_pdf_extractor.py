from pathlib import Path

import pytest

from pipeline.ingestion.errors import IngestionError
from pipeline.ingestion.pdf_extractor import extract
from pipeline.models import MaterialSource

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_text_from_valid_pdf():
    source = MaterialSource(kind="pdf", location=str(FIXTURES / "sample.pdf"))
    raw = extract(source)
    assert "Konstitusiya" in raw.text
    assert "Baki seheridir" in raw.text
    assert raw.metadata["pages"] == 1


def test_raises_on_missing_file():
    source = MaterialSource(kind="pdf", location=str(FIXTURES / "does_not_exist.pdf"))
    with pytest.raises(IngestionError):
        extract(source)


def test_raises_on_corrupt_pdf():
    source = MaterialSource(kind="pdf", location=str(FIXTURES / "corrupt.pdf"))
    with pytest.raises(IngestionError):
        extract(source)
