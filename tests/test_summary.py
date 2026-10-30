"""Dərs xülasəsi (Faza 3, 2026-10-30)."""

import json

import pytest

from pipeline import summary as summary_module
from pipeline.ingestion import pdf_extractor
from pipeline.models import MaterialSource, RawMaterial
from pipeline.summary import LessonSummary, SummaryError, ground, summarize_material

_SOURCE = MaterialSource(kind="pdf", location="x.pdf")

_GOOD = {
    "title": "Dövlət qulluğu haqqında qanun",
    "intro": "Qanun dövlət qulluğunun əsaslarını müəyyən edir.",
    "key_points": [
        "Qanun 2000-ci ildə qəbul edilib.",
        "Dövlət qulluqçusu siyasi neytrallığı qorumalıdır.",
        "Qulluğa qəbul müsabiqə yolu ilə aparılır.",
    ],
    "terms": [{"term": "Müsabiqə", "definition": "Qulluğa açıq seçim prosesi."}],
    "facts": ["Maddə 12: sınaq müddəti 6 aydır.", "Qanun 1999-cu ildə qüvvəyə minib."],
    "self_check": [{"question": "Qəbul necə aparılır?", "answer": "Müsabiqə ilə."}],
}

_TEXT = (
    "Dövlət qulluğu haqqında qanun 2000-ci ildə qəbul edilib. Maddə 12 sınaq "
    "müddətini 6 ay müəyyən edir. Qəbul müsabiqə yolu ilə aparılır. "
)


def _patch_text(monkeypatch, text):
    monkeypatch.setattr(pdf_extractor, "extract", lambda source: RawMaterial(text=text, metadata={}))


def test_short_material_uses_single_call(monkeypatch):
    _patch_text(monkeypatch, _TEXT)
    calls = []

    def completer(system, user):
        calls.append(user)
        return json.dumps(_GOOD)

    result = summarize_material(_SOURCE, completers={"groq": completer}, order=["groq"])
    assert len(calls) == 1
    assert _TEXT.strip() in calls[0]
    assert result.title == "Dövlət qulluğu haqqında qanun"


def test_invented_numbers_are_dropped(monkeypatch):
    """«1999» mənbədə yoxdur — həmin fakt atılır; «2000», «12», «6» qalır."""
    _patch_text(monkeypatch, _TEXT)
    result = summarize_material(_SOURCE, completers={"groq": lambda s, u: json.dumps(_GOOD)}, order=["groq"])
    assert result.facts == ["Maddə 12: sınaq müddəti 6 aydır."]
    assert "Qanun 2000-ci ildə qəbul edilib." in result.key_points


def test_long_material_is_mapped_then_reduced(monkeypatch):
    long_text = "\n\n".join(f"Bölmə {i}. " + "Qulluqçu qanuna əməl edir. " * 60 for i in range(40))
    _patch_text(monkeypatch, long_text)
    calls = []

    def completer(system, user):
        calls.append(user)
        if "qısa qeydlər" in user:
            return "- Qulluqçu qanuna əməl edir."
        return json.dumps({**_GOOD, "facts": []})

    summarize_material(_SOURCE, completers={"groq": completer}, order=["groq"])
    notes_calls = [c for c in calls if "qısa qeydlər" in c]
    assert len(notes_calls) == summary_module.MAX_PARTS
    assert len(calls) == summary_module.MAX_PARTS + 1
    assert "hissə-hissə qeydləri" in calls[-1]


def test_bad_json_is_retried_once(monkeypatch):
    _patch_text(monkeypatch, _TEXT)
    calls = []

    def completer(system, user):
        calls.append(user)
        return "bu JSON deyil" if len(calls) == 1 else json.dumps(_GOOD)

    summarize_material(_SOURCE, completers={"groq": completer}, order=["groq"])
    assert len(calls) == 2 and "DİQQƏT" in calls[1]


def test_persistent_bad_json_raises(monkeypatch):
    _patch_text(monkeypatch, _TEXT)
    with pytest.raises(SummaryError):
        summarize_material(_SOURCE, completers={"groq": lambda s, u: "yox"}, order=["groq"])


def test_empty_material_raises(monkeypatch):
    _patch_text(monkeypatch, "   ")
    with pytest.raises(SummaryError):
        summarize_material(_SOURCE, completers={"groq": lambda s, u: json.dumps(_GOOD)}, order=["groq"])


def test_ground_trims_lists():
    s = LessonSummary(
        title="t", intro="i", key_points=[f"fikir {c}" for c in "abcdefghij"],
        self_check=[{"question": "q", "answer": "a"}] * 5,
    )
    trimmed = ground(s, "")
    assert len(trimmed.key_points) == 8 and len(trimmed.self_check) == 3
