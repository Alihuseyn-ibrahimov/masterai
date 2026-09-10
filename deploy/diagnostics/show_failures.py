"""Uğursuz sual dəstlərinin səbəblərini göstərir.

`sqlite3` əmri serverdə quraşdırılmayıb (və onu quraşdırmaq üçün apt
işlətmək lazım gəlir) — Python-un öz `sqlite3` modulu isə onsuz da var.

    cd /opt/pr-agent/repo/masterai
    .venv/bin/python deploy/diagnostics/show_failures.py

Yalnız oxuyur.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

DEFAULT_DB = "question_sets.db"

# Səbəbləri qruplaşdırmaq üçün: fərqli mətnlər eyni kök səbəbdən ola
# bilər (məs. hər dəfə başqa URL, amma eyni «Sayt yüklənmədi»).
_PATTERNS = (
    ("sayt yüklənmədi",      r"sayt yüklənmədi|yüklənmədi"),
    ("mətn çıxarılmadı",     r"mətn çıxar|mətn tapılmadı|boş"),
    ("model xətası",         r"rate.?limit|429|llm|model|groq|anthropic"),
    ("vaxt bitdi",           r"timeout|vaxt"),
    ("URL problemi",         r"scheme|invalid url|url"),
)


def _bucket(error: str) -> str:
    lowered = (error or "").casefold()
    for name, pattern in _PATTERNS:
        if re.search(pattern, lowered):
            return name
    return "digər"


def main(argv: list[str]) -> int:
    db = argv[1] if len(argv) > 1 else DEFAULT_DB
    if not Path(db).exists():
        print(f"Baza tapılmadı: {db}")
        return 1

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, subject, material_kind, material_location, error "
        "FROM question_sets WHERE status = 'failed' ORDER BY id"
    ).fetchall()

    if not rows:
        print("Uğursuz dəst yoxdur.")
        return 0

    print("=" * 72)
    print(f"UĞURSUZ DƏSTLƏR: {len(rows)}")
    print("=" * 72)
    for row in rows:
        print(f"\n[{row['id']}] {row['title']}  ({row['subject']}, {row['material_kind']})")
        print(f"    mənbə: {row['material_location'][:100]}")
        print(f"    səbəb: {(row['error'] or '(səbəb yazılmayıb)')[:300]}")

    print()
    print("=" * 72)
    print("SƏBƏBLƏRİN QRUPLAŞDIRILMASI")
    print("=" * 72)
    buckets = Counter(_bucket(row["error"]) for row in rows)
    for name, count in buckets.most_common():
        share = count / len(rows) * 100
        print(f"  {name:<22} {count:>3}  ({share:.0f}%)")
    print()
    print("Bir qrup üstünlük təşkil edirsə, bir düzəliş uğursuzluğun")
    print("böyük hissəsini aradan qaldıra bilər.")

    # İlişib qalanlar da göstərilir — onlar `failed` deyil, amma ölüdür.
    stuck = conn.execute(
        "SELECT id, title, created_at FROM question_sets WHERE status = 'processing'"
    ).fetchall()
    if stuck:
        print()
        print("=" * 72)
        print(f"«HAZIRLANIR» VƏZİYYƏTİNDƏ İLİŞİB QALANLAR: {len(stuck)}")
        print("=" * 72)
        print("Bunlar xəta vermir, sadəcə heç vaxt bitmir — istifadəçi")
        print("üçün ölü dəstdir. Emal ortasında servis restart olanda yaranır.")
        for row in stuck:
            print(f"  [{row['id']}] {row['title']}  (yaradılıb: {row['created_at']})")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
