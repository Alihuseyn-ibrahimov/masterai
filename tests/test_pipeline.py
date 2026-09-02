import json
import threading

import pytest

from pipeline import pipeline as pipeline_module
from pipeline.ingestion import pdf_extractor
from pipeline.ingestion.errors import IngestionError
from pipeline.models import MaterialSource, RawMaterial
from pipeline.pipeline import PipelineError, generate_quiz

# Dedup sual MƏTNİNƏ görə oxşarlığa baxır — nömrə fərqli, qalan mətni demək
# olar eyni olan sualları (real generasiyada təsadüfi deyil) qəsdən yox,
# əvəzinə mövzuca fərqli sual mətnləri işlədirik ki, dedup onları həqiqətən
# fərqli sual kimi tanısın.
_QUESTION_TOPICS = [
    "Azərbaycan Respublikasının paytaxtı hansı şəhərdir?",
    "Dövlət hakimiyyəti neçə qola bölünür?",
    "Konstitusiya neçənci ildə qəbul olunub?",
    "Ali Məclisin funksiyası nədir?",
    "Məhkəmə hakimiyyətinin başında kim durur?",
    "Prezidentin səlahiyyət müddəti neçə ildir?",
    "Milli Məclisin deputat sayı neçədir?",
    "Yerli özünüidarəetmə orqanı necə adlanır?",
]


def _question(i: int) -> dict:
    return {
        "question": _QUESTION_TOPICS[i % len(_QUESTION_TOPICS)],
        "options": ["A", "B", "C", "D", "E"],
        "correct_index": 0,
        "explanation": "izah",
    }


def _valid_completer(n_per_call: int = 3):
    # Hər çağırışda unikal sual mətnləri qaytarır — dedup real sınaqda olduğu
    # kimi eyni suallara görə deyil, təsadüfən oxşar mətnlərə görə işləməlidir.
    # LCEL .batch() chunk-ları paralel (thread pool) işlədə bilər, ona görə
    # sayğac lock ilə qorunur.
    counter = {"n": 0}
    lock = threading.Lock()

    def completer(system: str, user: str) -> str:
        questions = []
        with lock:
            for _ in range(n_per_call):
                questions.append(_question(counter["n"]))
                counter["n"] += 1
        return json.dumps({"questions": questions})

    return {"groq": completer}


def _long_text() -> str:
    return "Bu numune ders materialidir ve test ucun kifayet qeder uzundur. " * 300


def test_generate_quiz_end_to_end_with_fake_extractor(monkeypatch):
    monkeypatch.setattr(
        pdf_extractor, "extract", lambda source: RawMaterial(text=_long_text(), metadata={})
    )

    source = MaterialSource(kind="pdf", location="fake.pdf")
    result = generate_quiz(
        source, questions_per_chunk=3, completers=_valid_completer(3), order=["groq"]
    )

    assert len(result.questions) >= 3
    assert result.source == source
    assert result.chunks_failed == 0
    assert result.chunks_processed >= 1


def test_ingestion_error_propagates_unwrapped(monkeypatch):
    def boom(source):
        raise IngestionError("sınıq fayl")

    monkeypatch.setattr(pdf_extractor, "extract", boom)

    source = MaterialSource(kind="pdf", location="fake.pdf")
    with pytest.raises(IngestionError):
        generate_quiz(source, completers=_valid_completer(), order=["groq"])


def test_raises_pipeline_error_when_too_few_questions(monkeypatch):
    monkeypatch.setattr(
        pdf_extractor, "extract", lambda source: RawMaterial(text="qısa mətn", metadata={})
    )

    def empty_completer(system: str, user: str) -> str:
        return json.dumps({"questions": []})

    source = MaterialSource(kind="pdf", location="fake.pdf")
    with pytest.raises(PipelineError):
        generate_quiz(source, completers={"groq": empty_completer}, order=["groq"])


def test_raises_pipeline_error_when_all_providers_fail(monkeypatch):
    monkeypatch.setattr(
        pdf_extractor, "extract", lambda source: RawMaterial(text=_long_text(), metadata={})
    )

    def broken(system: str, user: str) -> str:
        raise RuntimeError("provayder xətası")

    source = MaterialSource(kind="pdf", location="fake.pdf")
    with pytest.raises(PipelineError):
        generate_quiz(source, completers={"groq": broken}, order=["groq"])


def test_raises_pipeline_error_when_no_chunks_produced(monkeypatch):
    monkeypatch.setattr(
        pdf_extractor, "extract", lambda source: RawMaterial(text=_long_text(), metadata={})
    )
    monkeypatch.setattr(pipeline_module, "split", lambda text: [])

    source = MaterialSource(kind="pdf", location="fake.pdf")
    with pytest.raises(PipelineError):
        generate_quiz(source, completers=_valid_completer(), order=["groq"])


def test_dispatches_to_correct_extractor_by_kind(monkeypatch):
    from pipeline.ingestion import image_extractor, web_extractor

    calls = []
    monkeypatch.setattr(
        web_extractor,
        "extract",
        lambda source: calls.append("link") or RawMaterial(text=_long_text(), metadata={}),
    )
    monkeypatch.setattr(
        image_extractor,
        "extract",
        lambda source: calls.append("image") or RawMaterial(text=_long_text(), metadata={}),
    )

    generate_quiz(
        MaterialSource(kind="link", location="https://x.az"),
        completers=_valid_completer(3),
        order=["groq"],
    )
    generate_quiz(
        MaterialSource(kind="image", location="x.png"),
        completers=_valid_completer(3),
        order=["groq"],
    )

    assert calls == ["link", "image"]
