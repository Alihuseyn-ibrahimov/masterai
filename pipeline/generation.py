"""LCEL əsaslı sual generasiyası — material chunk-larından MCQ sualları.

Zəncir: `prompt | llm (fallback) | PydanticOutputParser`. `llm` addımı
`pipeline.providers.complete_with_fallback`-ı `RunnableLambda` kimi
sarıyır — beləliklə Groq/Claude/Ollama fallback məntiqi (Faza 4) LCEL
kompozisiyasının için saxlanılır, təkrarlanmır.
"""

from __future__ import annotations

from pydantic import BaseModel

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda

from pipeline.models import MCQQuestion
from pipeline.providers import Completer, DEFAULT_ORDER, complete_with_fallback

SYSTEM_PROMPT = (
    "Sən Azərbaycan dilində dövlət qulluğu və magistratura imtahanlarına "
    "hazırlıq üçün keyfiyyətli çoxseçimli (MCQ) test sualları hazırlayan bir "
    "köməkçisən. Yalnız verilən materiala əsaslan, uydurma məlumat işlətmə. "
    "Material bəzən sayt naviqasiyası, düymə/tab adları (məs. \"Yüklə\", "
    "\"Versiyalar\", \"Qüvvədədir\") kimi sənədin ƏSAS MƏZMUNUNA aid "
    "OLMAYAN mətn hissələri ehtiva edə bilər — belə hissələr üzrə HEÇ VAXT "
    "sual hazırlama, yalnız sənədin özünün faktiki məzmunundan (mövzu, "
    "maddə, anlayış və s.) sual qur."
)

# ---- Kurs profilləri (spec 2026-09-29 §5) --------------------------------
# `SYSTEM_PROMPT` (yuxarıda) `exam_prep` profilidir və BAYT-BAYT dəyişməz
# qalır (`tests/test_course_profiles.py` hash ilə yoxlayır) — mövcud
# imtahan kursu üçün heç nə dəyişməməlidir.
#
# İngilis promptları QƏSDƏN ingiliscədir: çıxış (sual və variantlar)
# ingiliscədir və model təlimatı çıxışın dilində daha dəqiq izləyir.

ENGLISH_PRACTICE_PROMPT = (
    "You write multiple-choice questions for an English course in Azerbaijan. "
    "The learners are at CEFR level A2-B1; never go above B1. "
    "Use ONLY the given lesson material as the source of vocabulary and grammar. "
    "Write the question and all 5 options in simple English: short sentences, "
    "B1 vocabulary or below, no idioms, no rare grammar. "
    "Write the explanation in Azerbaijani (1-2 sentences): explain WHY the correct "
    "option is right - the grammar rule or the meaning - not just repeat it. "
    "Question types: vocabulary (meaning, synonym, the right word in context), "
    "grammar (fill in the blank marked ___ : tense, preposition, article, word form) "
    "and usage (which sentence is correct). "
    "The learner will NOT see the material during the quiz: never ask what the "
    "text, passage, story or author says, and never ask to recall facts or events "
    "from the material. "
    "The material may contain website navigation, buttons or menus - never write "
    "questions about them."
)

ENGLISH_READING_PROMPT = (
    "You write reading comprehension multiple-choice questions for an English "
    "course in Azerbaijan. The learners are at CEFR level A2-B1; never go above B1. "
    "The learner WILL see the passage while answering, so questions about the "
    "passage are expected: main idea, specific details, vocabulary in context "
    "and simple inference. Use ONLY information from the passage. "
    "Write the question and all 5 options in simple English (B1 or below). "
    "Write the explanation in Azerbaijani (1-2 sentences) and point to the "
    "sentence in the passage that proves the answer."
)

_PROMPTS = {
    ("exam_prep", "practice"): SYSTEM_PROMPT,
    ("english", "practice"): ENGLISH_PRACTICE_PROMPT,
    ("english", "reading"): ENGLISH_READING_PROMPT,
}


def system_prompt_for(profile: str, bank_kind: str) -> str:
    """Profil + bank növü üçün sistem promptu. Naməlum cüt — xəta: səssizcə
    imtahan promptuna düşmək ingilis kursuna azərbaycanca hüquq sualları
    verərdi."""
    try:
        return _PROMPTS[(profile, bank_kind)]
    except KeyError:
        raise ValueError(f"Naməlum profil/bank növü: {profile}/{bank_kind}") from None


_RETRY_REMINDER = (
    "DİQQƏT: əvvəlki cavabın tələb olunan JSON sxeminə uyğun deyildi. "
    "Bu dəfə YALNIZ etibarlı JSON qaytar, əlavə mətn və ya izah yazma.\n\n"
)


# Real production-da tapılıb: `.batch()` defolt olaraq BÜTÜN chunk-ları
# eyni anda göndərir — Groq-un pulsuz tarif limiti (8000 token/dəqiqə)
# dərhal aşılır, hər chunk 429 alır və emal dəqiqələrlə ilişib qalır.
# Az sayda eyni-anda sorğu limitin bərpasına imkan verir (fon prosesində
# işlədiyi üçün bir qədər yavaş olması qəbul ediləndir).
_MAX_CONCURRENCY = 2


class _MCQBatch(BaseModel):
    questions: list[MCQQuestion]


_parser = PydanticOutputParser(pydantic_object=_MCQBatch)

# Variant uzunluğu qaydası (2026-10-30, istifadəçi şikayəti): model düzgün
# cavabı izahlı, uzun yazırdı - tələbə materialı bilmədən ən uzun variantı
# seçirdi. Prompt qaydası + `quality.answer_stands_out` filtri birlikdə.
_PROMPT = PromptTemplate.from_template(
    "Aşağıdakı dərs materialından {n} ədəd çoxseçimli (MCQ) test sualı hazırla.\n"
    "Hər sualın tam 5 variantı olmalıdır, yalnız biri düzgün, hər sualın öz "
    "izahı olmalıdır.\n"
    "Düzgün variant uzunluğu və təfsilatı ilə seçilməməlidir: 5 variantın "
    "hamısı təxminən eyni uzunluqda olsun, düzgün cavab ən uzun variant olmasın.\n\n"
    "Material:\n---\n{chunk}\n---\n\n{subject_note}{difficulty_note}{retry_note}{format_instructions}"
)


def _make_llm_runnable(
    completers: dict[str, Completer], order: list[str], system_prompt: str
) -> RunnableLambda:
    def call(prompt_value) -> str:
        return complete_with_fallback(system_prompt, prompt_value.to_string(), order, completers)

    return RunnableLambda(call)


def _build_chain(completers: dict[str, Completer], order: list[str], system_prompt: str):
    return _PROMPT | _make_llm_runnable(completers, order, system_prompt) | _parser


def _make_input(
    chunk: str, questions_per_chunk: int, *, retry: bool = False, difficulty_note: str = "",
    subject_note: str = "",
) -> dict:
    # Real testdə tapılıb: retry xəbərdarlığı əvvəllər `chunk`-a (yəni
    # "Material:" bölməsinin İÇİNƏ) əlavə olunurdu — AI onu materialın
    # bir hissəsi kimi oxuyub ÖZ HAQQINDA sual düzəldirdi (məs. "Which
    # phrase warns about the previous answer format?"). İndi ayrıca
    # `retry_note` dəyişəni ilə "Material:" bloкundan KƏNARDA, təlimat
    # hissəsində yerləşir.
    return {
        "chunk": chunk,
        "n": questions_per_chunk,
        "retry_note": _RETRY_REMINDER if retry else "",
        # Çətinlik bölgüsü (Faza 2) — `retry_note` kimi "Material:"
        # blokundan KƏNARDA: model onu materialın hissəsi saymasın.
        "difficulty_note": difficulty_note,
        # Fənn qaydası (bax `pipeline/subjects.py`) - eyni səbəbdən kənarda.
        "subject_note": subject_note,
        "format_instructions": _parser.get_format_instructions(),
    }


def user_prompt(chunk: str, questions_per_chunk: int, *, subject_note: str = "", difficulty_note: str = "") -> str:
    """Produksiyada modelə gedən istifadəçi mesajı - bayt-bayt eyni. Fine-tune dataseti
    (gün 16) və öz modelimizin serving-i (gün 17) məhz bu mətni işlədir: öyrətmə ilə
    istifadə arasında prompt fərqi modelin keyfiyyətini sükutla aşağı salardı."""
    return _PROMPT.format(**_make_input(chunk, questions_per_chunk, subject_note=subject_note,
                                        difficulty_note=difficulty_note))


def generate_for_chunks(
    chunks: list[str],
    completers: dict[str, Completer],
    order: list[str] = DEFAULT_ORDER,
    questions_per_chunk: int = 3,
    system_prompt: str = SYSTEM_PROMPT,
    difficulty_note: str = "",
    subject_note: str = "",
) -> tuple[list[MCQQuestion], int]:
    """Hər chunk üçün `questions_per_chunk` ədəd MCQ sualı çıxarır.

    LCEL `.batch()` ilə paralel işlədilir. Sxem xətası olan chunk-lar bir
    dəfə (yenə paralel) retry olunur; retry-dan sonra da uğursuz olan
    chunk-lar `chunks_failed` sayına düşür, digər chunk-ları batırmır.
    Qaytarır: (bütün uğurlu suallar, uğursuz chunk sayı).
    """
    if not chunks:
        return [], 0

    chain = _build_chain(completers, order, system_prompt)

    first_pass = chain.batch(
        [_make_input(c, questions_per_chunk, difficulty_note=difficulty_note, subject_note=subject_note)
         for c in chunks],
        config={"max_concurrency": _MAX_CONCURRENCY},
        return_exceptions=True,
    )

    questions: list[MCQQuestion] = []
    retry_indices: list[int] = []
    for i, result in enumerate(first_pass):
        if isinstance(result, Exception):
            retry_indices.append(i)
        else:
            questions.extend(result.questions)

    failed = 0
    if retry_indices:
        retry_pass = chain.batch(
            [
                _make_input(chunks[i], questions_per_chunk, retry=True, difficulty_note=difficulty_note,
                            subject_note=subject_note)
                for i in retry_indices
            ],
            config={"max_concurrency": _MAX_CONCURRENCY},
            return_exceptions=True,
        )
        for result in retry_pass:
            if isinstance(result, Exception):
                failed += 1
            else:
                questions.extend(result.questions)

    return questions, failed


def parse_questions(text: str) -> list[MCQQuestion]:
    """Model cavabı → suallar (produksiya ilə eyni parser). Pozuq JSON-da xəta atır."""
    return _parser.parse(text).questions
