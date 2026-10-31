"""QLoRA fine-tune dataseti: «material parçası → yaxşı suallar» cütləri (gün 16).

Mənbə - serverdəki HAZIR sual bankları. Hər bankın materialı yenidən oxunur,
produksiyadakı kimi parçalara bölünür (`pipeline.chunking`), hər sual BM25 ilə ən
uyğun parçaya bağlanır. Nümunə chat formatındadır və istifadəçi mesajı
produksiyadakı promptla BAYT-BAYT eynidir (`generation.user_prompt`):

    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", "content": "{\"questions\": [...]}"}],
     "bank_id": 12, "subject": "qanunvericilik"}

Yalnız YAXŞI suallar götürülür (model pis nümunədən də öyrənir):
- qaydalı filtr keçir (`evals.run.rules_flag`: uzunluqla özünü verən cavab, zəif izah ...);
- AI yoxlama komandası (gün 10) «fix» deməyib;
- sualla parça arasında ortaq söz var (bağlanmayan sual atılır).

Train/val bölgüsü BANK üzrədir: eyni materialın parçaları hər iki tərəfə düşsə,
val nəticəsi şişərdi.

Serverdə:
    cd /opt/masterai
    .venv/bin/python -m ml.sft_dataset --data-dir data --out /root/sft
    # → /root/sft/train.jsonl, /root/sft/val.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass

from evals.run import rules_flag
from pipeline.chunking import split
from pipeline.generation import SYSTEM_PROMPT, user_prompt
from pipeline.models import MaterialSource, MCQQuestion
from pipeline.rag import BM25, Document, Passage, tokenize
from pipeline.subjects import subject_note

MAX_PER_EXAMPLE = 5


@dataclass
class Bank:
    id: int
    subject: str
    kind: str
    location: str
    questions: list[tuple[int, MCQQuestion]]


def load_banks(data_dir: str, *, include_links: bool = False) -> list[Bank]:
    path = os.path.join(data_dir, "question_sets.db")
    if not os.path.exists(path):
        raise SystemExit(f"question_sets.db tapılmadı: {data_dir}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        flagged = {r["question_id"] for r in conn.execute("SELECT question_id FROM question_reviews "
                                                          "WHERE verdict = 'fix'")}
    except sqlite3.OperationalError:
        flagged = set()  # köhnə baza: yoxlama cədvəli yoxdur
    kinds = ("text", "pdf", "image", "link") if include_links else ("text", "pdf", "image")
    banks = []
    for b in conn.execute("SELECT id, subject, material_kind, material_location FROM question_sets "
                          f"WHERE status = 'ready' AND material_kind IN ({','.join('?' * len(kinds))}) "
                          "ORDER BY id", kinds):
        questions = []
        for q in conn.execute("SELECT id, question, options, correct_index, explanation, difficulty "
                              "FROM live_questions WHERE question_set_id = ? ORDER BY id", (b["id"],)):
            if q["id"] in flagged:
                continue
            questions.append((q["id"], MCQQuestion(
                question=q["question"], options=json.loads(q["options"]), correct_index=q["correct_index"],
                explanation=q["explanation"] or "", difficulty=q["difficulty"])))
        banks.append(Bank(b["id"], b["subject"], b["material_kind"], b["material_location"], questions))
    conn.close()
    return banks


def assign_to_chunks(chunks: list[str], questions: list[MCQQuestion]) -> dict[int, list[MCQQuestion]]:
    """Hər sual ən uyğun parçaya (sual + düzgün cavab ilə BM25). Uyğunluğu sıfırdırsa atılır."""
    doc = Document(key="m", title="", text="")
    index = BM25([Passage(doc=doc, text=c) for c in chunks])
    groups: dict[int, list[MCQQuestion]] = defaultdict(list)
    for q in questions:
        query = f"{q.question} {q.options[q.correct_index]}"
        if not tokenize(query):
            continue
        best = index.search(query, k=1)
        if best:
            groups[chunks.index(best[0].text)].append(q)
    return groups


def bank_examples(bank: Bank, text: str) -> list[dict]:
    chunks = split(text)
    good = [q for _, q in bank.questions if not rules_flag(q)]
    if not chunks or not good:
        return []
    examples = []
    for chunk_index, questions in sorted(assign_to_chunks(chunks, good).items()):
        for start in range(0, len(questions), MAX_PER_EXAMPLE):
            batch = questions[start:start + MAX_PER_EXAMPLE]
            answer = json.dumps({"questions": [q.model_dump() for q in batch]}, ensure_ascii=False)
            examples.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(chunks[chunk_index], len(batch),
                                                            subject_note=subject_note(bank.subject))},
                    {"role": "assistant", "content": answer},
                ],
                "bank_id": bank.id, "subject": bank.subject, "chunk": chunk_index,
            })
    return examples


def build(banks: list[Bank], read_text, *, val_share: float = 0.15, seed: int = 0) -> tuple[list, list, dict]:
    """`read_text(bank) -> str` (testdə saxta). Oxuna bilməyən material atlanır, sayı hesabatdadır."""
    per_bank, skipped = {}, 0
    for bank in banks:
        try:
            text = read_text(bank)
        except Exception:  # noqa: BLE001 - bir faylın itməsi bütün dataseti dayandırmasın
            skipped += 1
            continue
        examples = bank_examples(bank, text or "")
        if examples:
            per_bank[bank.id] = examples
    ids = sorted(per_bank)
    random.Random(seed).shuffle(ids)
    n_val = max(1, round(len(ids) * val_share)) if len(ids) > 1 else 0
    val_ids = set(ids[:n_val])
    train = [e for i in ids if i not in val_ids for e in per_bank[i]]
    val = [e for i in ids if i in val_ids for e in per_bank[i]]
    stats = {"banks": len(banks), "banks_used": len(ids), "banks_unreadable": skipped,
             "train_examples": len(train), "val_examples": len(val),
             "questions": sum(e["messages"][2]["content"].count('"question"') for e in train + val)}
    return train, val, stats


def read_material(bank: Bank) -> str:
    from pipeline.summary import extract_material_text

    return extract_material_text(MaterialSource(kind=bank.kind, location=bank.location))


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QLoRA dataseti: material → yaxşı suallar")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out", required=True, help="qovluq: train.jsonl + val.jsonl")
    parser.add_argument("--links", action="store_true", help="link materiallarını da oxu (Chrome açır, yavaş)")
    args = parser.parse_args(argv)
    train, val, stats = build(load_banks(args.data_dir, include_links=args.links), read_material)
    os.makedirs(args.out, exist_ok=True)
    write_jsonl(os.path.join(args.out, "train.jsonl"), train)
    write_jsonl(os.path.join(args.out, "val.jsonl"), val)
    print(json.dumps(stats, ensure_ascii=False))
    if stats["train_examples"] < 50:
        print("Qeyd: 50-dən az nümunə - fine-tune yalnız zənciri sınamaq üçündür, keyfiyyət qazancı gözləmə.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
