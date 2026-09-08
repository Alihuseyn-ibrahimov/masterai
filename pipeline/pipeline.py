"""Pipeline orkestrator — material mənbəyindən `PipelineResult`-a qədər olan
bütün addımları (ingestion → chunking → generation → dedup) birləşdirir."""

from __future__ import annotations

import math

from pipeline.chunking import split
from pipeline.dedup import filter_duplicates
from pipeline.generation import generate_for_chunks
from pipeline.ingestion import image_extractor, pdf_extractor, web_extractor
from pipeline.models import MaterialSource, PipelineResult, RawMaterial
from pipeline.providers import Completer, DEFAULT_ORDER, build_completers

_MIN_QUESTIONS = 3
DEFAULT_TARGET_QUESTION_COUNT = 10


class PipelineError(Exception):
    """Pipeline uğurlu, keyfiyyətli nəticə istehsal edə bilmədikdə atılır."""


def _extract(source: MaterialSource) -> RawMaterial:
    if source.kind == "link":
        return web_extractor.extract(source)
    if source.kind == "pdf":
        return pdf_extractor.extract(source)
    return image_extractor.extract(source)


def generate_quiz(
    source: MaterialSource,
    target_question_count: int = DEFAULT_TARGET_QUESTION_COUNT,
    completers: dict[str, Completer] | None = None,
    order: list[str] = DEFAULT_ORDER,
) -> PipelineResult:
    """`target_question_count` — çağıranın (müəllimin) istədiyi ÜMUMİ sual
    sayı (bax dizayn sənədi, 2026-09-08). Material neçə chunk-a bölünürsə,
    hər birindən `ceil(target/chunk_sayı)` sual istənilir (dedup-da itki
    ehtimalına qarşı "bir az artıq" istəmək lazımdır), dedup-dan sonra
    `target`-dan çox qalarsa İLK `target` sual saxlanılır. Material qısadırsa
    (target-a çatmasa) olduğu kimi qəbul edilir — yalnız `_MIN_QUESTIONS`
    alt həddi məcburidir."""
    raw = _extract(source)  # IngestionError susmadan yuxarı ötürülür

    chunks = split(raw.text)
    if not chunks:
        raise PipelineError(f"Materialdan chunk yaradıla bilmədi: {source.location}")

    if completers is None:
        completers = build_completers()

    questions_per_chunk = max(1, math.ceil(target_question_count / len(chunks)))
    questions, chunks_failed = generate_for_chunks(
        chunks, completers, order=order, questions_per_chunk=questions_per_chunk
    )
    questions = filter_duplicates(questions)

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
    )
