"""Kod tapşırıqlarının yoxlanması (gün 19).

    pip install -r requirements-autogen.txt          # AutoGen (ayrı venv); Docker da lazımdır
    python -m code_checker.cli list
    python -m code_checker.cli check --exercise cut_ededlerin_cemi --file telebe.py
    python -m code_checker.cli check --exercise cut_ededlerin_cemi --file telebe.py --no-ai
    python -m code_checker.cli batch --exercise cut_ededlerin_cemi --dir cavablar/ --out qiymetler.csv

`batch`: qovluqdakı hər `.py` faylı bir tələbədir (fayl adı = tələbə). CSV-də bal
testlərdəndir; `--ai` verilsə mentorun rəyi də yazılır (hər fayl üçün LLM çağırışı).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from code_checker.exercises import list_exercises, load_exercise, run_tests
from code_checker.sandbox import docker_available

MAX_CODE_BYTES = 50_000


def _read_code(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_CODE_BYTES:
        raise ValueError(f"{path.name}: fayl çox böyükdür ({len(data)} bayt)")
    return data.decode("utf-8", errors="replace")


def main(argv: list[str] | None = None, *, reviewer=None) -> int:
    parser = argparse.ArgumentParser(description="Docker + AutoGen kod yoxlayıcısı")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p_check = sub.add_parser("check")
    p_check.add_argument("--exercise", required=True)
    p_check.add_argument("--file", type=Path, required=True)
    p_check.add_argument("--no-ai", action="store_true", help="yalnız testlər, agentsiz")
    p_batch = sub.add_parser("batch")
    p_batch.add_argument("--exercise", required=True)
    p_batch.add_argument("--dir", type=Path, required=True)
    p_batch.add_argument("--out", type=Path, required=True)
    p_batch.add_argument("--ai", action="store_true", help="hər fayl üçün mentor rəyi də")
    args = parser.parse_args(argv)

    if args.command == "list":
        for ex in list_exercises():
            print(f"{ex.id:<28} {ex.title} · {len(ex.tests)} test · {ex.lesson}")
        return 0
    if not docker_available():
        print("Docker işləmir: tələbə kodu yalnız sandbox-da işlədilir (Docker Desktop-u aç).")
        return 2
    exercise = load_exercise(args.exercise)

    def ai_review(code):
        if reviewer is not None:
            return reviewer(exercise, code)
        from code_checker.team import model_client_from_env, review

        return review(exercise, code, reviewer_client=model_client_from_env())

    if args.command == "check":
        code = _read_code(args.file)
        if args.no_ai:
            report = run_tests(exercise, code)
            print(report.summary())
        else:
            result = ai_review(code)
            report = result.report
            print(report.summary())
            print("\nMentorun rəyi:\n" + result.feedback)
        return 0 if report.passed == report.total else 1

    rows = []
    for path in sorted(args.dir.glob("*.py")):
        try:
            code = _read_code(path)
        except ValueError as exc:
            rows.append({"student": path.stem, "passed": 0, "total": len(exercise.tests), "score": 0.0,
                         "error": str(exc), "feedback": ""})
            continue
        if args.ai:
            result = ai_review(code)
            report, feedback = result.report, result.feedback
        else:
            report, feedback = run_tests(exercise, code), ""
        rows.append({"student": path.stem, "passed": report.passed, "total": report.total, "score": report.score,
                     "error": report.error, "feedback": feedback})
        print(f"{path.stem:<24} {report.passed}/{report.total}")
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["student", "passed", "total", "score", "error", "feedback"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} tələbə → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
