"""Pipeline orkestrator — material mənbəyindən `PipelineResult`-a qədər olan
bütün addımları (ingestion → chunking → generation → dedup) birləşdirir."""

from __future__ import annotations

import math

from pipeline.chunking import split
from pipeline.dedup import filter_duplicates
from pipeline.generation import generate_for_chunks, system_prompt_for
from pipeline.ingestion import image_extractor, pdf_extractor, web_extractor
from pipeline.models import MaterialSource, PipelineResult, RawMaterial
from pipeline.providers import Completer, DEFAULT_ORDER, build_completers
from pipeline.quality import recalls_material

_MIN_QUESTIONS = 3
DEFAULT_TARGET_QUESTION_COUNT = 10

# Real production-da tapılıb (e-qanun.az, 389 min simvolluq qanun mətni):
# böyük sənəd 65 chunk-a bölünürdü və HAMISI LLM-ə (paralel) göndərilirdi —
# 10 sual üçün 65 API çağırışı. Groq-un pulsuz tarif limiti (8000 token/
# dəqiqə) bununla dərhal aşılır, hər chunk 429 alıb təkrar-təkrar cəhd edir,
# emal dəqiqələrlə "hazırlanır" vəziyyətində ilişib qalır. Həlli: istənilən
# sual sayına görə LAZIM OLAN qədər chunk seçmək (dedup itkisinə qarşı
# bir qədər ehtiyatla), bütün sənədi deyil.
_CHUNKS_PER_QUESTION_BUFFER = 2


# Reading mətni tələbəyə telefonda göstərilir: ~3000 simvol (≈500 söz)
# B1 səviyyəsi üçün bir oxu tapşırığıdır, daha uzunu ekranda itir.
PASSAGE_MAX_CHARS = 3000


def make_passage(text: str, max_chars: int = PASSAGE_MAX_CHARS) -> str:
    """Materialın əvvəlindən oxu mətni — CÜMLƏ SƏRHƏDİNDƏ kəsilir.
    Cümlə ortasında kəsilmiş mətn tələbəni çaşdırar, sual isə yarımçıq
    cümləyə istinad edə bilər."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    cut = max(head.rfind(". "), head.rfind(".\n"), head.rfind("? "), head.rfind("! "))
    return head[: cut + 1].strip() if cut > 0 else head.strip()


class PipelineError(Exception):
    """Pipeline uğurlu, keyfiyyətli nəticə istehsal edə bilmədikdə atılır."""


def _extract(source: MaterialSource) -> RawMaterial:
    if source.kind == "link":
        return web_extractor.extract(source)
    if source.kind == "pdf":
        return pdf_extractor.extract(source)
    return image_extractor.extract(source)


def _select_chunks(chunks: list[str], target_question_count: int) -> list[str]:
    """Sənəd boyu BƏRABƏR paylanmış şəkildə lazım olan qədər chunk seçir.

    Yalnız ilk N chunk-ı götürmək mövzu müxtəlifliyini itirər (qanunun
    yalnız girişindən sual çıxar) — ona görə addımlı (interval) seçim
    edilir. Chunk sayı onsuz da azdırsa, hamısı saxlanılır."""
    max_chunks = max(1, target_question_count * _CHUNKS_PER_QUESTION_BUFFER)
    if len(chunks) <= max_chunks:
        return chunks

    step = len(chunks) / max_chunks
    indices = sorted({int(i * step) for i in range(max_chunks)})
    return [chunks[i] for i in indices]


def generate_quiz(
    source: MaterialSource,
    target_question_count: int = DEFAULT_TARGET_QUESTION_COUNT,
    completers: dict[str, Completer] | None = None,
    order: list[str] = DEFAULT_ORDER,
    profile: str = "exam_prep",
    bank_kind: str = "practice",
) -> PipelineResult:
    """`target_question_count` — çağıranın (müəllimin) istədiyi ÜMUMİ sual
    sayı (bax dizayn sənədi, 2026-09-08). Material neçə chunk-a bölünürsə,
    hər birindən `ceil(target/chunk_sayı)` sual istənilir (dedup-da itki
    ehtimalına qarşı "bir az artıq" istəmək lazımdır), dedup-dan sonra
    `target`-dan çox qalarsa İLK `target` sual saxlanılır. Material qısadırsa
    (target-a çatmasa) olduğu kimi qəbul edilir — yalnız `_MIN_QUESTIONS`
    alt həddi məcburidir."""
    # Profil/bank cütü ƏVVƏLCƏ yoxlanır: yanlış cüt (məs. imtahan kursunda
    # reading) material yüklənib LLM-ə pul xərclənmədən rədd olunmalıdır.
    system_prompt = system_prompt_for(profile, bank_kind)

    raw = _extract(source)  # IngestionError susmadan yuxarı ötürülür

    passage = None
    if bank_kind == "reading":
        # Reading: TƏK mətn, tələbəyə göstəriləcək məhz odur — suallar
        # başqa hissədən qurulsa, tələbə cavabı mətndə tapa bilməz.
        passage = make_passage(raw.text)
        chunks = [passage] if passage else []
    else:
        chunks = split(raw.text)
    if not chunks:
        raise PipelineError(f"Materialdan chunk yaradıla bilmədi: {source.location}")

    if completers is None:
        completers = build_completers()

    if passage is None:
        chunks = _select_chunks(chunks, target_question_count)
    questions_per_chunk = max(1, math.ceil(target_question_count / len(chunks)))
    questions, chunks_failed = generate_for_chunks(
        chunks, completers, order=order, questions_per_chunk=questions_per_chunk,
        system_prompt=system_prompt,
    )
    questions = filter_duplicates(questions)
    questions = [q for q in questions if not recalls_material(q, profile, bank_kind)]

    if len(questions) < _MIN_QUESTIONS:
        raise PipelineError(
            f"Kifayət qədər keyfiyyətli sual alınmadı "
            f"({len(questions)} < {_MIN_QUESTIONS}): {source.location}"
        )

    if len(questions) > target_question_count:
        questions = questions[:target_question_count]

    return PipelineResult(
        questions=questions,
        source=source,
        chunks_processed=len(chunks),
        chunks_failed=chunks_failed,
        requested_question_count=target_question_count,
        passage=passage,
    )
