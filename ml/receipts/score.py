"""Qəbz oxuyucusunun qiymətləndirilməsi: sahə üzrə dəqiqlik + bütün sahələr düz.

    python -m ml.receipts.score --gold test_unseen.jsonl --pred base.jsonl --pred qlora.jsonl
    python -m ml.receipts.score --gold test_unseen.jsonl --rules      # qaydalı baza

`--pred` faylı hər sətirdə `{"output": "<model cavabı>"}` saxlayır (gold ilə eyni sıra).
Ad müqayisəsi `normalize` ilədir (diakritik və böyük/kiçik hərf fərqi səhv sayılmır).
"""

from __future__ import annotations

import argparse
import json

from pipeline.receipt_reader import Receipt, ReceiptError, normalize, parse_reply, rule_based

from .synth import FIELDS


def _same(field: str, gold, pred) -> bool:
    if gold is None or pred is None:
        return gold is None and pred is None
    if field == "amount":
        return abs(float(gold) - float(pred)) < 0.005
    if field in ("payer", "student"):
        return normalize(str(gold)) == normalize(str(pred))
    return str(gold) == str(pred)


def score(golds: list[dict], preds: list[Receipt | None]) -> dict:
    n = len(golds)
    correct = {f: 0 for f in FIELDS}
    all_ok = parsed = 0
    for gold, pred in zip(golds, preds):
        if pred is None:
            continue
        parsed += 1
        values = pred.model_dump()
        ok = [_same(f, gold[f], values[f]) for f in FIELDS]
        for f, good in zip(FIELDS, ok):
            correct[f] += good
        all_ok += all(ok)
    return {
        "n": n,
        "valid_json": round(parsed / n, 4) if n else 0.0,
        "all_fields": round(all_ok / n, 4) if n else 0.0,
        "fields": {f: round(c / n, 4) if n else 0.0 for f, c in correct.items()},
    }


def parse_outputs(outputs: list[str]) -> list[Receipt | None]:
    out = []
    for text in outputs:
        try:
            out.append(parse_reply(text))
        except ReceiptError:
            out.append(None)
    return out


def read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def gold_rows(rows: list[dict]) -> tuple[list[str], list[dict]]:
    """SFT sətrindən (chat formatı) mətn və etiket."""
    texts, golds = [], []
    for r in rows:
        texts.append(r["text"])
        golds.append(json.loads(r["messages"][2]["content"]))
    return texts, golds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qəbz oxuyucusunun qiymətləndirilməsi")
    parser.add_argument("--gold", required=True)
    parser.add_argument("--pred", action="append", default=[])
    parser.add_argument("--rules", action="store_true")
    args = parser.parse_args(argv)
    texts, golds = gold_rows(read_jsonl(args.gold))
    runs = {}
    if args.rules:
        runs["rules"] = [rule_based(t) for t in texts]
    for path in args.pred:
        runs[path] = parse_outputs([r["output"] for r in read_jsonl(path)])
    for name, preds in runs.items():
        s = score(golds, preds)
        fields = " ".join(f"{k}={v:.2f}" for k, v in s["fields"].items())
        print(f"{name}: hamısı düz {s['all_fields']:.2%}, JSON {s['valid_json']:.0%} | {fields}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
