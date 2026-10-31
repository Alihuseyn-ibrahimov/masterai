"""Çətinlik modeli üçün dataset: CSV oxuma/yazma və sintetik demo dəsti.

CSV sütunları: `FEATURES` + `accuracy` (düzgün cavab payı, 0-1) + `answers`
(neçə cavabdan hesablanıb) + `ai_level`. Real CSV serverdə
`deploy/export_difficulty_data.py` ilə çıxarılır; tələbə məlumatı yoxdur.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass

from pipeline.difficulty_features import FEATURES


@dataclass
class Row:
    features: list[float]
    accuracy: float
    answers: int
    ai_level: str = ""


def read_csv(path: str) -> list[Row]:
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [name for name in FEATURES + ["accuracy", "answers"] if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV-də sütun yoxdur: {', '.join(missing)}")
        return [Row([float(r[name]) for name in FEATURES], float(r["accuracy"]), int(r["answers"]),
                    r.get("ai_level", "")) for r in reader]


def write_csv(path: str, rows: list[Row], extra: list[dict] | None = None) -> None:
    extra_keys = sorted({k for e in extra or [] for k in e})
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(FEATURES + ["accuracy", "answers", "ai_level"] + extra_keys)
        for i, row in enumerate(rows):
            more = [(extra[i] if extra else {}).get(k, "") for k in extra_keys]
            writer.writerow([round(v, 6) for v in row.features] + [round(row.accuracy, 4), row.answers,
                                                                   row.ai_level] + more)


def synthetic(n: int, seed: int = 0) -> list[Row]:
    """Demo dəsti: real cavab yığılana qədər öyrətmə zəncirini sınamaq üçün.

    «Gizli qayda» (model bunu tapmalıdır): uzun sual, rəqəmli variant və inkar
    çətinləşdirir; cavabın uzunluqla özünü verməsi və sualla üst-üstə düşməsi
    asanlaşdırır; AI-nın səviyyəsi qismən doğrudur. Nəticə binomial səs-küylüdür,
    real sinifdə olduğu kimi. Bu dəstlə öyrədilmiş model PRODUKSİYAYA QOYULMUR
    (`synthetic: true` bayrağı ilə yazılır, server onu göstərmir).
    """
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        stem_chars = rng.randint(25, 220)
        option_chars = rng.randint(3, 60)
        correct_ratio = max(0.4, rng.gauss(1.05, 0.3))
        has_number = float(rng.random() < 0.35)
        numeric = rng.choice([0.0, 0.0, 0.0, 0.6, 1.0])
        negation = float(rng.random() < 0.15)
        overlap_c = min(1.0, max(0.0, rng.gauss(0.15, 0.15)))
        overlap_d = min(1.0, max(0.0, rng.gauss(0.12, 0.1)))
        level = rng.choice(["asan", "orta", "orta", "çətin", ""])
        logit = (1.2 - 0.008 * stem_chars - 0.6 * numeric - 0.9 * negation
                 + 1.4 * max(0.0, correct_ratio - 1.2) + 1.5 * overlap_c - 1.0 * overlap_d
                 + {"asan": 0.5, "orta": 0.0, "çətin": -0.5, "": 0.0}[level] + rng.gauss(0, 0.3))
        p = 1 / (1 + math.exp(-logit))
        answers = rng.randint(5, 40)
        accuracy = sum(rng.random() < p for _ in range(answers)) / answers
        features = [
            math.log1p(stem_chars), stem_chars / 70, math.log1p(option_chars),
            max(0.0, rng.gauss(0.3, 0.15)), correct_ratio, has_number, numeric, negation,
            overlap_c, overlap_d, math.log1p(rng.randint(20, 200)),
            float(level == "asan"), float(level == "orta"), float(level == "çətin"),
        ]
        rows.append(Row(features, accuracy, answers, level))
    return rows
