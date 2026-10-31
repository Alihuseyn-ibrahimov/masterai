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
        source, target_question_count=3, completers=_valid_completer(3), order=["groq"]
    )

    assert len(result.questions) >= 3
    assert result.source == source
    assert result.chunks_failed == 0
    assert result.chunks_processed >= 1
    assert result.requested_question_count == 3


def test_generate_quiz_truncates_to_target_when_more_are_generated(monkeypatch):
    """Material bir neçə chunk-a bölünürsə, hər chunk-dan `target`-a
    çatmaq üçün lazım olandan çox sual istənilə bilər (dedup itkisinə
    qarşı) — dedup-dan sonra `target`-dan artıq qalarsa kəsilməlidir."""
    monkeypatch.setattr(
        pdf_extractor, "extract", lambda source: RawMaterial(text=_long_text(), metadata={})
    )

    source = MaterialSource(kind="pdf", location="fake.pdf")
    result = generate_quiz(
        source, target_question_count=4, completers=_valid_completer(3), order=["groq"]
    )

    assert len(result.questions) == 4
    assert result.requested_question_count == 4


def test_generate_quiz_accepts_fewer_than_target_when_material_is_short(monkeypatch):
    """Material qısadırsa (az chunk), tələb olunan sayı bacarmasa da,
    ən azı `_MIN_QUESTIONS` alınırsa nəticə qəbul edilir (undershoot)."""
    monkeypatch.setattr(
        pdf_extractor, "extract", lambda source: RawMaterial(text="qısa material mətni", metadata={})
    )

    def small_completer(system: str, user: str) -> str:
        return json.dumps({"questions": [_question(i) for i in range(3)]})

    source = MaterialSource(kind="pdf", location="fake.pdf")
    result = generate_quiz(
        source, target_question_count=20, completers={"groq": small_completer}, order=["groq"]
    )

    assert len(result.questions) == 3
    assert result.requested_question_count == 20


class TestSelectChunks:
    """Real production-da tapılıb (e-qanun.az, 389 min simvol → 65 chunk):
    10 sual üçün 65 API çağırışı Groq-un rate limitini (8000 token/dəqiqə)
    aşırdı və emal ilişib qalırdı. İstənilən sual sayına görə lazım olan
    qədər chunk seçilməlidir."""

    def test_keeps_all_chunks_when_document_is_small(self):
        chunks = [f"chunk {i}" for i in range(5)]
        assert pipeline_module._select_chunks(chunks, target_question_count=10) == chunks

    def test_caps_chunk_count_for_large_documents(self):
        chunks = [f"chunk {i}" for i in range(65)]

        selected = pipeline_module._select_chunks(chunks, target_question_count=10)

        assert len(selected) == 10 * pipeline_module._CHUNKS_PER_QUESTION_BUFFER
        assert len(selected) < len(chunks)

    def test_selection_is_spread_across_the_whole_document(self):
        """Yalnız ilk N chunk götürülsə, suallar sənədin yalnız girişindən
        çıxardı — seçim sənəd boyu paylanmalıdır."""
        chunks = [f"chunk {i}" for i in range(100)]

        selected = pipeline_module._select_chunks(chunks, target_question_count=5)

        assert selected[0] == "chunk 0"
        assert selected[-1] != "chunk 9"  # sadəcə ilk 10-dan seçilməyib
        assert chunks.index(selected[-1]) > len(chunks) // 2

    def test_never_returns_empty_for_tiny_targets(self):
        chunks = [f"chunk {i}" for i in range(50)]
        assert len(pipeline_module._select_chunks(chunks, target_question_count=0)) >= 1


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


def test_generate_quiz_drops_long_correct_answers_when_surplus(monkeypatch):
    """2026-10-30: düzgün cavabı uzunluğu ilə özünü verən sual, artıq sual
    olanda bankdan düşür."""
    monkeypatch.setattr(
        pdf_extractor, "extract", lambda source: RawMaterial(text=_long_text(), metadata={})
    )
    long_opts = ["Qanunla müəyyən edilmiş hallarda yazılı qərar əsasında", "Şifahi", "Əmrlə", "Heç vaxt", "Hər zaman"]

    def completer(system: str, user: str) -> str:
        questions = [_question(i) for i in range(4)]
        for q in questions[:2]:
            q["options"] = long_opts
        return json.dumps({"questions": questions})

    result = generate_quiz(
        MaterialSource(kind="pdf", location="fake.pdf"),
        target_question_count=3, completers={"groq": completer}, order=["groq"],
    )
    long_ones = [q for q in result.questions if q.options == long_opts]
    assert len(result.questions) == 3
    assert len(long_ones) == 1  # 2 balanslı + çatmayan yer üçün 1 uzun
