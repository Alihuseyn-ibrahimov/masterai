"""Sual dəstinin keyfiyyətini yoxlamaq üçün giriş nöqtəsi.

Serverdə işlədilir (real baza oradadır):

    cd /opt/masterai
    .venv/bin/python -m pipeline.audit --list
    .venv/bin/python -m pipeline.audit --set 3 --out /tmp/sual-yoxlama.txt

`--out` verilməsə nəticə ekrana yazılır.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from pipeline.models import MCQQuestion
from pipeline.quality import audit_questions
from pipeline.quality_report import format_review_sheet

DEFAULT_DB = "question_sets.db"


def _connect(path: str) -> sqlite3.Connection:
    if not Path(path).exists():
        raise SystemExit(
            f"Baza tapılmadı: {path}\n"
            "Serverdə servisin işlədiyi qovluqdan çağırın və ya --db ilə yol verin."
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _list_sets(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT s.id, s.subject, s.title, s.status, s.created_at, "
        "       (SELECT COUNT(*) FROM live_questions q WHERE q.question_set_id = s.id) AS n "
        "FROM question_sets s ORDER BY s.id"
    ).fetchall()
    if not rows:
        print("Heç bir sual dəsti yoxdur.")
        return 0
    print(f"{'ID':>4}  {'sual':>5}  {'status':<12} {'fənn':<16} başlıq")
    print("-" * 72)
    for row in rows:
        print(f"{row['id']:>4}  {row['n']:>5}  {row['status']:<12} {row['subject']:<16} {row['title']}")
    return 0


def _load_questions(conn: sqlite3.Connection, set_id: int) -> list[MCQQuestion]:
    rows = conn.execute(
        "SELECT question, options, correct_index, explanation "
        "FROM live_questions WHERE question_set_id = ? ORDER BY id",
        (set_id,),
    ).fetchall()
    questions = []
    for row in rows:
        questions.append(
            MCQQuestion(
                question=row["question"],
                options=json.loads(row["options"]),
                correct_index=row["correct_index"],
                explanation=row["explanation"],
            )
        )
    return questions


def _audit_set(conn: sqlite3.Connection, set_id: int, out: str | None) -> int:
    meta = conn.execute(
        "SELECT id, subject, title, status, material_kind, material_location "
        "FROM question_sets WHERE id = ?",
        (set_id,),
    ).fetchone()
    if meta is None:
        print(f"{set_id} nömrəli sual dəsti yoxdur. Mövcudları görmək üçün: --list", file=sys.stderr)
        return 1

    questions = _load_questions(conn, set_id)
    report = audit_questions(questions)

    header = "\n".join([
        "=" * 72,
        f"DƏST {meta['id']}: {meta['title']}",
        f"Fənn: {meta['subject']}   Status: {meta['status']}",
        f"Material: {meta['material_kind']} — {meta['material_location']}",
        "=" * 72,
        "",
        "Yoxlayarkən mənbə materialını yanınızda açıq saxlayın:",
        f"  {meta['material_location']}",
        "",
    ])
    text = header + format_review_sheet(questions, report)

    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Yazıldı: {out}  ({len(questions)} sual, {len(report.findings)} avtomatik tapıntı)")
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MasterAI — sual keyfiyyəti auditi")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite baza yolu (defolt: {DEFAULT_DB})")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="sual dəstlərini sadala")
    group.add_argument("--set", type=int, help="bu dəsti yoxla")
    parser.add_argument("--out", help="nəticəni fayla yaz")
    args = parser.parse_args(argv)

    conn = _connect(args.db)
    try:
        if args.list:
            return _list_sets(conn)
        return _audit_set(conn, args.set, args.out)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
