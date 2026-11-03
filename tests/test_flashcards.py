"""Flashcard-lar (Faza 1 «Müəllim AI asistenti», PR 3, 2026-11-03)."""

import json

import pytest

from pipeline import flashcards as fc
from pipeline.flashcards import Flashcard, FlashcardError, generate_flashcards, parse_cards
from pipeline.ingestion import pdf_extractor
from pipeline.models import MaterialSource, RawMaterial

_SOURCE = MaterialSource(kind="pdf", location="x.pdf")
_TEXT = (
    "Dövlət qulluğu haqqında qanun 2000-ci ildə qəbul edilib. Maddə 12 sınaq müddətini 6 ay "
    "müəyyən edir. Qulluğa qəbul müsabiqə yolu ilə aparılır, müsabiqəni Dövlət İmtahan Mərkəzi keçirir."
)


def _c(front, back="Müsabiqə yolu ilə.", difficulty="orta"):
    return {"front": front, "back": back, "difficulty": difficulty}


@pytest.fixture(autouse=True)
def _text(monkeypatch):
    monkeypatch.setattr(pdf_extractor, "extract", lambda source: RawMaterial(text=_TEXT, metadata={}))


def test_generates_cards_with_subject_note():
    calls = []

    def completer(system, user):
        calls.append(user)
        return json.dumps({"cards": [
            _c("Qulluğa qəbul necə aparılır?"),
            _c("Sınaq müddəti nə qədərdir?", back="6 ay."),
        ]})

    result = generate_flashcards(_SOURCE, count=2, subject="qanunvericilik",
                                 completers={"groq": completer}, order=["groq"])
    assert [c.front for c in result] == ["Qulluğa qəbul necə aparılır?", "Sınaq müddəti nə qədərdir?"]
    assert len(calls) == 1
    assert "Fənn: Qanunvericilik" in calls[0] and _TEXT in calls[0]


def test_invented_numbers_and_duplicates_are_dropped():
    reply = json.dumps({"cards": [
        _c("Qanun nə vaxt qəbul edilib?", back="1999-cu ildə."),  # 1999 materialda yoxdur
        _c("Qulluğa qəbul necə aparılır?"),
        _c("Qulluğa  qəbul necə aparılır?!"),                      # təkrar
        _c("Sınaq müddəti nə qədərdir?", back="Maddə 12-yə görə 6 ay."),  # 12 və 6 materialda var
    ]})
    result = generate_flashcards(_SOURCE, count=5, completers={"groq": lambda s, u: reply}, order=["groq"])
    assert [c.front for c in result] == ["Qulluğa qəbul necə aparılır?", "Sınaq müddəti nə qədərdir?"]


def test_bad_json_is_retried_once():
    replies = iter(["bağışlayın, JSON yoxdur", json.dumps({"cards": [_c("Qulluğa qəbul necə aparılır?")]})])
    calls = []

    def completer(system, user):
        calls.append(user)
        return next(replies)

    result = generate_flashcards(_SOURCE, count=1, completers={"groq": completer}, order=["groq"])
    assert len(result) == 1 and len(calls) == 2
    assert "DİQQƏT" in calls[1]


def test_nothing_usable_raises():
    with pytest.raises(FlashcardError):
        generate_flashcards(_SOURCE, count=1, completers={"groq": lambda s, u: "{}"}, order=["groq"])


def test_long_material_is_spread_over_parts(monkeypatch):
    long_text = "\n\n".join(f"Bölmə {i}. " + "Qulluqçu qanuna əməl edir. " * 60 for i in range(40))
    monkeypatch.setattr(pdf_extractor, "extract", lambda source: RawMaterial(text=long_text, metadata={}))
    calls = []

    def completer(system, user):
        calls.append(user)
        return json.dumps({"cards": [_c(f"Sual {len(calls)}: qulluqçu nəyə əməl edir?", back="Qanuna.")]})

    result = generate_flashcards(_SOURCE, count=10, completers={"groq": completer}, order=["groq"])
    assert len(calls) == fc.MAX_PARTS
    assert len(result) == fc.MAX_PARTS
    assert all(len(c) < fc.PART_CHARS + 3000 for c in calls)


def test_model_quirks_are_normalized():
    card = Flashcard.model_validate({"front": " Müsabiqəni izah edin. ", "back": " cavab ", "difficulty": "hard"})
    assert card.front == "Müsabiqəni izah edin." and card.back == "cavab" and card.difficulty == "çətin"


def test_parse_skips_broken_items():
    text = "Cavab:\n" + json.dumps({"cards": [_c("Qulluğa qəbul necə aparılır?"), {"front": "yarımçıq"}]})
    result = parse_cards(text)
    assert len(result) == 1 and result[0].front == "Qulluğa qəbul necə aparılır?"


def test_parse_raises_on_missing_json():
    with pytest.raises(ValueError):
        parse_cards("heç bir JSON yoxdur")


def test_count_out_of_range_raises():
    with pytest.raises(ValueError):
        generate_flashcards(_SOURCE, count=0, completers={"groq": lambda s, u: "{}"}, order=["groq"])
    with pytest.raises(ValueError):
        generate_flashcards(_SOURCE, count=fc.MAX_COUNT + 1, completers={"groq": lambda s, u: "{}"}, order=["groq"])
