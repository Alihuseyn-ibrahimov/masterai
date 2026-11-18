"""Səhv Detektivi: golden dəstdə PRODUKSİYA yolunun ölçülməsi (`pipeline.sehv_detektivi.diagnose`).

    python -m evals.sehv                                   # yalnız sympy (model yoxdur, CI)
    python -m evals.sehv --url http://localhost:8000 --model sehv --api-key KEY   # vLLM
    python -m evals.sehv --adapter /content/drive/MyDrive/sehv-detektivi/sehv-lora-v3
    python -m evals.sehv ... --threshold 0.6 --out sehv.md

Səhv Detektivi reposundakı `scripts/evaluate.py` modelin ÖZÜNÜ ölçür. Bu skript isə masterai-də
tələbənin gördüyü nəticəni ölçür: eyni prompt, eyni parse, sympy vetosu, kalibrasiya eşiyi və
«yoxlanmadı» halı. Üç rejim yan-yana:

* `sympy` - model yoxdur (server adapter olmadan belə işləyir)
* `model` - yalnız model (`SEHV_SYMPY_VETO=false`)
* `model+sympy` - produksiya defoltu

Metrikalar (golden etiketinə qarşı):
* addım - `wrong_step` tam düz (düzgün həll üçün None düz)
* var/yox - «səhv var / yoxdur» qərarı düz. `unknown` SƏHV sayılır: cavab verilməyib
* yalançı həyəcan - düzgün həllərin neçə faizinə «səhv var» deyilib (hədəf < 0.20)
* buraxılan səhv - səhvli həllərin neçə faizinə «düzgündür» deyilib
* yoxlanmadı - `status=unknown` payı
* növ macro-F1 - səhv növü («DÜZGÜN» və «YOXLANMADI» də sinifdir)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from pipeline.sehv_detektivi import Calibration, LocalBackend, VllmBackend, diagnose

GOLDEN = Path(__file__).parent / "datasets" / "sehv_golden.jsonl"


def load_golden(path: Path = GOLDEN) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _macro_f1(gold: list[str], pred: list[str]) -> float:
    scores = []
    for label in sorted(set(gold)):
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


def score(golden: list[dict], results: list[dict]) -> dict:
    """Hər qrup (hamısı, riyaziyyat, mentiq) üçün metrikalar."""
    groups = defaultdict(list)
    for gold, res in zip(golden, results):
        groups["hamısı"].append((gold, res))
        groups[gold["domain"]].append((gold, res))
    report = {}
    for name, pairs in groups.items():
        correct = [(g, r) for g, r in pairs if g["wrong_step"] is None]
        faulty = [(g, r) for g, r in pairs if g["wrong_step"] is not None]
        known = [(g, r) for g, r in pairs if r["status"] != "unknown"]
        report[name] = {
            "n": len(pairs),
            "step_acc": sum(r["status"] != "unknown" and r["wrong_step"] == g["wrong_step"]
                            for g, r in pairs) / len(pairs),
            "detect_acc": sum((r["status"] == "error_found") == (g["wrong_step"] is not None)
                              for g, r in known) / len(pairs),
            "false_alarm": (sum(r["status"] == "error_found" for _, r in correct) / len(correct)
                            if correct else None),
            "missed": sum(r["status"] == "correct" for _, r in faulty) / len(faulty) if faulty else None,
            "unknown": sum(r["status"] == "unknown" for _, r in pairs) / len(pairs),
            "type_macro_f1": _macro_f1(
                [g["error_type"] or "DÜZGÜN" for g, _ in pairs],
                [("YOXLANMADI" if r["status"] == "unknown" else (r["error_type"] or "DÜZGÜN")) for _, r in pairs]),
        }
    return report


def run(golden: list[dict], backend=None, calibration: Calibration | None = None, progress=None) -> list[dict]:
    results = []
    for i, rec in enumerate(golden, 1):
        results.append(diagnose(rec["domain"], rec["problem"], rec["steps"], backend, calibration))
        if progress:
            progress(i, len(golden))
    return results


def _pct(value) -> str:
    return "-" if value is None else f"{value:.0%}"


def format_report(reports: dict[str, dict]) -> str:
    lines = ["| Rejim | Qrup | n | Addım | Var/yox | Yalançı həyəcan | Buraxılan | Yoxlanmadı | Növ F1 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for mode, report in reports.items():
        for group, r in report.items():
            lines.append(f"| {mode} | {group} | {r['n']} | {_pct(r['step_acc'])} | {_pct(r['detect_acc'])} | "
                         f"{_pct(r['false_alarm'])} | {_pct(r['missed'])} | {_pct(r['unknown'])} | "
                         f"{r['type_macro_f1']:.2f} |")
    return "\n".join(lines)


def evaluate(golden: list[dict], backend=None, threshold: float | None = None, progress=None) -> dict[str, dict]:
    """Model varsa model-only və model+sympy (eşik verilsə ikisinə də tətbiq olunur), həmişə sympy."""
    reports = {"sympy": score(golden, run(golden))}
    if backend is not None:
        reports["model"] = score(golden, run(golden, backend, Calibration(threshold, sympy_veto=False), progress))
        reports["model+sympy"] = score(golden, run(golden, backend, Calibration(threshold, sympy_veto=True), progress))
    return reports


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="vLLM ünvanı (OpenAI-uyğun)")
    parser.add_argument("--model", default="sehv", help="--lora-modules adı")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--adapter", help="lokal backend: adapter qovluğu və ya HF repo")
    parser.add_argument("--threshold", type=float, help="SEHV_NULL_THRESHOLD (yalnız lokal backend)")
    parser.add_argument("--golden", type=Path, default=GOLDEN)
    parser.add_argument("--out", type=Path, help="markdown hesabatı bu fayla da yaz")
    args = parser.parse_args(argv)

    backend = None
    if args.url:
        backend = VllmBackend(args.url, args.model, api_key=args.api_key, timeout=120)
    elif args.adapter:
        backend = LocalBackend(args.adapter)
    golden = load_golden(args.golden)

    def progress(i, n):
        print(f"\r{i}/{n}", end="" if i < n else "\n", file=sys.stderr, flush=True)

    text = format_report(evaluate(golden, backend, args.threshold, progress))
    print(text)
    if args.out:
        args.out.write_text(f"# Səhv Detektivi eval\n\n{text}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
