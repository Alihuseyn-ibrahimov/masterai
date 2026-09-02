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
    return PipelineResult(questions=[question], source=source, chunks_processed=1, chunks_failed=0)


def test_cli_pdf_success_prints_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "generate_quiz", lambda source, questions_per_chunk: _fake_result(source))

    exit_code = cli.main(["--pdf", "fake.pdf"])

    assert exit_code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["questions"][0]["question"] == "Test?"
    assert data["source"]["kind"] == "pdf"


def test_cli_link_and_image_build_correct_source_kind(monkeypatch):
    captured = {}

    def fake_generate(source, questions_per_chunk):
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
    def boom(source, questions_per_chunk):
        raise PipelineError("uğursuz oldu")

    monkeypatch.setattr(cli, "generate_quiz", boom)

    exit_code = cli.main(["--pdf", "fake.pdf"])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "uğursuz oldu" in err
