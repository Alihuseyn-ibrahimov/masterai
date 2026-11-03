"""Açıq suallar (Faza 1 «Müəllim AI asistenti», 2026-11-03)."""

import json

import pytest

from pipeline import open_questions as oq
from pipeline.ingestion import pdf_extractor
from pipeline.models import MaterialSource, RawMaterial
from pipeline.open_questions import OpenQuestion, OpenQuestionError, generate_open_questions, parse_questions

_SOURCE = MaterialSource(kind="pdf", location="x.pdf")
_TEXT = (
    "Dövlət qulluğu haqqında qanun 2000-ci ildə qəbul edilib. Maddə 12 sınaq müddətini 6 ay "
    "müəyyən edir. Qulluğa qəbul müsabiqə yolu ilə aparılır, müsabiqəni Dövlət İmtahan Mərkəzi keçirir."
)


def _q(question, kind="qisa", answer="Müsabiqə yolu ilə.", rubric=None, difficulty="orta"):
    return {"question": question, "kind": kind, "model_answer": answer,
            "rubric": rubric or [{"criterion": "Müsabiqəni göstərir", "points": 2}], "difficulty": difficulty}


@pytest.fixture(autouse=True)
def _text(monkeypatch):
    monkeypatch.setattr(pdf_extractor, "extract", lambda source: RawMaterial(text=_TEXT, metadata={}))


def test_generates_questions_with_rubric_and_subject_note():
    calls = []

    def completer(system, user):
        calls.append(user)
        return json.dumps({"questions": [
            _q("Qulluğa qəbul necə aparılır?"),
            _q("Sınaq müddətinin məqsədini izah edin.", kind="esse", answer="Sınaq 6 ay davam edir.",
               rubric=[{"criterion": "6 ayı göstərir", "points": 2}, {"criterion": "Məqsədi izah edir", "points": 3}]),
        ]})

    result = generate_open_questions(_SOURCE, count=2, subject="qanunvericilik",
                                     completers={"groq": completer}, order=["groq"])
    assert [q.kind for q in result] == ["qisa", "esse"]
    assert result[1].max_points == 5
    assert len(calls) == 1
    assert "Fənn: Qanunvericilik" in calls[0] and _TEXT in calls[0]


def test_invented_numbers_and_duplicates_are_dropped():
    reply = json.dumps({"questions": [
        _q("Qanun nə vaxt qəbul edilib?", answer="1999-cu ildə."),       # 1999 materialda yoxdur
        _q("Qulluğa qəbul necə aparılır?"),
        _q("Qulluğa  qəbul necə aparılır?!"),                             # təkrar
        _q("Sınaq müddəti nə qədərdir?", answer="6 ay.",
           rubric=[{"criterion": "12 ay deyir", "points": 1}]),           # meyarda 12 var - maddə 12, qalır
    ]})
    result = generate_open_questions(_SOURCE, count=5, completers={"groq": lambda s, u: reply}, order=["groq"])
    assert [q.question for q in result] == ["Qulluğa qəbul necə aparılır?", "Sınaq müddəti nə qədərdir?"]


def test_bad_json_is_retried_once():
    replies = iter(["bağışlayın, JSON yoxdur", json.dumps({"questions": [_q("Qulluğa qəbul necə aparılır?")]})])
    calls = []

    def completer(system, user):
        calls.append(user)
        return next(replies)

    result = generate_open_questions(_SOURCE, count=1, completers={"groq": completer}, order=["groq"])
    assert len(result) == 1 and len(calls) == 2
    assert "DİQQƏT" in calls[1]


def test_nothing_usable_raises():
    with pytest.raises(OpenQuestionError):
        generate_open_questions(_SOURCE, count=1, completers={"groq": lambda s, u: "{}"}, order=["groq"])


def test_kind_filter_keeps_only_requested_kind():
    reply = json.dumps({"questions": [_q("Qulluğa qəbul necə aparılır?"),
                                      _q("Müsabiqəni kim keçirir, izah edin.", kind="esse")]})
    result = generate_open_questions(_SOURCE, count=3, kind="esse", completers={"groq": lambda s, u: reply},
                                     order=["groq"])
    assert [q.kind for q in result] == ["esse"]


def test_long_material_is_spread_over_parts(monkeypatch):
    long_text = "\n\n".join(f"Bölmə {i}. " + "Qulluqçu qanuna əməl edir. " * 60 for i in range(40))
    monkeypatch.setattr(pdf_extractor, "extract", lambda source: RawMaterial(text=long_text, metadata={}))
    calls = []

    def completer(system, user):
        calls.append(user)
        return json.dumps({"questions": [_q(f"Sual {len(calls)}: qulluqçu nəyə əməl edir?", answer="Qanuna.")]})

    result = generate_open_questions(_SOURCE, count=10, completers={"groq": completer}, order=["groq"])
    assert len(calls) == oq.MAX_PARTS
    assert len(result) == oq.MAX_PARTS
    assert all(len(c) < oq.PART_CHARS + 3000 for c in calls)


def test_model_quirks_are_normalized():
    q = OpenQuestion.model_validate({"question": "Müsabiqəni izah edin.", "kind": "Essay",
                                     "model_answer": " cavab ", "difficulty": "hard",
                                     "rubric": [{"criterion": "a", "points": 10}] * 9})
    assert q.kind == "esse" and q.difficulty == "çətin" and q.model_answer == "cavab"
    assert len(q.rubric) == oq.MAX_RUBRIC_ITEMS and q.rubric[0].points == oq.MAX_POINTS_PER_ITEM


def test_parse_skips_broken_items():
    text = "Cavab:\n" + json.dumps({"questions": [_q("Qulluğa qəbul necə aparılır?"), {"question": "yarımçıq"}]})
    assert len(parse_questions(text)) == 1
    with pytest.raises(ValueError):
        parse_questions("heç nə")


def test_count_and_kind_are_validated():
    with pytest.raises(ValueError):
        generate_open_questions(_SOURCE, count=0, completers={}, order=[])
    with pytest.raises(ValueError):
        generate_open_questions(_SOURCE, count=3, kind="test", completers={}, order=[])
