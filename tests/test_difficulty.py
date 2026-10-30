"""Çətinlik bölgüsü (Faza 2, 2026-10-30)."""

import json

import pytest

from pipeline.difficulty import breakdown, prompt_note, quotas, select_by_mix, validate_mix
from pipeline.ingestion import pdf_extractor
from pipeline.models import MaterialSource, MCQQuestion, RawMaterial
from pipeline.pipeline import generate_quiz


def _q(text: str, difficulty: str | None) -> MCQQuestion:
    return MCQQuestion(
        question=text, options=["A", "B", "C", "D", "E"], correct_index=0,
        explanation="izah", difficulty=difficulty,
    )


class TestModel:
    @pytest.mark.parametrize("raw,expected", [
        ("asan", "asan"), ("Orta", "orta"), ("ÇƏTİN", None), ("çətin", "çətin"),
        ("cetin", "çətin"), ("hard", "çətin"), ("easy", "asan"), ("bilmirəm", None), (3, None),
    ])
    def test_difficulty_is_normalized_not_rejected(self, raw, expected):
        """Model səviyyəni səhv yazsa, sual İTMİR — sadəcə səviyyəsiz qalır.
        («ÇƏTİN»-in `lower()`-i Python-da «çəti̇n» olur — bu da itmir, None.)"""
        assert _q("s", raw).difficulty == expected

    def test_old_questions_without_difficulty_still_parse(self):
        assert MCQQuestion(question="s", options=list("ABCDE"), correct_index=0, explanation="i").difficulty is None


class TestQuotas:
    @pytest.mark.parametrize("total,mix,expected", [
        (10, (30, 50, 20), {"asan": 3, "orta": 5, "çətin": 2}),
        (7, (30, 50, 20), {"asan": 2, "orta": 4, "çətin": 1}),
        (3, (0, 0, 100), {"asan": 0, "orta": 0, "çətin": 3}),
        (1, (34, 33, 33), {"asan": 1, "orta": 0, "çətin": 0}),
    ])
    def test_sum_is_always_total(self, total, mix, expected):
        result = quotas(total, mix)
        assert result == expected
        assert sum(result.values()) == total

    @pytest.mark.parametrize("mix", [(50, 50, 10), (-10, 60, 50), (101, 0, -1), (30, 50)])
    def test_invalid_mix_is_rejected(self, mix):
        with pytest.raises(ValueError):
            validate_mix(mix)


class TestSelection:
    def test_exact_mix_when_enough_questions(self):
        pool = [_q(f"a{i}", "asan") for i in range(5)] + [_q(f"o{i}", "orta") for i in range(6)] \
            + [_q(f"c{i}", "çətin") for i in range(4)]
        chosen = select_by_mix(pool, 10, (30, 50, 20))
        assert [q.difficulty for q in chosen].count("asan") == 3
        assert [q.difficulty for q in chosen].count("orta") == 5
        assert [q.difficulty for q in chosen].count("çətin") == 2

    def test_shortfall_is_filled_from_neighbour_without_stealing_its_quota(self):
        """Çətin sual yoxdur: 2 yer «orta»nın ARTIQ suallarından dolur,
        «orta»nın öz 5 yeri toxunulmaz qalır."""
        pool = [_q(f"a{i}", "asan") for i in range(3)] + [_q(f"o{i}", "orta") for i in range(8)]
        chosen = select_by_mix(pool, 10, (30, 50, 20))
        levels = [q.difficulty for q in chosen]
        assert len(chosen) == 10
        assert levels.count("asan") == 3 and levels.count("orta") == 7

    def test_unlabelled_questions_count_as_medium(self):
        pool = [_q(f"x{i}", None) for i in range(4)]
        assert len(select_by_mix(pool, 4, (0, 100, 0))) == 4

    def test_original_order_is_kept(self):
        pool = [_q("1", "çətin"), _q("2", "asan"), _q("3", "orta")]
        assert [q.question for q in select_by_mix(pool, 3, (34, 33, 33))] == ["1", "2", "3"]


def test_prompt_note_names_counts_and_levels():
    note = prompt_note(10, (30, 50, 20))
    assert "3 asan, 5 orta, 2 çətin" in note
    assert "difficulty" in note


def test_generate_quiz_applies_mix_end_to_end(monkeypatch):
    monkeypatch.setattr(
        pdf_extractor, "extract",
        lambda source: RawMaterial(text="Qısa dərs materialı. " * 20, metadata={}),
    )
    prompts = []
    levels = ["asan"] * 4 + ["orta"] * 6 + ["çətin"] * 4

    def completer(system: str, user: str) -> str:
        prompts.append(user)
        # Dedup mətn oxşarlığına baxır — suallar mövzuca FƏRQLİ olmalıdır.
        topics = [
            "Azərbaycanın paytaxtı hansı şəhərdir?", "Hakimiyyət neçə qola bölünür?",
            "Konstitusiya hansı ildə qəbul edilib?", "Milli Məclisdə neçə deputat var?",
            "Ali Məhkəmənin sədrini kim təyin edir?", "Prezidentin səlahiyyət müddəti nədir?",
            "Bələdiyyə seçkiləri neçə ildən bir keçirilir?", "Dövlət büdcəsini kim təsdiqləyir?",
            "Vergilər hansı qanunla müəyyən edilir?", "Ordu kimin komandanlığındadır?",
            "Bayraqda neçə rəng var?", "Himnin sözlərinin müəllifi kimdir?",
            "Dövlət dili hansıdır?", "Ombudsman hansı hüquqları qoruyur?",
        ]
        return json.dumps({"questions": [
            {"question": topic, "options": list("ABCDE"),
             "correct_index": 0, "explanation": "izah", "difficulty": level}
            for topic, level in zip(topics, levels)
        ]})

    result = generate_quiz(
        MaterialSource(kind="pdf", location="x.pdf"), target_question_count=10,
        completers={"groq": completer}, order=["groq"], difficulty_mix=(20, 50, 30),
    )
    got = [q.difficulty for q in result.questions]
    assert (got.count("asan"), got.count("orta"), got.count("çətin")) == (2, 5, 3)
    assert "Çətinlik bölgüsü" in prompts[0]


def test_generate_quiz_without_mix_sends_no_difficulty_note(monkeypatch):
    monkeypatch.setattr(
        pdf_extractor, "extract",
        lambda source: RawMaterial(text="Qısa dərs materialı. " * 20, metadata={}),
    )
    prompts = []

    def completer(system: str, user: str) -> str:
        prompts.append(user)
        return json.dumps({"questions": [
            {"question": topic, "options": list("ABCDE"), "correct_index": 0, "explanation": "i"}
            for topic in ("Paytaxt hansı şəhərdir?", "Bayraqda neçə rəng var?", "Dövlət dili hansıdır?")
        ]})

    generate_quiz(MaterialSource(kind="pdf", location="x.pdf"), target_question_count=3,
                  completers={"groq": completer}, order=["groq"])
    assert "Çətinlik bölgüsü" not in prompts[0]


def test_breakdown_groups_by_level_and_keeps_unlabelled_apart():
    rows = [
        {"difficulty": "asan", "correct_count": 4, "total_answers": 5},
        {"difficulty": "çətin", "correct_count": 1, "total_answers": 5},
        {"difficulty": "çətin", "correct_count": 3, "total_answers": 5},
        {"difficulty": None, "correct_count": 2, "total_answers": 2},
    ]
    assert breakdown(rows) == [
        {"level": "asan", "question_count": 1, "correct_count": 4, "total_answers": 5},
        {"level": "çətin", "question_count": 2, "correct_count": 4, "total_answers": 10},
        {"level": None, "question_count": 1, "correct_count": 2, "total_answers": 2},
    ]


def test_breakdown_of_nothing_is_empty():
    assert breakdown([]) == []
