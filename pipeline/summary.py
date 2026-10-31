"""Dərs xülasəsi (Faza 3, 2026-10-30) — yüklənmiş materialdan qısa xülasə.

Quruluş (plan sənədi): mövzu başlığı + 1-2 cümləlik giriş, 5-8 əsas fikir,
açar terminlər, yadda saxlanmalı rəqəm/tarix/maddələr, 3 özünü yoxla sualı.

Uzun material üçün iki addım (map → reduce): əvvəlcə seçilmiş hissələrin
hər birindən qısa qeyd çıxarılır, sonra qeydlər TƏK xülasədə birləşir.
Bütün sənədi bir sorğuya sığdırmaq Groq-un dəqiqəlik token limitini aşır
(bax `pipeline.py`-dakı 65 chunk dərsi).

**Uydurmaya qarşı ucuz yoxlama:** rəqəm daşıyan fikir və faktlarda HƏR
rəqəm mənbə mətnində olmalıdır, yoxdursa həmin maddə atılır. Tarixi,
maddə nömrəsini və məbləği səhv yazan xülasə tələbəyə səhv öyrədir —
bu, xülasənin ən təhlükəli və ən asan yoxlanan xətasıdır.
"""

from __future__ import annotations

import re

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from pipeline.chunking import split
from pipeline.ingestion import image_extractor, pdf_extractor, text_extractor, web_extractor
from pipeline.models import MaterialSource
from pipeline.providers import Completer, DEFAULT_ORDER, build_completers, complete_with_fallback

# Bu həddə qədər mətn TƏK sorğuda xülasə olunur (~3000 token).
SINGLE_PASS_CHARS = 12000
# Uzun materialda ən çox bu qədər hissədən qeyd çıxarılır (sənəd boyu
# bərabər paylanmış) — 6 hissə + 1 birləşdirmə = 7 LLM çağırışı.
MAX_PARTS = 6
_MAX_CONCURRENCY = 2

SUMMARY_SYSTEM_PROMPT = (
    "Sən Azərbaycan dilində dövlət qulluğu və magistratura imtahanlarına "
    "hazırlaşan tələbələr üçün qısa dərs xülasəsi hazırlayan köməkçisən. "
    "YALNIZ verilən materiala əsaslan: materialda olmayan fakt, tarix, rəqəm "
    "və ya maddə nömrəsi yazma. Sayt naviqasiyası, düymə və menyu mətnlərini "
    "nəzərə alma. Aydın, sadə cümlələrlə yaz."
)


class KeyTerm(BaseModel):
    term: str = Field(description="Termin")
    definition: str = Field(description="Terminin bir cümləlik izahı")


class SelfCheck(BaseModel):
    question: str = Field(description="Qısa yoxlama sualı")
    answer: str = Field(description="Qısa cavab")


class LessonSummary(BaseModel):
    title: str = Field(description="Mövzu başlığı")
    intro: str = Field(description="1-2 cümləlik giriş")
    key_points: list[str] = Field(description="5-8 əsas fikir")
    terms: list[KeyTerm] = Field(default_factory=list, description="Açar terminlər")
    facts: list[str] = Field(
        default_factory=list, description="Yadda saxlanmalı rəqəmlər, tarixlər, maddə nömrələri"
    )
    self_check: list[SelfCheck] = Field(default_factory=list, description="3 özünü yoxla sualı")


class SummaryError(Exception):
    """Materialdan istifadəyə yararlı xülasə alınmadı."""


_parser = PydanticOutputParser(pydantic_object=LessonSummary)

_NOTES_PROMPT = PromptTemplate.from_template(
    "Aşağıdakı dərs materialı hissəsindən ən vacib məlumatları qısa qeydlər "
    "kimi yaz (ən çox 8 maddə). Rəqəm, tarix və maddə nömrələrini olduğu kimi "
    "saxla.\n\nMaterial:\n---\n{chunk}\n---"
)

_SUMMARY_PROMPT = PromptTemplate.from_template(
    "Aşağıdakı {source_label} əsasında dərs xülasəsi hazırla:\n"
    "- title: mövzu başlığı\n"
    "- intro: 1-2 cümləlik giriş\n"
    "- key_points: 5-8 əsas fikir\n"
    "- terms: ən çox 8 açar termin və bir cümləlik izahı\n"
    "- facts: yadda saxlanmalı rəqəmlər, tarixlər, maddə nömrələri (materialda yoxdursa boş)\n"
    "- self_check: 3 qısa özünü yoxla sualı və cavabı\n\n"
    "Material:\n---\n{text}\n---\n\n{retry_note}{format_instructions}"
)

_RETRY_REMINDER = (
    "DİQQƏT: əvvəlki cavab tələb olunan JSON formatında deyildi. YALNIZ "
    "aşağıdakı sxemə uyğun JSON qaytar, başqa mətn yazma.\n\n"
)

_LIMITS = {"key_points": 8, "terms": 8, "facts": 10, "self_check": 3}
_NUMBER_RE = re.compile(r"\d+")


def _extract_text(source: MaterialSource) -> str:
    if source.kind == "link":
        return web_extractor.extract(source).text
    if source.kind == "pdf":
        return pdf_extractor.extract(source).text
    if source.kind == "text":
        return text_extractor.extract(source).text
    return image_extractor.extract(source).text


# Başqa modullar (gün 10 yoxlama komandası) eyni çıxarışı işlədir.
extract_material_text = _extract_text


def _spread(chunks: list[str], limit: int) -> list[str]:
    """Sənəd boyu bərabər paylanmış `limit` hissə — yalnız girişi deyil."""
    if len(chunks) <= limit:
        return chunks
    step = len(chunks) / limit
    return [chunks[int(i * step)] for i in range(limit)]


def _llm(completers: dict[str, Completer], order: list[str]) -> RunnableLambda:
    return RunnableLambda(
        lambda prompt: complete_with_fallback(SUMMARY_SYSTEM_PROMPT, prompt.to_string(), order, completers)
    )


def _numbers_grounded(text: str, source_numbers: set[str]) -> bool:
    return all(number in source_numbers for number in _NUMBER_RE.findall(text))


def ground(summary: LessonSummary, source_text: str) -> LessonSummary:
    """Mənbədə olmayan rəqəm daşıyan fikir/faktı atır və siyahıları kəsir."""
    source_numbers = set(_NUMBER_RE.findall(source_text))
    key_points = [p for p in summary.key_points if _numbers_grounded(p, source_numbers)]
    facts = [f for f in summary.facts if _numbers_grounded(f, source_numbers)]
    return summary.model_copy(update={
        "key_points": key_points[: _LIMITS["key_points"]],
        "terms": summary.terms[: _LIMITS["terms"]],
        "facts": facts[: _LIMITS["facts"]],
        "self_check": summary.self_check[: _LIMITS["self_check"]],
    })


def summarize_material(
    source: MaterialSource,
    completers: dict[str, Completer] | None = None,
    order: list[str] = DEFAULT_ORDER,
) -> LessonSummary:
    text = _extract_text(source).strip()  # IngestionError susmadan yuxarı ötürülür
    if not text:
        raise SummaryError(f"Materialdan mətn çıxarıla bilmədi: {source.location}")
    if completers is None:
        completers = build_completers()
    llm = _llm(completers, order)

    if len(text) <= SINGLE_PASS_CHARS:
        body, label = text, "dərs materialı"
    else:
        parts = _spread(split(text), MAX_PARTS)
        notes_chain = _NOTES_PROMPT | llm | StrOutputParser()
        results = notes_chain.batch(
            [{"chunk": part} for part in parts],
            config={"max_concurrency": _MAX_CONCURRENCY},
            return_exceptions=True,
        )
        notes = [r for r in results if not isinstance(r, Exception)]
        if not notes:
            raise SummaryError("Materialın heç bir hissəsindən qeyd çıxarıla bilmədi")
        body = "\n\n".join(notes)
        label = "dərs materialının hissə-hissə qeydləri"

    chain = _SUMMARY_PROMPT | llm | _parser
    inputs = {"text": body, "source_label": label, "format_instructions": _parser.get_format_instructions()}
    try:
        summary = chain.invoke({**inputs, "retry_note": ""})
    except Exception:  # noqa: BLE001 — sxem xətası bir dəfə təkrar sınanır
        try:
            summary = chain.invoke({**inputs, "retry_note": _RETRY_REMINDER})
        except Exception as exc:  # noqa: BLE001
            raise SummaryError(f"Xülasə alınmadı: {exc}") from exc

    summary = ground(summary, text)
    if len(summary.key_points) < 2:
        raise SummaryError("Xülasədə kifayət qədər əsas fikir alınmadı")
    return summary
