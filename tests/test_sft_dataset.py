"""Gün 16: QLoRA dataseti, generasiya qiymətləndirməsi və Colab notebook-u."""

import ast
import json
from pathlib import Path

from ml.score_generation import grounded, score
from ml.sft_dataset import Bank, assign_to_chunks, build, load_banks, main
from pipeline.generation import SYSTEM_PROMPT, generate_for_chunks, user_prompt
from pipeline.models import MCQQuestion
from pipeline.rag import tokenize
from pipeline.subjects import subject_note
from server.question_set_store import QuestionSetStore

ROOT = Path(__file__).resolve().parents[1]

# İki mövzu, hər biri bir parçadan böyük: bölücü onları ayrı parçalara qoyur.
CONSTITUTION = ("Azərbaycan Respublikasının Konstitusiyası 1995-ci ildə referendumla qəbul edilib. "
                "Milli Məclis 125 deputatdan ibarətdir. ") * 70
PHOTOSYNTHESIS = ("Fotosintez xloroplastlarda gedir, xlorofil işığı udur və oksigen ayrılır. ") * 90
MATERIAL = CONSTITUTION + "\n\n" + PHOTOSYNTHESIS


def mcq(question, options, correct=0, explanation="Materialda belə yazılıb, çünki mətn bunu deyir.",
        difficulty="orta"):
    return MCQQuestion(question=question, options=options, correct_index=correct, explanation=explanation,
                       difficulty=difficulty)


GOOD_LAW = mcq("Milli Məclis neçə deputatdan ibarətdir?", ["125", "100", "150", "175", "200"])
GOOD_BIO = mcq("Fotosintez harada gedir?", ["Xloroplastlarda", "Nüvədə", "Ribosomda", "Vakuolda", "Membranda"])
GIVEAWAY = mcq("Konstitusiya necə qəbul edilib?", ["Fərmanla", "Qərarla",
               "Ümumxalq səsverməsi - referendum yolu ilə 1995-ci ildə", "Əmrlə", "Sərəncamla"], correct=2)


def test_user_prompt_is_byte_identical_to_production():
    """Fine-tune promptu produksiyadakından fərqlənsə, model öyrəndiyini istifadədə görməz."""
    seen = []

    def fake(system, user):
        seen.append((system, user))
        return json.dumps({"questions": [GOOD_LAW.model_dump()]}, ensure_ascii=False)

    note = subject_note("qanunvericilik")
    generate_for_chunks(["Parça mətni"], {"x": fake}, order=["x"], questions_per_chunk=2, subject_note=note)
    assert seen == [(SYSTEM_PROMPT, user_prompt("Parça mətni", 2, subject_note=note))]


def test_questions_go_to_their_own_chunk():
    from pipeline.chunking import split

    chunks = split(MATERIAL)
    assert len(chunks) >= 2
    groups = assign_to_chunks(chunks, [GOOD_LAW, GOOD_BIO])
    by_question = {q.question: i for i, qs in groups.items() for q in qs}
    assert "Milli Məclis" in chunks[by_question[GOOD_LAW.question]]
    assert "Fotosintez" in chunks[by_question[GOOD_BIO.question]]


def _banks(tmp_path):
    store = QuestionSetStore(str(tmp_path / "question_sets.db"))
    ids = []
    for i in range(4):
        bank = store.create(subject="qanunvericilik", title=f"B{i}", material_kind="text",
                            material_location=f"/m{i}.txt", created_by=1)
        added = [store.add_question(bank["id"], q) for q in (GOOD_LAW, GOOD_BIO, GIVEAWAY)]
        store.mark_ready(bank["id"])
        ids.append((bank["id"], added))
    # AI komandası (gün 10) bir bankda bioloji sualı «fix» deyib.
    store.start_review(ids[0][0])
    store.finish_review(ids[0][0], [{"question_id": ids[0][1][1]["id"], "verdict": "fix", "issues": [],
                                     "suggestion": None}])
    link = store.create(subject="x", title="L", material_kind="link", material_location="https://x.az",
                        created_by=1)
    store.mark_ready(link["id"])
    return ids


def test_load_banks_skips_links_and_ai_flagged(tmp_path):
    ids = _banks(tmp_path)
    banks = load_banks(str(tmp_path))
    assert [b.id for b in banks] == [i for i, _ in ids]          # link bankı yoxdur
    assert len(banks[0].questions) == 2 and len(banks[1].questions) == 3
    assert len(load_banks(str(tmp_path), include_links=True)) == 5


def test_build_filters_bad_questions_and_splits_by_bank(tmp_path):
    _banks(tmp_path)
    banks = load_banks(str(tmp_path))
    banks.append(Bank(99, "x", "text", "/yox.txt", [(1, GOOD_LAW)]))
    train, val, stats = build(banks, lambda b: (_ for _ in ()).throw(OSError()) if b.id == 99 else MATERIAL)
    assert stats["banks_unreadable"] == 1 and stats["banks_used"] == 4
    assert {e["bank_id"] for e in train}.isdisjoint({e["bank_id"] for e in val}) and val
    for example in train + val:
        system, user, assistant = (m["content"] for m in example["messages"])
        assert system == SYSTEM_PROMPT and "Material:\n---\n" in user
        answer = json.loads(assistant)["questions"]
        assert all(MCQQuestion(**q) for q in answer)
        assert GIVEAWAY.question not in assistant      # uzunluqla özünü verən sual öyrədilmir
    assert all(GOOD_BIO.question not in e["messages"][2]["content"]
               for e in train + val if e["bank_id"] == banks[0].id)


def test_cli_writes_train_and_val(tmp_path, monkeypatch):
    import ml.sft_dataset as mod

    _banks(tmp_path)
    monkeypatch.setattr(mod, "read_material", lambda bank: MATERIAL)
    out = tmp_path / "sft"
    assert main(["--data-dir", str(tmp_path), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in (out / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["messages"][0]["role"] == "system"


def test_score_reference_garbage_and_giveaway(tmp_path):
    _banks(tmp_path)
    train, val, _ = build(load_banks(str(tmp_path)), lambda b: MATERIAL)
    rows = train + val
    perfect = score(rows, [e["messages"][2]["content"] for e in rows])
    assert perfect["parse_rate"] == 1.0 and perfect["count_rate"] == 1.0
    assert perfect["rules_pass"] == 1.0 and perfect["giveaway_rate"] == 0.0 and perfect["grounded_rate"] == 1.0

    broken = score(rows, ["Bağışlayın, sual yaza bilmərəm."] * len(rows))
    assert broken["parse_rate"] == 0.0 and broken["questions"] == 0 and broken["rules_pass"] is None

    cheat = json.dumps({"questions": [GIVEAWAY.model_dump()]}, ensure_ascii=False)
    assert score(rows[:1], [cheat])["giveaway_rate"] == 1.0


def test_grounded():
    material = set(tokenize("Milli Məclis 125 deputatdan ibarətdir"))
    assert grounded("125 deputat", material)
    assert not grounded("Ali Məhkəmənin sədri", material)


def test_notebook_is_valid_and_pinned():
    nb = json.loads((ROOT / "ml" / "qlora_mcq.ipynb").read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and nb["metadata"]["accelerator"] == "GPU"
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for source in code:
        kept, shell = [], False
        for line in source.splitlines():
            if shell or line.lstrip().startswith(("!", "%")):
                shell = line.rstrip().endswith("\\")   # «\» ilə davam edən shell əmri
                continue
            kept.append(line)
        python = "\n".join(kept)
        ast.parse(python)  # sintaksis səhvi Colab-da 20 dəqiqəlik quraşdırmadan sonra çıxmasın
    joined = "\n".join(code)
    for pin in ('"trl==', '"peft==', '"transformers==', '"bitsandbytes=='):
        assert pin in joined
    assert "bnb_4bit_quant_type=\"nf4\"" in joined and "LoraConfig(" in joined
    assert "ml.score_generation" in joined and "merge_and_unload" in joined
    assert all(not c.get("outputs") for c in nb["cells"] if c["cell_type"] == "code")
