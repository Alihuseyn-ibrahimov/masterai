"""Qəbz oxuyucusu: QLoRA adapteri `evals.kassa`-nın EYNİ dəstində qaydalar və Groq ilə.

Colab notebook-u (`ml/qlora_receipts.ipynb`) modelin cavablarını yaradır, bu modul isə
onları `evals.kassa.receipts_eval` ilə eyni qəbzlərdə qiymətləndirir. `evals` paketini
idxal ETMİR: o, `pipeline.rag` vasitəsilə langchain tələb edir, Colab-da isə yalnız
pydantic var. Dəstin eyniliyini `tests/test_receipt_compare.py` yoxlayır.

İki ölçü:
- `raw`: modelin JSON-u olduğu kimi (`parse_reply`), yoxlama yoxdur;
- `pipeline`: produksiya yolu `read_receipt` (LLM → `grounded` → alınmasa qaydalar).
  Groq rəqəmi MƏHZ bu yolla ölçülüb, ona görə müqayisə bu sütundadır.

Groq serverdə hər növdən yalnız ilk 10 qəbzdə ölçülüb (`--receipts 10`: görülən 40,
görülməyən 20), ona görə adapter həm bütün dəstdə, həm də həmin 60 qəbzdə verilir.
"""

from __future__ import annotations

import json

from pipeline.receipt_reader import SYSTEM_PROMPT, read_receipt, rule_based, user_prompt

from . import synth
from .score import parse_outputs, score

EVAL_PER_FAMILY = 60      # evals.kassa.receipts_eval defoltu
EVAL_SEED = 11
GROQ_PER_FAMILY = 10      # serverdəki `python -m evals.kassa --live --receipts 10`

# Əvvəlki ölçmələr (bütün sahələr düz). Qaydalar burada yenidən hesablanır, bu sətir
# yalnız hesabatda yanında göstərilir; Groq-u Colab-da təkrarlamırıq (açar lazımdır).
REFERENCE = {
    "groq_pipeline": {"seen": 0.88, "unseen": 1.00, "n": {"seen": 40, "unseen": 20},
                      "note": "server, evals.kassa --live --receipts 10, openai/gpt-oss-120b"},
}


def eval_parts(per_family: int = EVAL_PER_FAMILY, seed: int = EVAL_SEED) -> dict[str, list[dict]]:
    samples = synth.generate(per_family, seed)
    return {"seen": [s for s in samples if s["family"] not in synth.HELD_OUT],
            "unseen": [s for s in samples if s["family"] in synth.HELD_OUT]}


def first_per_family(rows: list[dict], limit: int) -> list[dict]:
    taken: dict[str, int] = {}
    out = []
    for r in rows:
        if taken.get(r["family"], 0) < limit:
            taken[r["family"]] = taken.get(r["family"], 0) + 1
            out.append(r)
    return out


def prompts(parts: dict[str, list[dict]]) -> list[dict]:
    """Modelə veriləcək chat mesajları (produksiya promptu), təkrarsız."""
    seen, out = set(), []
    for rows in parts.values():
        for r in rows:
            if r["text"] not in seen:
                seen.add(r["text"])
                out.append({"text": r["text"], "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(r["text"])}]})
    return out


def overlap_with_train(parts: dict[str, list[dict]], train_texts: set[str]) -> int:
    """Eval qəbzlərindən neçəsi öyrətmə datasında hərfi-hərfinə var (sızma yoxlaması)."""
    return sum(r["text"] in train_texts for rows in parts.values() for r in rows)


def _by_family(rows: list[dict], preds: list) -> dict[str, float]:
    out = {}
    for fam in dict.fromkeys(r["family"] for r in rows):
        idx = [i for i, r in enumerate(rows) if r["family"] == fam]
        out[fam] = score([rows[i]["label"] for i in idx], [preds[i] for i in idx])["all_fields"]
    return out


def evaluate(rows: list[dict], preds: list) -> dict:
    return score([r["label"] for r in rows], preds) | {"by_family": _by_family(rows, preds)}


def compare(outputs: dict[str, dict[str, str]], parts: dict[str, list[dict]] | None = None,
            subset: int | None = GROQ_PER_FAMILY) -> dict:
    """`outputs`: {"base": {mətn: cavab}, "qlora": {mətn: cavab}}.

    Qaytarır: {"full": {...}, "groq_subset": {...}}, hər birində
    {"rules": {"seen": .., "unseen": ..}, "<ad>_raw": .., "<ad>_pipeline": ..}.
    """
    parts = parts or eval_parts()
    views = {"full": parts}
    if subset:
        views["groq_subset"] = {k: first_per_family(v, subset) for k, v in parts.items()}
    report: dict = {"n": {view: {k: len(v) for k, v in p.items()} for view, p in views.items()},
                    "reference": REFERENCE}
    for view, p in views.items():
        block: dict = {"rules": {k: evaluate(rows, [rule_based(r["text"]) for r in rows])
                                 for k, rows in p.items()}}
        for name, by_text in outputs.items():
            raw, pipe, sources = {}, {}, {}
            for split, rows in p.items():
                replies = [by_text[r["text"]] for r in rows]
                raw[split] = evaluate(rows, parse_outputs(replies))
                answers = dict(zip((user_prompt(r["text"]) for r in rows), replies))
                results, src = [], {"llm": 0, "rules": 0, "none": 0}
                for r in rows:
                    result, source, _ = read_receipt(r["text"], lambda _s, u: answers[u])
                    results.append(result)
                    src[source] += 1
                pipe[split] = evaluate(rows, results) | {"sources": src}
            block[f"{name}_raw"], block[f"{name}_pipeline"] = raw, pipe
        report[view] = block
    return report


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.0%}"


def format_report(report: dict) -> str:
    names = [k[:-4] for k in report["full"] if k.endswith("_raw")]
    groq = report["reference"]["groq_pipeline"]
    lines = ["# Qəbz oxuyucusu: QLoRA vs qaydalar vs Groq", "",
             "Bütün sahələr düz (məbləğ, tarix, ödəyən, kart, ay, şagird). Data sintetikdir.", ""]
    for view, title in (("full", "Bütün eval dəsti"), ("groq_subset", "Groq ilə eyni 60 qəbz")):
        if view not in report:
            continue
        n, block = report["n"][view], report[view]
        lines += [f"## {title} (görülən {n['seen']}, görülməyən {n['unseen']})", "",
                  "| Yol | Görülən | Görülməyən | JSON oxundu (görülməyən) |", "|---|---|---|---|",
                  f"| Qaydalar | {_pct(block['rules']['seen']['all_fields'])} | "
                  f"{_pct(block['rules']['unseen']['all_fields'])} | - |"]
        for name in names:
            for kind, label in (("raw", "xam JSON"), ("pipeline", "+ yoxlama + qaydalar")):
                b = block[f"{name}_{kind}"]
                lines.append(f"| {name} {label} | {_pct(b['seen']['all_fields'])} | "
                             f"{_pct(b['unseen']['all_fields'])} | "
                             f"{_pct(b['unseen']['valid_json']) if kind == 'raw' else '-'} |")
        if view == "groq_subset":
            lines.append(f"| Groq + yoxlama + qaydalar (əvvəlki ölçmə) | {_pct(groq['seen'])} | "
                         f"{_pct(groq['unseen'])} | - |")
        lines.append("")
    full = report["full"]
    lines += ["## Növ üzrə (bütün dəst, «+ yoxlama + qaydalar»)", "",
              "| Növ | Qaydalar | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for split in ("seen", "unseen"):
        for fam, value in full["rules"][split]["by_family"].items():
            cells = [_pct(full[f"{n}_pipeline"][split]["by_family"][fam]) for n in names]
            mark = " (görülməyən)" if split == "unseen" else ""
            lines.append(f"| {fam}{mark} | {_pct(value)} | " + " | ".join(cells) + " |")
    lines += ["", "## Sahə üzrə, görülməyən növlər (xam JSON)", "",
              "| Sahə | Qaydalar | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for field in synth.FIELDS:
        cells = [_pct(full[f"{n}_raw"]["unseen"]["fields"][field]) for n in names]
        lines.append(f"| {field} | {_pct(full['rules']['unseen']['fields'][field])} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def save(report: dict, path_md: str) -> None:
    with open(path_md, "w", encoding="utf-8") as fh:
        fh.write(format_report(report) + "\n")
    with open(path_md.rsplit(".", 1)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
