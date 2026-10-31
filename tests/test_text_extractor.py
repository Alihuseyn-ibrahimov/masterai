import pytest

from pipeline.ingestion import text_extractor
from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource
from pipeline.pipeline import _extract
from pipeline.summary import _extract_text


def test_reads_transcript_file_through_both_pipelines(tmp_path):
    path = tmp_path / "lesson.txt"
    path.write_text("  Konstitusiya əsas qanundur.\n", encoding="utf-8")
    source = MaterialSource(kind="text", location=str(path))
    assert _extract(source).text == "Konstitusiya əsas qanundur."
    assert _extract_text(source) == "Konstitusiya əsas qanundur."


def test_missing_or_empty_file_is_ingestion_error(tmp_path):
    with pytest.raises(IngestionError):
        text_extractor.extract(MaterialSource(kind="text", location=str(tmp_path / "yox.txt")))
    empty = tmp_path / "bos.txt"
    empty.write_text("   ", encoding="utf-8")
    with pytest.raises(IngestionError):
        text_extractor.extract(MaterialSource(kind="text", location=str(empty)))
