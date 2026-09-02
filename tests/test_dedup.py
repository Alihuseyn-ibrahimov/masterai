from pipeline.dedup import filter_duplicates
from pipeline.models import MCQQuestion


def _q(question: str, correct_index: int = 0) -> MCQQuestion:
    return MCQQuestion(
        question=question,
        options=["A", "B", "C", "D", "E"],
        correct_index=correct_index,
        explanation="izah",
    )


def test_keeps_all_when_no_duplicates():
    questions = [_q("Azərbaycanın paytaxtı hansıdır?"), _q("Konstitusiya neçənci ildə qəbul olunub?")]
    result = filter_duplicates(questions)
    assert len(result) == 2


def test_drops_near_identical_question_keeping_first():
    original = _q("Azərbaycan Respublikasının paytaxtı hansı şəhərdir?")
    near_duplicate = _q("Azərbaycan Respublikasının paytaxtı hansı şəhərdir??")
    result = filter_duplicates([original, near_duplicate])
    assert result == [original]


def test_keeps_clearly_different_questions_even_if_short():
    questions = [_q("Paytaxt hansıdır?"), _q("Dövlət dili nədir?")]
    result = filter_duplicates(questions)
    assert len(result) == 2


def test_empty_list_returns_empty_list():
    assert filter_duplicates([]) == []
