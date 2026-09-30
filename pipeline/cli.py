"""Əl ilə sınaq üçün giriş nöqtəsi.

İstifadə:
    .venv/bin/python -m pipeline.cli --pdf tests/fixtures/sample.pdf
    .venv/bin/python -m pipeline.cli --link https://example.az/ders
    .venv/bin/python -m pipeline.cli --image tests/fixtures/sample_image.png

İngilis dili kursu - müəllimin qiymətləndirməsi üçün (spec 2026-09-29 §5):
    .venv/bin/python -m pipeline.cli --pdf unit1.pdf --profile english \
        --question-count 30 --review-csv unit1.csv
    .venv/bin/python -m pipeline.cli --pdf story.pdf --profile english \
        --bank-kind reading --question-count 10 --review-csv story.csv

GROQ_API_KEY / ANTHROPIC_API_KEY `.env`-dən (və ya mühit dəyişənlərindən)
oxunur — `build_completers()` vasitəsilə, real şəbəkə çağırışı edir.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from pipeline.models import MaterialSource, PipelineResult
from pipeline.pipeline import PipelineError, generate_quiz
from pipeline.quality import audit_questions

_LETTERS = "ABCDE"


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
    parser.add_argument("--question-count", type=int, default=10)
    parser.add_argument("--profile", choices=["exam_prep", "english"], default="exam_prep")
    parser.add_argument("--bank-kind", choices=["practice", "reading"], default="practice")
    parser.add_argument(
        "--review-csv",
        help="Müəllimin qiymətləndirmə cədvəli (Excel/Google Sheets-də açılır)",
    )
    return parser


def _write_review_sheet(path: Path, result: PipelineResult, profile: str, bank_kind: str) -> None:
    """Müəllim hər sualı DOLDURUR: doğrudurmu, səviyyəyə uyğundurmu. Audit
    qeydləri müəllimə hansı sualı daha diqqətlə oxumalı olduğunu göstərir.
    `utf-8-sig`: BOM olmasa Excel faylı ANSI kimi açır və «ə» pozulur."""
    report = audit_questions(result.questions, profile=profile, bank_kind=bank_kind)
    notes: dict[int, list[str]] = {}
    for finding in report.findings:
        if finding.question_number is not None:
            notes.setdefault(finding.question_number, []).append(finding.message)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "№", "Sual", *_LETTERS, "Düzgün cavab", "İzah", "Audit qeydi",
            "Doğrudur? (hə/yox)", "Səviyyə (A2/B1/çətin)", "Müəllimin qeydi",
        ])
        for number, question in enumerate(result.questions, start=1):
            writer.writerow([
                number, question.question, *question.options,
                _LETTERS[question.correct_index], question.explanation,
                "; ".join(notes.get(number, [])), "", "", "",
            ])
    if result.passage:
        path.with_name(f"{path.stem}_metn.txt").write_text(result.passage, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    source = _build_source(args)

    try:
        result = generate_quiz(
            source,
            target_question_count=args.question_count,
            profile=args.profile,
            bank_kind=args.bank_kind,
        )
    except PipelineError as exc:
        print(f"Pipeline uğursuz oldu: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    if args.review_csv:
        _write_review_sheet(Path(args.review_csv), result, args.profile, args.bank_kind)
        print(f"Qiymətləndirmə cədvəli: {args.review_csv}", file=sys.stderr)
    print(
        f"\n{len(result.questions)} sual, {result.chunks_processed} chunk "
        f"({result.chunks_failed} uğursuz)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
