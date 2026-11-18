"""Colab notebook-unun qəbz müqayisəsi (`ml/receipts/compare.py`)."""

import json

import pytest

from ml.receipts import compare, sft, synth


def _label_outputs(parts, mutate=None):
    out = {}
    for rows in parts.values():
        for i, r in enumerate(rows):
            label = dict(r["label"])
            if mutate:
                label = mutate(i, label)
            out[r["text"]] = json.dumps(label, ensure_ascii=False)
    return out


def test_same_receipts_as_evals_kassa():
    pytest.importorskip("langchain_text_splitters")   # evals.kassa pipeline.rag-ı idxal edir
    from evals import kassa
    parts = compare.eval_parts()
    report = kassa.receipts_eval()
    assert report["n"] == {k: len(v) for k, v in parts.items()}
    for name in ("seen", "unseen"):
        mine = compare.compare({}, parts, subset=None)["full"]["rules"][name]
        assert mine["all_fields"] == report[f"rules_{name}"]["all_fields"]


def test_rules_baseline_matches_known_numbers():
    report = compare.compare({}, subset=None)
    assert report["n"]["full"] == {"seen": 240, "unseen": 120}
    assert report["full"]["rules"]["seen"]["all_fields"] == pytest.approx(0.925)
    assert report["full"]["rules"]["unseen"]["all_fields"] == pytest.approx(0.50)


def test_groq_subset_is_first_ten_per_family():
    report = compare.compare({})
    assert report["n"]["groq_subset"] == {"seen": 40, "unseen": 20}


def test_perfect_junk_and_pipeline_fallback():
    parts = compare.eval_parts()
    perfect = _label_outputs(parts)
    junk = {t: "bilmirəm" for t in perfect}
    report = compare.compare({"perfect": perfect, "junk": junk}, parts)["full"]
    assert report["perfect_raw"]["unseen"]["all_fields"] == 1.0
    assert report["junk_raw"]["seen"]["valid_json"] == 0.0
    # produksiya yolu: pozuq LLM cavabında qaydalara düşür
    assert report["junk_pipeline"]["seen"]["all_fields"] == report["rules"]["seen"]["all_fields"]
    assert report["junk_pipeline"]["unseen"]["sources"]["llm"] == 0


def test_grounding_rejects_invented_amount():
    parts = compare.eval_parts()
    lying = _label_outputs(parts, lambda i, lab: lab | {"amount": 99999.0})
    report = compare.compare({"lying": lying}, parts)["full"]
    assert report["lying_raw"]["seen"]["fields"]["amount"] == 0.0
    assert report["lying_pipeline"]["seen"]["sources"]["llm"] == 0   # uydurma məbləğ rədd olunur


def test_no_eval_text_in_training_data():
    parts = compare.eval_parts()
    train = sft.split(synth.generate(400, 7), 7)["train"]
    assert compare.overlap_with_train(parts, {r["text"] for r in train}) == 0


def test_prompts_are_production_prompts_and_unique():
    from pipeline.receipt_reader import SYSTEM_PROMPT, user_prompt
    parts = compare.eval_parts()
    rows = compare.prompts(parts)
    assert len(rows) == len({r["text"] for r in rows})
    assert rows[0]["messages"] == [{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": user_prompt(rows[0]["text"])}]


def test_format_and_save(tmp_path):
    parts = compare.eval_parts()
    report = compare.compare({"qlora": _label_outputs(parts)}, parts)
    text = compare.format_report(report)
    assert "Groq + yoxlama + qaydalar" in text and "88%" in text and "messenger (görülməyən)" in text
    compare.save(report, str(tmp_path / "report.md"))
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["n"]["full"]["seen"] == 240
