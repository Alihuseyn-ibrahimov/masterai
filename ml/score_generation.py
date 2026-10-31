"""Sual generasiyası modelinin çıxışını qiymətləndirir (gün 16-17).

Eyni val dəstində baza model, fine-tune olunmuş model və produksiya modeli
müqayisə olunur. Hər çıxış üçün:

- **parse**: produksiya parseri ilə JSON oxunurmu (oxunmursa sual itir);
- **count**: istənilən sayda sual gəlibmi;
- **rules_pass**: qaydalı filtri keçən sualların payı (`evals.run.rules_flag`);
- **giveaway**: düzgün cavabın uzunluqla özünü verdiyi sualların payı (aşağı = yaxşı);
- **grounded**: düzgün cavabın sözlərinin ən azı yarısı materialda varmı (uydurmaya qarşı).

    python -m ml.score_generation --val sft/val.jsonl --pred base.jsonl --pred qlora.jsonl

Proqnoz faylı: hər sətir `{"output": "<modelin mətni>"}`, val ilə eyni sırada.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from evals.run import rules_flag
from pipeline.generation import parse_questions
from pipeline.quality import answer_stands_out
from pipeline.rag import tokenize

_MATERIAL = re.compile(r"Material:\n---\n(.*?)\n---", re.DOTALL)


def material_of(example: dict) -> str:
    match = _MATERIAL.search(example["messages"][1]["content"])
    return match.group(1) if match else ""


def expected_count(example: dict) -> int:
    return len(json.loads(example["messages"][2]["content"])["questions"])


def grounded(answer: str, material_tokens: set[str]) -> bool:
    tokens = set(tokenize(answer))
    return bool(tokens) and len(tokens & material_tokens) / len(tokens) >= 0.5


def score(val: list[dict], outputs: list[str]) -> dict:
    if len(val) != len(outputs):
        raise ValueError(f"val {len(val)} nümunə, proqnoz {len(outputs)} - sıra uyğun gəlmir")
    parsed = count_ok = 0
    questions = rules_ok = giveaway = ground_ok = 0
    for example, text in zip(val, outputs):
        try:
            items = parse_questions(text)
        except Exception:  # noqa: BLE001 - parser hər cür pozuq mətndə xəta atır
            continue
        parsed += 1
        count_ok += len(items) == expected_count(example)
        material = set(tokenize(material_of(example)))
        for q in items:
            questions += 1
            rules_ok += not rules_flag(q)
            giveaway += answer_stands_out(q)
            ground_ok += grounded(q.options[q.correct_index], material)
    rate = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {"examples": len(val), "parse_rate": rate(parsed, len(val)), "count_rate": rate(count_ok, len(val)),
            "questions": questions, "rules_pass": rate(rules_ok, questions),
            "giveaway_rate": rate(giveaway, questions), "grounded_rate": rate(ground_ok, questions)}


def read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generasiya çıxışının qiymətləndirilməsi")
    parser.add_argument("--val", required=True)
    parser.add_argument("--pred", action="append", required=True, help="proqnoz faylı (bir neçə dəfə)")
    args = parser.parse_args(argv)
    val = read_jsonl(args.val)
    columns = ["parse_rate", "count_rate", "rules_pass", "giveaway_rate", "grounded_rate"]
    print("model".ljust(28) + "".join(c.ljust(15) for c in columns))
    for path in args.pred:
        result = score(val, [row["output"] for row in read_jsonl(path)])
        print(path[-28:].ljust(28) + "".join(str(result[c]).ljust(15) for c in columns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
