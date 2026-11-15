"""python -m ml.churn --students 400 --seed 7 --out /tmp/kassa

Sintetik kurs datasını (masterai cədvəlləri formasında) və churn datasetini yazır,
sonda qısa xülasə çap edir: kəsik sayı, aylıq itki faizi, borclu payı.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from datetime import datetime, timezone

from . import dataset, synth
from .schema import write_tables


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kurs Kassası: sintetik data + churn dataseti")
    ap.add_argument("--students", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True, help="CSV-lərin yazılacağı qovluq")
    args = ap.parse_args(argv)

    tables = synth.generate(args.students, args.seed)
    write_tables(tables, args.out)
    rows = dataset.build(
        tables,
        datetime(2025, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    dataset.write_csv(rows, os.path.join(args.out, "churn_dataset.csv"))

    print(f"{len(tables.chat_members)} şagird, {len(rows)} sətir -> {args.out}")
    by_month = Counter(r["snapshot"] for r in rows)
    churn = Counter(r["snapshot"] for r in rows if r["churned"])
    for month in sorted(by_month):
        print(f"  {month}: {by_month[month]:4d} şagird, itki {churn[month] / by_month[month]:.1%}")
    debtors = sum(1 for r in rows if r["prev_month_unpaid"] and not r["churned"])
    print(f"Ümumi itki {sum(churn.values()) / len(rows):.1%}, borclu qalıb davam edən {debtors / len(rows):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
