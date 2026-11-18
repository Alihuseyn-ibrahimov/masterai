"""Kurs Kassası, addım 5: qəbz oxuyucusu (sintetik data, qaydalar, uydurmaya qarşı yoxlama,
SFT dataseti, notebook). Endpoint testləri `tests/server/test_kassa.py`-dədir."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from ml.receipts import sft, synth
from ml.receipts.score import _same, main as score_main, score
from pipeline.receipt_reader import (
    SYSTEM_PROMPT, Receipt, ReceiptError, grounded, normalize, parse_reply, read_receipt,
    rule_based, user_prompt,
)

ROOT = Path(__file__).resolve().parents[1]


def test_synth_is_deterministic_and_labels_are_in_the_text():
    rows = synth.generate(60, seed=5)
    assert rows == synth.generate(60, seed=5)
    assert {r["family"] for r in rows} == set(synth.FAMILIES)
    for r in rows:
        # Düzgün etiket öz yoxlamamızdan keçməlidir, yoxsa oxuyucu düz cavabı atar.
        checked, dropped = grounded(Receipt(**r["label"]), r["text"])
        assert checked is not None and dropped == [], r


def test_genitive_and_capitalize():
    assert synth.genitive("Aysel") == "Ayselin" and synth.genitive("Lalə") == "Lalənin"
    assert synth.genitive("Murad") == "Muradın" and synth.genitive("Orxan") == "Orxanın"
    assert synth.genitive("Könül") == "Könülün" and synth.genitive("Zaur") == "Zaurun"
    assert synth.az_capitalize("iyul") == "İyul"
    assert synth.ascii_upper("Məmmədova") == "MAMMADOVA"


@pytest.mark.parametrize("text, expected", [
    ("Mədaxil: 120.00 AZN\nKart: *4417\nGöndərən: RAUF ALIYEV\nTəyinat: Aysel noyabr\n"
     "Tarix: 03.11.2026 14:20\nBalans: 1530.20 AZN",
     {"amount": 120.0, "date": "2026-11-03", "payer": "RAUF ALIYEV", "card_last4": "4417",
      "month": 11, "student": "Aysel"}),
    ("Ödəniş qəbzi\nMəbləğ: 90,50 AZN\nKomissiya: 0.91 AZN\nTarix: 2026-10-01\n"
     "Göndərən: R*** Q***\nTəyinat: Murad, oktyabr",
     {"amount": 90.5, "date": "2026-10-01", "payer": None, "card_last4": None, "month": 10,
      "student": "Murad"}),
    ("Salam müəllim, Lalənin dekabr pulunu köçürdüm, 80 manat.",
     {"amount": 80.0, "date": None, "payer": None, "card_last4": None, "month": 12,
      "student": "Lalə"}),
])
def test_rules_skip_balance_and_commission(text, expected):
    assert rule_based(text).model_dump() == expected


def test_rules_return_none_without_amount():
    assert rule_based("Salam, sabah ödəyəcəm") is None


def test_parse_reply_accepts_fenced_json_and_rejects_garbage():
    r = parse_reply('Cavab:\n```json\n{"amount": 120, "student": " Aysel ", "month": 11}\n```')
    assert r.amount == 120 and r.student == "Aysel" and r.month == 11
    for bad in ("JSON yoxdur", '{"amount": -5}', '{"amount": 10, "date": "2026-13-01"}',
                '{"amount": 10, "card_last4": "44"}', '{"amount": 10, "month": 13}'):
        with pytest.raises(ReceiptError):
            parse_reply(bad)


def test_grounded_rejects_invented_amount_and_drops_invented_fields():
    text = "Kartınıza *4417 120.00 AZN daxil oldu. 03.11.2026. Qalıq: 900.00 AZN. Qeyd: Aysel"
    assert grounded(Receipt(amount=900.5), text) == (None, ["amount"])
    checked, dropped = grounded(Receipt(amount=120, date="2026-11-04", card_last4="1111",
                                        student="Nigar", payer="Rauf", month=12), text)
    assert checked.amount == 120 and dropped == ["date", "card_last4", "payer", "student", "month"]
    assert checked.model_dump() == {"amount": 120.0, "date": None, "payer": None,
                                    "card_last4": None, "month": None, "student": None}
    ok, dropped = grounded(Receipt(amount=120, date="2026-11-03", card_last4="4417",
                                   student="Aysel"), text)
    assert dropped == [] and ok.student == "Aysel"


def test_read_receipt_falls_back_to_rules():
    text = "Salam müəllim, Ayselin noyabr pulunu köçürdüm, 120 AZN."

    def broken(system, user):
        raise RuntimeError("vLLM düşüb")

    assert read_receipt(text, broken)[1] == "rules"
    assert read_receipt(text, lambda s, u: "bilmirəm")[1] == "rules"
    assert read_receipt(text, lambda s, u: '{"amount": 999}')[1] == "rules"   # uydurma məbləğ
    seen = []

    def llm(system, user):
        seen.append((system, user))
        return '{"amount": 120, "student": "Aysel", "month": 11, "card_last4": "0000"}'

    result, source, dropped = read_receipt(text, llm)
    assert source == "llm" and result.student == "Aysel" and dropped == ["card_last4"]
    assert seen == [(SYSTEM_PROMPT, user_prompt(text))]
    assert read_receipt("salam", None) == (None, "none", [])


def test_production_complete_is_private_by_default(monkeypatch):
    from pipeline import receipt_reader

    for key in ("VLLM_BASE_URL", "VLLM_RECEIPT_MODEL", "RECEIPT_ALLOW_EXTERNAL_LLM"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert receipt_reader.production_complete() is None       # Groq açarı var, amma qəbz ora getmir
    monkeypatch.setenv("VLLM_BASE_URL", "http://gpu:8000")
    monkeypatch.setenv("VLLM_RECEIPT_MODEL", "receipts")
    assert callable(receipt_reader.production_complete())


def test_score_normalizes_names_and_counts_invalid_json():
    assert _same("payer", "Rəşad Əliyev", "RESAD ELIYEV")
    assert not _same("amount", 120.0, 120.5) and _same("date", None, None)
    gold = [{"amount": 120.0, "date": None, "payer": None, "card_last4": None, "month": 11,
             "student": "Aysel"}] * 2
    out = score(gold, [Receipt(**gold[0]), None])
    assert out["valid_json"] == 0.5 and out["all_fields"] == 0.5 and out["fields"]["amount"] == 0.5


def test_sft_split_holds_out_unseen_families_and_matches_production_prompt(tmp_path, capsys):
    assert sft.main(["--per-family", "30", "--out", str(tmp_path)]) == 0
    parts = {p.stem: [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
             for p in tmp_path.glob("*.jsonl")}
    assert set(parts) == {"train", "val", "test_seen", "test_unseen"}
    assert {r["family"] for r in parts["test_unseen"]} == set(synth.HELD_OUT)
    for name in ("train", "val", "test_seen"):
        assert not {r["family"] for r in parts[name]} & set(synth.HELD_OUT)
    row = parts["train"][0]
    assert row["messages"][0]["content"] == SYSTEM_PROMPT
    assert row["messages"][1]["content"] == user_prompt(row["text"])
    assert Receipt(**json.loads(row["messages"][2]["content"]))
    assert "Qaydalı baza, test_unseen" in capsys.readouterr().out

    gold = tmp_path / "test_seen.jsonl"
    pred = tmp_path / "pred.jsonl"
    pred.write_text("\n".join(json.dumps({"output": r["messages"][2]["content"]})
                              for r in parts["test_seen"]), encoding="utf-8")
    assert score_main(["--gold", str(gold), "--pred", str(pred), "--rules"]) == 0
    assert f"{pred}: hamısı düz 100.00%" in capsys.readouterr().out


def test_rules_are_brittle_on_unseen_format():
    """Baza ölçüsü: qaydalar görmədikləri sərbəst formatda (`messenger`) şagirdi tapmır.
    QLoRA modelinin üstünlüyü məhz bu ailədə ölçülür."""
    rows = [r for r in synth.generate(40, seed=9) if r["family"] == "messenger"]
    found = [rule_based(r["text"]) for r in rows]
    assert all(f is not None and f.amount == r["label"]["amount"] for f, r in zip(found, rows))
    assert score([r["label"] for r in rows], found)["fields"]["student"] == 0.0


def test_normalize():
    assert normalize("  İYUL  Əliyeva ") == "iyul eliyeva"


def _notebook_code(name: str) -> str:
    nb = json.loads((ROOT / "ml" / name).read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and nb["metadata"]["accelerator"] == "GPU"
    assert all(not c.get("outputs") for c in nb["cells"] if c["cell_type"] == "code")
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for source in code:
        kept, shell = [], False
        for line in source.splitlines():
            if shell or line.lstrip().startswith(("!", "%")):
                shell = line.rstrip().endswith("\\")
                continue
            kept.append(line)
        ast.parse("\n".join(kept))
    return "\n".join(code)


def test_receipt_training_notebook():
    """Öyrətmə Colab-da işləyən Səhv Detektivi yolu ilədir: ən son paketlər (versiyalar
    hesabata yazılır), fp16=False + fp32 LoRA (fp16=True BFloat16 GradScaler xətası verirdi)."""
    joined = _notebook_code("qlora_receipts.ipynb")
    for needle in ('bnb_4bit_quant_type="nf4"', "LoraConfig(", "ml.receipts.sft", "compare.eval_parts()",
                   "compare.compare(", "fp16=False, bf16=False", "p.data = p.data.float()",
                   "/content/drive/MyDrive/masterai-receipts", "get_last_checkpoint", "VERSIONS",
                   '"completion"', "disable_adapter()"):
        assert needle in joined, needle
    assert "fp16=True," not in joined


def test_receipt_serve_notebook_is_pinned():
    joined = _notebook_code("vllm_receipts.ipynb")
    assert '"vllm==' in joined
    for needle in ("--enable-lora", "--lora-modules", "guided_json", "ml.bench_llm", "compare.compare("):
        assert needle in joined, needle
