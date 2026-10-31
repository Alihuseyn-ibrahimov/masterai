"""Çətinlik modeli üçün dataset: hər sualın REAL düzgün cavab faizi (gün 15).

Canlı sessiya və ev tapşırığı cavablarından sual üzrə «neçə cavab, neçəsi
düzgün» sayılır, sualın əlamətləri (`pipeline.difficulty_features`) yanına
yazılır. Tələbə adı, e-poçtu, ID-si CSV-yə DÜŞMÜR - yalnız sual ID-si,
əlamətlər və faiz. Bazalar yalnız OXUNUR (`mode=ro`).

Serverdə:

    cd /opt/masterai
    .venv/bin/python deploy/export_difficulty_data.py --data-dir data --out /root/cetinlik.csv

Sonra CSV-ni noutbuka/Colab-a köçür və `python -m ml.train_difficulty --csv ...` işlət.

Məhdudiyyət: cavab sualın bankdakı SIRASINA (`question_index`) bağlıdır. Sessiyadan
sonra bankdan sual silinibsə, sonrakı sualların statistikası sürüşər - belə banklar
nadirdir, amma `--min-answers` kiçik saxlanılmamalıdır.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.data import Row, write_csv  # noqa: E402
from pipeline.difficulty_features import extract  # noqa: E402
from pipeline.models import MCQQuestion  # noqa: E402


def _connect(path: str) -> sqlite3.Connection | None:
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def answer_stats(data_dir: str) -> dict[tuple[int, int], list[int]]:
    """(bank, sualın sırası) → [düzgün, cəmi]."""
    stats: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
    live = _connect(os.path.join(data_dir, "live_sessions.db"))
    if live is not None:
        for row in live.execute(
            "SELECT s.question_set_id AS qs, a.question_index AS idx, a.is_correct AS ok "
            "FROM live_answers a JOIN live_sessions s ON s.id = a.session_id"
        ):
            cell = stats[(row["qs"], row["idx"])]
            cell[0] += int(row["ok"])
            cell[1] += 1
        live.close()
    homework = _connect(os.path.join(data_dir, "homework.db"))
    if homework is not None:
        for row in homework.execute(
            "SELECT h.question_set_id AS qs, a.question_index AS idx, a.is_correct AS ok "
            "FROM homework_answers a JOIN homework_attempts t ON t.id = a.attempt_id "
            "JOIN homework_assignments h ON h.id = t.assignment_id"
        ):
            cell = stats[(row["qs"], row["idx"])]
            cell[0] += int(row["ok"])
            cell[1] += 1
        homework.close()
    return stats


def build_rows(data_dir: str, min_answers: int = 5) -> tuple[list[Row], list[dict]]:
    stats = answer_stats(data_dir)
    banks = _connect(os.path.join(data_dir, "question_sets.db"))
    if banks is None:
        raise SystemExit(f"question_sets.db tapılmadı: {data_dir}")
    rows, extra = [], []
    by_bank: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for q in banks.execute("SELECT id, question_set_id, question, options, correct_index, explanation, "
                           "difficulty FROM live_questions ORDER BY id"):
        by_bank[q["question_set_id"]].append(q)
    subjects = {r["id"]: r["subject"] for r in banks.execute("SELECT id, subject FROM question_sets")}
    banks.close()
    for bank_id, questions in by_bank.items():
        for index, q in enumerate(questions):
            correct, total = stats.get((bank_id, index), [0, 0])
            if total < min_answers:
                continue
            mcq = MCQQuestion(question=q["question"], options=json.loads(q["options"]),
                              correct_index=q["correct_index"], explanation=q["explanation"] or "",
                              difficulty=q["difficulty"])
            rows.append(Row(extract(mcq), correct / total, total, mcq.difficulty or ""))
            extra.append({"question_id": q["id"], "subject": subjects.get(bank_id, "")})
    return rows, extra


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sual üzrə real düzgün cavab faizi → CSV")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-answers", type=int, default=5)
    args = parser.parse_args(argv)
    rows, extra = build_rows(args.data_dir, args.min_answers)
    write_csv(args.out, rows, extra)
    answers = sum(r.answers for r in rows)
    print(f"{len(rows)} sual, {answers} cavab (sual başına ən azı {args.min_answers}) → {args.out}")
    if len(rows) < 100:
        print("Qeyd: etibarlı model üçün ~100+ sual tövsiyə olunur; az datada model bazanı keçməyə bilər.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
