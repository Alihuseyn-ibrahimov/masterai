import json

import pytest

from pipeline import cli
from pipeline.models import MaterialSource, MCQQuestion, PipelineResult
from pipeline.pipeline import PipelineError


def _fake_result(source: MaterialSource) -> PipelineResult:
    question = MCQQuestion(
        question="Test?",
        options=["A", "B", "C", "D", "E"],
        correct_index=0,
        explanation="izah",
    )
    return PipelineResult(
        questions=[question], source=source, chunks_processed=1, chunks_failed=0,
        requested_question_count=1,
    )


def test_cli_pdf_success_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "generate_quiz", lambda source, target_question_count, **_options: _fake_result(source))

    exit_code = cli.main(["--pdf", "fake.pdf"])

    assert exit_code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["questions"][0]["question"] == "Test?"
    assert data["source"]["kind"] == "pdf"


def test_cli_link_and_image_build_correct_source_kind(monkeypatch):
    captured = {}

    def fake_generate(source, target_question_count, **_options):
        captured["kind"] = source.kind
        return _fake_result(source)

    monkeypatch.setattr(cli, "generate_quiz", fake_generate)

    cli.main(["--link", "https://example.az"])
    assert captured["kind"] == "link"

    cli.main(["--image", "sekil.png"])
    assert captured["kind"] == "image"


def test_cli_requires_one_source_argument():
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_pipeline_error_returns_nonzero_and_prints_message(monkeypatch, capsys):
    def boom(source, target_question_count, **_options):
        raise PipelineError("uğursuz oldu")

    monkeypatch.setattr(cli, "generate_quiz", boom)

    exit_code = cli.main(["--pdf", "fake.pdf"])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "uğursuz oldu" in err


def test_cli_passes_profile_and_writes_review_sheet(monkeypatch, tmp_path):
    """Müəllimin keyfiyyət qiymətləndirməsi üçün (spec 2026-09-29 §5):
    uydurma data yox, müəllimin REAL materialından bank + qiymətləndirmə
    cədvəli. Excel Azərbaycan hərflərini düzgün açsın deyə utf-8-sig."""
    captured = {}

    def fake_generate(source, target_question_count, *, profile, bank_kind):
        captured.update(profile=profile, bank_kind=bank_kind)
        result = _fake_result(source)
        result.passage = "Tom lives in Baku."
        return result

    monkeypatch.setattr(cli, "generate_quiz", fake_generate)
    sheet = tmp_path / "review.csv"
    exit_code = cli.main(["--pdf", "x.pdf", "--profile", "english", "--bank-kind", "reading",
                          "--review-csv", str(sheet)])

    assert exit_code == 0
    assert captured == {"profile": "english", "bank_kind": "reading"}
    raw = sheet.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM: Excel UTF-8 kimi oxusun
    text = raw.decode("utf-8-sig")
    header = text.splitlines()[0]
    for column in ("Sual", "Düzgün cavab", "İzah", "Doğrudur", "Səviyyə", "Audit"):
        assert column in header
    assert "Test?" in text
    assert (tmp_path / "review_metn.txt").read_text(encoding="utf-8") == "Tom lives in Baku."


def test_cli_rejects_unknown_profile():
    with pytest.raises(SystemExit):
        cli.main(["--pdf", "x.pdf", "--profile", "riyaziyyat"])
