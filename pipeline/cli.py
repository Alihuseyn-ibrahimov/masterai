"""Əl ilə sınaq üçün giriş nöqtəsi.

İstifadə:
    .venv/bin/python -m pipeline.cli --pdf tests/fixtures/sample.pdf
    .venv/bin/python -m pipeline.cli --link https://example.az/ders
    .venv/bin/python -m pipeline.cli --image tests/fixtures/sample_image.png

GROQ_API_KEY / ANTHROPIC_API_KEY `.env`-dən (və ya mühit dəyişənlərindən)
oxunur — `build_completers()` vasitəsilə, real şəbəkə çağırışı edir.
"""

from __future__ import annotations

import argparse
import json
import sys

from pipeline.models import MaterialSource
from pipeline.pipeline import PipelineError, generate_quiz


def _build_source(args: argparse.Namespace) -> MaterialSource:
    if args.pdf:
        return MaterialSource(kind="pdf", location=args.pdf)
    if args.link:
        return MaterialSource(kind="link", location=args.link)
    return MaterialSource(kind="image", location=args.image)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MasterAI pipeline — əl ilə sınaq")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", help="PDF fayl yolu")
    group.add_argument("--link", help="Sayt linki")
    group.add_argument("--image", help="Şəkil fayl yolu")
    parser.add_argument("--questions-per-chunk", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    source = _build_source(args)

    try:
        result = generate_quiz(source, questions_per_chunk=args.questions_per_chunk)
    except PipelineError as exc:
        print(f"Pipeline uğursuz oldu: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    print(
        f"\n{len(result.questions)} sual, {result.chunks_processed} chunk "
        f"({result.chunks_failed} uğursuz)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
