"""QLoRA üçün chat formatında dataset (Colab: `ml/qlora_receipts.ipynb`).

    python -m ml.receipts.sft --per-family 400 --seed 7 --out /tmp/receipts

Yazır: `train.jsonl`, `val.jsonl`, `test_seen.jsonl` (öyrətmədə olan ailələr),
`test_unseen.jsonl` (`synth.HELD_OUT` ailələri: model bu formatları HEÇ görməyib).
Sistem və istifadəçi mesajı produksiya ilə bayt-bayt eynidir
(`pipeline.receipt_reader.SYSTEM_PROMPT`, `user_prompt`), test bunu yoxlayır.
"""

from __future__ import annotations

import argparse
import json
import os
import random

from pipeline.receipt_reader import SYSTEM_PROMPT, rule_based, user_prompt

from . import synth
from .score import score


def to_chat(sample: dict) -> dict:
    return {
        "family": sample["family"],
        "text": sample["text"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(sample["text"])},
            {"role": "assistant", "content": json.dumps(sample["label"], ensure_ascii=False)},
        ],
    }


def split(samples: list[dict], seed: int = 7) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    seen = [s for s in samples if s["family"] not in synth.HELD_OUT]
    rng.shuffle(seen)
    n_test, n_val = len(seen) // 10, len(seen) // 10
    return {
        "test_seen": seen[:n_test],
        "val": seen[n_test:n_test + n_val],
        "train": seen[n_test + n_val:],
        "test_unseen": [s for s in samples if s["family"] in synth.HELD_OUT],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qəbz oxuyucusu üçün SFT dataseti")
    parser.add_argument("--per-family", type=int, default=400)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    parts = split(synth.generate(args.per_family, args.seed), args.seed)
    os.makedirs(args.out, exist_ok=True)
    for name, rows in parts.items():
        with open(os.path.join(args.out, f"{name}.jsonl"), "w", encoding="utf-8") as fh:
            for s in rows:
                fh.write(json.dumps(to_chat(s), ensure_ascii=False) + "\n")
    print(" ".join(f"{k}={len(v)}" for k, v in parts.items()))
    for name in ("test_seen", "test_unseen"):
        rows = parts[name]
        s = score([r["label"] for r in rows], [rule_based(r["text"]) for r in rows])
        print(f"Qaydalı baza, {name}: hamısı düz {s['all_fields']:.2%} | "
              + " ".join(f"{k}={v:.2f}" for k, v in s["fields"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
