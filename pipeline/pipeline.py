"""Pipeline orkestrator — material mənbəyindən `PipelineResult`-a qədər olan
bütün addımları (ingestion → chunking → generation → dedup) birləşdirir."""

from __future__ import annotations

from pipeline.chunking import split
from pipeline.dedup import filter_duplicates
from pipeline.generation import generate_for_chunks
from pipeline.ingestion import image_extractor, pdf_extractor, web_extractor
from pipeline.models import MaterialSource, PipelineResult, RawMaterial
from pipeline.providers import Completer, DEFAULT_ORDER, build_completers

_MIN_QUESTIONS = 3


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
    questions_per_chunk: int = 3,
    completers: dict[str, Completer] | None = None,
    order: list[str] = DEFAULT_ORDER,
) -> PipelineResult:
    raw = _extract(source)  # IngestionError susmadan yuxarı ötürülür

    chunks = split(raw.text)
    if not chunks:
        raise PipelineError(f"Materialdan chunk yaradıla bilmədi: {source.location}")

    if completers is None:
        completers = build_completers()

    questions, chunks_failed = generate_for_chunks(
        chunks, completers, order=order, questions_per_chunk=questions_per_chunk
    )
    questions = filter_duplicates(questions)

    if len(questions) < _MIN_QUESTIONS:
        raise PipelineError(
            f"Kifayət qədər keyfiyyətli sual alınmadı "
            f"({len(questions)} < {_MIN_QUESTIONS}): {source.location}"
        )

    return PipelineResult(
        questions=questions,
        source=source,
        chunks_processed=len(chunks),
        chunks_failed=chunks_failed,
    )
