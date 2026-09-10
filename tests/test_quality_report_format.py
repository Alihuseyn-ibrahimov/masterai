"""Yoxlama vərəqinin formatı.

Ən təhlükəli səhv burada yaşayır: vərəqdə DÜZGÜN variant səhv
işarələnsə, insan yanlış məlumatla qiymətləndirmə aparar və bütün
nəticə etibarsız olar. Ona görə işarələmə testlə bağlanır.
"""

from __future__ import annotations

from pipeline.models import MCQQuestion
from pipeline.quality import audit_questions
from pipeline.quality_report import format_review_sheet


def q(correct_index: int = 0) -> MCQQuestion:
    return MCQQuestion(
        question="Dövlət qulluqçusuna nə qadağandır?",
        options=["Elmi fəaliyyət", "Sahibkarlıq", "Pedaqoji fəaliyyət", "Yaradıcılıq", "Tədris"],
        correct_index=correct_index,
        explanation="Qanunun 20.1-ci maddəsi sahibkarlığı birbaşa qadağan edir.",
    )


class TestCorrectAnswerMarking:
    def test_the_marked_option_is_the_one_the_data_says_is_correct(self):
        for index, letter in enumerate("ABCDE"):
            sheet = format_review_sheet([q(correct_index=index)], audit_questions([q(correct_index=index)]))
            marked = [line for line in sheet.splitlines() if line.lstrip().startswith("→")]
            assert len(marked) == 1, f"{letter}: bir variant işarələnməlidir"
            assert marked[0].lstrip().startswith(f"→ {letter}"), f"{letter} işarələnməli idi: {marked[0]}"

    def test_every_option_appears_on_the_sheet(self):
        question = q()
        sheet = format_review_sheet([question], audit_questions([question]))
        for option in question.options:
            assert option in sheet


class TestSheetContent:
    def test_explanation_is_shown_so_the_reviewer_can_judge_it(self):
        question = q()
        sheet = format_review_sheet([question], audit_questions([question]))
        assert question.explanation in sheet

    def test_automatic_findings_are_attached_to_their_question(self):
        bad = MCQQuestion(
            question="Bu sənəd hansı tarixdə dərc edilmişdir?",
            options=["Bir", "İki", "Üç", "Dörd", "Beş"],
            correct_index=0,
            explanation="Sənədin başlığında göstərilib, ona görə belədir.",
        )
        sheet = format_review_sheet([bad], audit_questions([bad]))
        assert "metadata_sual" in sheet

    def test_sheet_has_a_place_to_record_the_verdict(self):
        question = q()
        sheet = format_review_sheet([question], audit_questions([question]))
        assert "DÜZGÜN / SƏHV" in sheet

    def test_empty_set_says_so_instead_of_printing_nothing(self):
        sheet = format_review_sheet([], audit_questions([]))
        assert "sual yoxdur" in sheet.lower()
