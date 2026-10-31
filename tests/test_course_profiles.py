"""Kurs profilləri: generasiya promptu, keyfiyyət yoxlamaları, reading — spec 2026-09-29 §5.

ƏSAS ZƏMANƏT: `exam_prep` (mövcud imtahan kursu) üçün heç nə dəyişmir —
prompt BAYT-BAYT eynidir, bütün yoxlamalar işləyir, heç bir sual atılmır.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from pipeline import pipeline as pipeline_module
from pipeline.generation import (
    SYSTEM_PROMPT,
    _PROMPT,
    generate_for_chunks,
    system_prompt_for,
)
from pipeline.ingestion import pdf_extractor
from pipeline.models import MaterialSource, MCQQuestion, RawMaterial
from pipeline.pipeline import PASSAGE_MAX_CHARS, generate_quiz
from pipeline.quality import audit_questions

# 2026-09-30, profil dəyişikliyindən ƏVVƏL götürülüb.
_EXAM_SYSTEM_SHA = "e7766d086299622f4fe32ea6da8949c1f422af518d6dc7e5306294bac4c7ca22"
# İnsan şablonu 2026-10-30-da QƏSDƏN dəyişdi (istifadəçi istəyi): variant
# uzunluğu qaydası əlavə olundu. Hash yeni şablonu qoruyur.
_EXAM_HUMAN_SHA = "332f4f7f738efd05ce5fb5a32af93e119f5ecaf784ba9cf9ef00c8f3ed8df11d"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _q(question: str, explanation: str = "Bu cavab doğrudur, çünki qayda belədir.") -> dict:
    return {"question": question, "options": ["went", "go", "goes", "going", "gone"],
            "correct_index": 0, "explanation": explanation}


class TestPrompts:
    def test_exam_prep_prompt_is_byte_identical(self):
        assert _sha(SYSTEM_PROMPT) == _EXAM_SYSTEM_SHA
        # Çətinlik qeydi (Faza 2, 2026-10-30) boş olanda şablon köhnə
        # şablonla BAYT-BAYT eynidir — bölgü seçilməyən yükləmə dəyişmir.
        assert _sha(_PROMPT.template.replace("{difficulty_note}", "")) == _EXAM_HUMAN_SHA
        assert system_prompt_for("exam_prep", "practice") is SYSTEM_PROMPT

    def test_english_practice_prompt(self):
        prompt = system_prompt_for("english", "practice")
        assert prompt != SYSTEM_PROMPT
        for must in ("B1", "Azerbaijani", "English", "will NOT see"):
            assert must in prompt, must

    def test_english_reading_prompt(self):
        prompt = system_prompt_for("english", "reading")
        assert "WILL see the passage" in prompt
        assert "Azerbaijani" in prompt

    @pytest.mark.parametrize("profile,kind", [("math", "practice"), ("exam_prep", "reading")])
    def test_unknown_combination_rejected(self, profile, kind):
        with pytest.raises(ValueError):
            system_prompt_for(profile, kind)

    def test_generate_for_chunks_uses_given_system_prompt(self):
        seen = []

        def completer(system, user):
            seen.append(system)
            return json.dumps({"questions": [_q("I ___ to school yesterday.")]})

        generate_for_chunks(["mətn"], {"groq": completer}, order=["groq"],
                            system_prompt=system_prompt_for("english", "practice"))
        assert seen == [system_prompt_for("english", "practice")]

    def test_default_system_prompt_is_exam_prep(self):
        seen = []

        def completer(system, user):
            seen.append(system)
            return json.dumps({"questions": [_q("Sual?")]})

        generate_for_chunks(["mətn"], {"groq": completer}, order=["groq"])
        assert seen == [SYSTEM_PROMPT]


class TestQualityProfiles:
    def _codes(self, questions, **kwargs):
        report = audit_questions([MCQQuestion(**q) for q in questions], **kwargs)
        return {f.code for f in report.findings}

    def test_english_material_reference_detected(self):
        codes = self._codes([_q("According to the text, what did Tom do on Sunday?")],
                            profile="english", bank_kind="practice")
        assert "materiala_istinad" in codes

    def test_reading_allows_text_questions(self):
        codes = self._codes([_q("According to the passage, what did Tom do on Sunday?")],
                            profile="english", bank_kind="reading")
        assert "materiala_istinad" not in codes

    def test_legal_checks_off_for_english(self):
        # «versiya» e-qanun metadata naxışıdır — ingilis kursunda mənasızdır.
        question = [_q("Which versiya is correct?")]
        assert "metadata_sual" in self._codes(question)  # imtahan profilində tutulur
        assert "metadata_sual" not in self._codes(question, profile="english", bank_kind="practice")

    def test_exam_prep_default_unchanged(self):
        default = self._codes([_q("Materialda qeyd olunan hansıdır?")])
        explicit = self._codes([_q("Materialda qeyd olunan hansıdır?")], profile="exam_prep")
        assert "materiala_istinad" in default
        assert default == explicit


# Bir-birindən FƏRQLİ suallar: `filter_duplicates` 85%+ oxşar mətni
# birləşdirir, «Q (0)», «Q (1)» kimi suallar bir suala enərdi.
_DISTINCT = [
    "She ___ her homework every evening.",
    "Which word means the opposite of 'cheap'?",
    "Choose the correct preposition: I was born ___ May.",
    "Which sentence is grammatically correct?",
    "What is the past form of the verb 'buy'?",
    "Pick the right article: He is ___ honest man.",
]
_DISTINCT_AZ = [
    "Materialda qeyd olunan dövlət orqanı hansıdır?",
    "Mətndə qeyd edilən müddət neçə gündür?",
    "Parçada adı çəkilən sənəd hansıdır?",
    "Yuxarıda qeyd olunan hüquq hansıdır?",
]
_READING = [
    "According to the passage, why does Tom like English?",
    "What does Tom do every day in the passage?",
    "Which title fits the passage best?",
    "In the passage, how often does Tom go to school?",
    "What can we infer about Tom from the passage?",
    "Which word in the passage means 'enjoys'?",
]


def _completer_returning(questions):
    def completer(system, user):
        return json.dumps({"questions": questions})
    return {"groq": completer}


def _long_text(paragraphs=40):
    return "\n\n".join(f"Paragraph {i}. Tom goes to school every day. He likes English." for i in range(paragraphs))


class TestPipelineProfiles:
    def test_english_practice_drops_text_recall_questions(self, monkeypatch):
        monkeypatch.setattr(pdf_extractor, "extract", lambda s: RawMaterial(text=_long_text(), metadata={}))
        good = [_q(text) for text in _DISTINCT[:4]]
        bad = [_q("According to the text, where does Tom go?")]
        result = generate_quiz(MaterialSource(kind="pdf", location="x.pdf"), 5,
                               completers=_completer_returning(good + bad), order=["groq"],
                               profile="english", bank_kind="practice")
        assert all("According to the text" not in q.question for q in result.questions)
        assert result.passage is None

    def test_exam_prep_drops_nothing(self, monkeypatch):
        """Mövcud davranış: audit yalnız hesabatdır, sual atılmır."""
        monkeypatch.setattr(pdf_extractor, "extract", lambda s: RawMaterial(text=_long_text(), metadata={}))
        questions = [_q(text) for text in _DISTINCT_AZ]
        result = generate_quiz(MaterialSource(kind="pdf", location="x.pdf"), 4,
                               completers=_completer_returning(questions), order=["groq"])
        assert len(result.questions) == 4

    def test_reading_uses_single_bounded_passage(self, monkeypatch):
        monkeypatch.setattr(pdf_extractor, "extract", lambda s: RawMaterial(text=_long_text(400), metadata={}))
        users = []

        def completer(system, user):
            users.append(user)
            return json.dumps({"questions": [_q(text) for text in _READING]})

        result = generate_quiz(MaterialSource(kind="pdf", location="x.pdf"), 6,
                               completers={"groq": completer}, order=["groq"],
                               profile="english", bank_kind="reading")
        assert len(users) == 1  # tək mətn = tək LLM çağırışı
        assert result.passage and len(result.passage) <= PASSAGE_MAX_CHARS
        assert result.passage.endswith(".")  # cümlə ortasında kəsilmir
        assert result.passage in users[0]
        assert len(result.questions) == 6  # reading-də mətnə istinad normaldır

    def test_reading_rejected_for_exam_prep(self):
        with pytest.raises(ValueError):
            generate_quiz(MaterialSource(kind="pdf", location="x.pdf"), 5,
                          completers=_completer_returning([]), order=["groq"],
                          profile="exam_prep", bank_kind="reading")


def test_pipeline_module_exports_passage_limit():
    assert pipeline_module.PASSAGE_MAX_CHARS >= 1500
