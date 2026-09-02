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
    "köməkçisən. Yalnız verilən materiala əsaslan, uydurma məlumat işlətmə."
)

_RETRY_REMINDER = (
    "\n\nDİQQƏT: əvvəlki cavabın tələb olunan JSON sxeminə uyğun deyildi. "
    "Bu dəfə YALNIZ etibarlı JSON qaytar, əlavə mətn və ya izah yazma."
)


class _MCQBatch(BaseModel):
    questions: list[MCQQuestion]


_parser = PydanticOutputParser(pydantic_object=_MCQBatch)

_PROMPT = PromptTemplate.from_template(
    "Aşağıdakı dərs materialından {n} ədəd çoxseçimli (MCQ) test sualı hazırla.\n"
    "Hər sualın tam 5 variantı olmalıdır, yalnız biri düzgün, hər sualın öz "
    "izahı olmalıdır.\n\n"
    "Material:\n---\n{chunk}\n---\n\n{format_instructions}"
)


def _make_llm_runnable(completers: dict[str, Completer], order: list[str]) -> RunnableLambda:
    def call(prompt_value) -> str:
        return complete_with_fallback(SYSTEM_PROMPT, prompt_value.to_string(), order, completers)

    return RunnableLambda(call)


def _build_chain(completers: dict[str, Completer], order: list[str]):
    return _PROMPT | _make_llm_runnable(completers, order) | _parser


def _make_input(chunk: str, questions_per_chunk: int, *, retry: bool = False) -> dict:
    text = chunk + _RETRY_REMINDER if retry else chunk
    return {
        "chunk": text,
        "n": questions_per_chunk,
        "format_instructions": _parser.get_format_instructions(),
    }


def generate_for_chunks(
    chunks: list[str],
    completers: dict[str, Completer],
    order: list[str] = DEFAULT_ORDER,
    questions_per_chunk: int = 3,
) -> tuple[list[MCQQuestion], int]:
    """Hər chunk üçün `questions_per_chunk` ədəd MCQ sualı çıxarır.

    LCEL `.batch()` ilə paralel işlədilir. Sxem xətası olan chunk-lar bir
    dəfə (yenə paralel) retry olunur; retry-dan sonra da uğursuz olan
    chunk-lar `chunks_failed` sayına düşür, digər chunk-ları batırmır.
    Qaytarır: (bütün uğurlu suallar, uğursuz chunk sayı).
    """
    if not chunks:
        return [], 0

    chain = _build_chain(completers, order)

    first_pass = chain.batch(
        [_make_input(c, questions_per_chunk) for c in chunks],
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
            [_make_input(chunks[i], questions_per_chunk, retry=True) for i in retry_indices],
            return_exceptions=True,
        )
        for result in retry_pass:
            if isinstance(result, Exception):
                failed += 1
            else:
                questions.extend(result.questions)

    return questions, failed
