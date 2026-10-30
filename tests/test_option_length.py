"""Düzgün cavab uzunluğu ilə özünü verməməlidir (2026-10-30, real şikayət)."""

from __future__ import annotations

from pipeline.generation import _PROMPT
from pipeline.models import MCQQuestion
from pipeline.quality import answer_stands_out, prefer_balanced


def _q(options: list[str], correct: int = 0, text: str = "Sual?") -> MCQQuestion:
    return MCQQuestion(question=text, options=options, correct_index=correct, explanation="İzah.")


LONG_CORRECT = _q([
    "Qanunla müəyyən edilmiş hallarda inzibati orqanın yazılı qərarı ilə",
    "Şifahi göstərişlə",
    "Məhkəmə qərarı ilə",
    "Nazirin əmri ilə",
    "Heç bir halda",
])
BALANCED = _q([
    "İnzibati orqanın yazılı qərarı ilə",
    "Nazirliyin şifahi göstərişi əsasında",
    "Yalnız məhkəmənin qətnaməsi ilə",
    "Prezidentin fərmanı ilə birbaşa",
    "Bələdiyyə şurasının razılığı ilə",
])


def test_long_correct_answer_stands_out():
    assert answer_stands_out(LONG_CORRECT)


def test_balanced_options_do_not_stand_out():
    assert not answer_stands_out(BALANCED)


def test_short_numeric_options_are_not_flagged():
    """«10 il» «5 il»dən uzundur, amma bu, uzunluq ipucu deyil."""
    assert not answer_stands_out(_q(["10 il", "5 il", "3 il", "7 il", "1 il"]))


def test_long_wrong_option_is_not_flagged():
    """Ən uzun variant səhvdirsə, tələbəni yanıltmaq olar - ipucu yoxdur."""
    assert not answer_stands_out(_q(LONG_CORRECT.options, correct=1))


def test_prefer_balanced_moves_flagged_to_end_keeping_order():
    a = _q(BALANCED.options, text="A")
    b = _q(LONG_CORRECT.options, text="B")
    c = _q(BALANCED.options, text="C")
    assert [q.question for q in prefer_balanced([b, a, c])] == ["A", "C", "B"]


def test_prefer_balanced_keeps_all_questions():
    assert len(prefer_balanced([LONG_CORRECT, LONG_CORRECT])) == 2


def test_prompt_asks_for_equal_length_options():
    assert "eyni uzunluqda" in _PROMPT.template
