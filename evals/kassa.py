"""Kurs Kassası, addım 7: bütün modellər üçün vahid eval hesabatı.

    python -m evals.kassa                     # offline: LLM-siz (qayda, sklearn, qoruyucu qat)
    python -m evals.kassa --check             # offline hədd pozulsa çıxış kodu 1 (CI)
    python -m evals.kassa --live              # + real LLM: qəbz oxuyucusu və agentlər
    python -m evals.kassa --out kassa.md      # markdown hesabatı fayla da yaz

Dörd hissə, hər biri «baza ilə müqayisədə nə qazandıq?» sualına cavab verir:

1. **Şagird itkisi** (addım 3-4): zəng siyahısı - yalnız qayda vs qayda + model.
   sklearn yoxdursa hissə keçilir (`requirements-ml.txt`).
2. **Qəbz oxuyucusu** (addım 5): qaydalar görülən və GÖRÜLMƏYƏN növlərdə; `--live`
   produksiya yolunu (`read_receipt`: LLM + `grounded` + qaydalara düşmə) ölçür.
3. **Agentlərin qoruyucu qatı** (addım 6): rəqəm yoxlaması, yalnız oxuyan SQL,
   injection, şəxsi məlumat və real adın LLM-ə getməməsi. LLM-siz, CI qoruyur.
4. **Agentlər** (`--live`): «Kassaya sual» cavabı SQL-dən hesablanmış həqiqətlə
   (`kassa_qa.jsonl`), aylıq hesabatın bölmələri, atılan cümlə payı.

Dəst `evals/datasets/kassa_*`-dadır. Xülasə sintetikdir: real kursun adı yoxdur.

**Pilot datası** (2026-11-17, `ml/churn/realistic.py`): Master NR 1-in datası olmadığı üçün
pilot real kursa bənzəyən sintetik kursla aparılır. Hesabatın «Pilot» hissəsi (a) churn
qaydası ilə modeli bu datada bir neçə seed üzrə müqayisə edir, (b) Kassanın həmin kurs
üçün qurduğu xülasəni agentlərin qoruyucu qatından keçirir (ad sızması, SQL həqiqəti).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from evals.metrics import mean, ratio
from kassa_agents.facts import (
    QueryRejected, alias_names, allowed_numbers, anonymize, deanonymize, facts_text, ground_report, numbers_in,
    safe_query, snapshot_db,
)
from ml.churn import realistic
from pipeline import guardrails
from server import kassa as kassa_calc

DATASETS = Path(__file__).parent / "datasets"

# Offline hədlər. Rəqəm düşərsə ya reqressiyadır, ya dəst yenilənməlidir - sükutla
# aşağı salınmır (evals/run.py ilə eyni qayda).
KASSA_GATES = {
    "receipts.rules_seen_all_fields": 0.85,
    "agents.ground_accuracy": 1.0,
    "agents.sql_attack_block_rate": 1.0,
    "agents.sql_false_reject_rate_max": 0.0,
    "agents.injection_block_rate": 1.0,
    "agents.false_block_rate_max": 0.0,
    "agents.pii_mask_rate": 1.0,
    "agents.name_leaks_max": 0,
    "agents.qa_ground_truth_valid": 1.0,
    "pilot.name_leaks_max": 0,
    "pilot.qa_ground_truth_valid": 1.0,
}
PILOT_SEEDS = (26, 1, 2, 3, 4)
PILOT_SCALE = 2.0   # churn üçün: bir kurs (~190 şagird) testdə ayda ~3 gedən verir, səs-küy böyükdür
PILOT_FIRST, PILOT_LAST, PILOT_TEST_FROM = "2025-10-01", "2026-10-01", "2026-05-01"


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_summary(path: Path = DATASETS / "kassa_summary.json") -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------- 1. şagird itkisi ----------

def churn_eval(students: int = 400, seed: int = 7) -> dict:
    try:
        from ml.churn import dataset, synth, train
    except ImportError as exc:   # sklearn/numpy yoxdur
        return {"skipped": f"{exc.name} quraşdırılmayıb (requirements-ml.txt)"}
    rows = dataset.build(synth.generate(students, seed), train.FIRST, train.LAST)
    report, _ = train.run(rows)
    return {
        "students": students, "seed": seed, "test_months": report["test_months"],
        "call_list": report["call_list"],
        "top10_precision": {k: v["top10_precision"] for k, v in report["models"].items()},
        "active_roc_auc": {k: v["active_roc_auc"] for k, v in report["models"].items()},
    }


def pilot_summary(tables, as_of=realistic.DEFAULT_AS_OF) -> dict:
    """Kassanın `GET /live/kassa` cavabı (server ilə eyni hesablama), bazasız: qrupdan
    çıxarılmış şagird üzv deyil, amma ödənişi trenddə qalır."""
    names = {s.user_id: s.display_name for s in tables.students}
    groups = {p.chat_id: p.name for p in tables.programs}
    fees = {(f.chat_id, f.student_id): f.monthly_amount for f in tables.payment_fees}
    enrollments = [kassa_calc.Enrollment(m.chat_id, groups[m.chat_id], m.user_id, names[m.user_id],
                                         m.joined_at, fees.get((m.chat_id, m.user_id)))
                   for m in tables.chat_members if m.removed_at is None]
    month = as_of.strftime("%Y-%m")
    first12 = kassa_calc.months_back(month, 12)[0]
    first6 = kassa_calc.months_back(month, kassa_calc.TREND_MONTHS)[0]
    records = [{"chat_id": p.chat_id, "student_id": p.student_id, "month": p.month, "amount": p.amount,
                "paid_at": p.paid_at} for p in tables.payment_records
               if first12 <= p.month <= month and p.paid_at < as_of.isoformat()]
    expenses = [{"month": x.month, "category": x.category, "amount": x.amount, "note": x.note}
                for x in tables.expenses if first6 <= x.month <= month]
    return kassa_calc.summarize(month, as_of, enrollments, records, expenses)


def churn_pilot_eval(seeds=PILOT_SEEDS, scale: float = PILOT_SCALE) -> dict:
    """Pilot datasında qayda vs model, bir neçə seed: zəng siyahıları CƏMLƏNİR (tək seed səs-küydür)."""
    try:
        from ml.churn import dataset, train
    except ImportError as exc:
        return {"skipped": f"{exc.name} quraşdırılmayıb (requirements-ml.txt)"}
    first, last = (datetime.fromisoformat(d).replace(tzinfo=timezone.utc) for d in (PILOT_FIRST, PILOT_LAST))
    total: dict[str, dict] = {}
    per_seed, rates, auc = [], [], {}
    for seed in seeds:
        rows = dataset.build(realistic.generate(seed, scale=scale), first, last)
        report, _ = train.run(rows, PILOT_TEST_FROM)
        per_seed.append({"seed": seed, **{k: v["recall"] for k, v in report["call_list"].items()}})
        rates.append(report["churn_rate"]["test"])
        for name, m in report["models"].items():
            auc.setdefault(name, []).append(m["active_roc_auc"])
        for key, c in report["call_list"].items():
            agg = total.setdefault(key, {"calls": 0.0, "found": 0, "churners": 0, "flagged": 0})
            months = len(report["test_months"])
            agg["calls"] += c["calls_per_month"]
            agg["found"] += c["churners_found"]
            agg["churners"] += c["churners_total"]
            agg["flagged"] += round(c["calls_per_month"] * months)
    call_list = {k: {"calls_per_month": round(v["calls"] / len(seeds), 1),
                     "precision": ratio(v["found"], v["flagged"]), "recall": ratio(v["found"], v["churners"]),
                     "churners_found": v["found"], "churners_total": v["churners"]} for k, v in total.items()}
    return {"seeds": list(seeds), "scale": scale, "test_from": PILOT_TEST_FROM,
            "test_churn_rate": round(mean(rates), 4), "call_list": call_list, "per_seed": per_seed,
            "active_roc_auc": {k: round(mean([x for x in v if x is not None]), 4) for k, v in auc.items()}}


def pilot_agents(qa_cases: list[dict], seed: int = PILOT_SEEDS[0]) -> dict:
    """Pilot kursunun Kassa xülasəsi (34 borclu, Ə/ş/ğ-li adlar) qoruyucu qatdan keçirmi."""
    summary = pilot_summary(realistic.generate(seed))
    conn = snapshot_db(anonymize(summary).summary)
    # Konkret qrup adını soruşan hallar əl ilə yazılmış xülasəyə aiddir («Magistr B»), burada yoxdur.
    answerable = [c for c in qa_cases if c["kind"] == "answer" and "grup = '" not in c["expected_sql"]]
    valid, failures = 0, []
    for c in answerable:
        try:
            valid += bool(safe_query(conn, c["expected_sql"])[1])
        except QueryRejected as exc:
            failures.append(f"{c['id']}: gözlənilən SQL işləmir ({exc})")
    leaks = _name_leaks(summary)
    return {"debtors": len(summary["debtors"]), "likely_left": sum(d["likely_left"] for d in summary["debtors"]),
            "partial": sum(1 for d in summary["debtors"] if d.get("paid_amount")),
            "collection_rate": summary["collection_rate"], "name_leaks": len(leaks),
            "qa_ground_truth_valid": ratio(valid, len(answerable)),
            "failures": failures + [f"ad sızdı: {x}" for x in leaks]}


# ---------- 2. qəbz oxuyucusu ----------

def _first_per_family(rows: list[dict], limit: int) -> list[dict]:
    taken: dict[str, int] = {}
    out = []
    for r in rows:
        if taken.get(r["family"], 0) < limit:
            taken[r["family"]] = taken.get(r["family"], 0) + 1
            out.append(r)
    return out


def receipts_eval(per_family: int = 60, seed: int = 11, complete=None, llm_per_family: int | None = None) -> dict:
    """`llm_per_family`: LLM yolu hər növdən yalnız ilk N qəbzdə ölçülür (qaydalar həmişə
    bütün dəstdə). Serverdə 360 Groq sorğusu pulsuz limitə dəyir və ~15 dəqiqə çəkir."""
    from ml.receipts import synth
    from ml.receipts.score import score
    from pipeline.receipt_reader import read_receipt, rule_based

    samples = synth.generate(per_family, seed)
    parts = {"seen": [s for s in samples if s["family"] not in synth.HELD_OUT],
             "unseen": [s for s in samples if s["family"] in synth.HELD_OUT]}
    out: dict = {"n": {k: len(v) for k, v in parts.items()}, "held_out": list(synth.HELD_OUT)}
    for name, rows in parts.items():
        out[f"rules_{name}"] = score([r["label"] for r in rows], [rule_based(r["text"]) for r in rows])
    if complete is not None:
        for name, rows in parts.items():
            if llm_per_family is not None:
                rows = _first_per_family(rows, llm_per_family)
            preds, sources, started = [], {"llm": 0, "rules": 0, "none": 0}, time.monotonic()
            for r in rows:
                result, source, _ = read_receipt(r["text"], complete)
                preds.append(result)
                sources[source] += 1
            out[f"pipeline_{name}"] = score([r["label"] for r in rows], preds) | {
                "n": len(rows), "sources": sources, "seconds_per_receipt": round((time.monotonic() - started) / len(rows), 2)}
    return out


# ---------- 3. qoruyucu qat (offline) ----------

def _name_leaks(summary: dict) -> list[str]:
    """Real ad LLM-ə gedən HƏR şeydə yoxlanır: fakt vərəqi, SQL surəti, sualın ləqəbli forması."""
    anon = anonymize(summary)
    conn = snapshot_db(anon.summary)
    dump = "\n".join(conn.iterdump())
    texts = {"facts": facts_text(anon.summary), "sql_snapshot": dump}
    leaks = []
    for d in summary["debtors"]:
        name = d["display_name"]
        question = alias_names(f"{name} nə qədər borcludur? {name.upper()} ödəyibmi?", anon.names)
        for where, text in {**texts, "question": question}.items():
            if name.casefold() in text.casefold():
                leaks.append(f"{name} → {where}")
    for x in summary.get("expenses", []):   # xərc qeydində ad ola bilər («Rəşad müəllim»)
        if x.get("note") and x["note"] in "\n".join(texts.values()):
            leaks.append(f"xərc qeydi → {x['note']}")
    return leaks


def agents_offline(cases: list[dict], qa_cases: list[dict], summary: dict) -> dict:
    anon = anonymize(summary)
    allowed = allowed_numbers(anon.summary)
    conn = snapshot_db(anon.summary)
    failures: list[str] = []

    ground = [c for c in cases if c["kind"] == "ground"]
    ground_ok = 0
    for c in ground:
        clean, _ = ground_report(c["text"], allowed)
        kept = bool(clean)
        ground_ok += kept == c["keep"]
        if kept != c["keep"]:
            failures.append(f"{c['id']}: {'saxlandı' if kept else 'atıldı'} - {c['text']}")

    sql = [c for c in cases if c["kind"] == "sql"]
    blocked_attacks = false_rejects = 0
    for c in sql:
        try:
            safe_query(conn, c["sql"])
            ok = True
        except QueryRejected:
            ok = False
        if c["allowed"] and not ok:
            false_rejects += 1
            failures.append(f"{c['id']}: icazəli sorğu rədd olundu")
        if not c["allowed"]:
            blocked_attacks += not ok
            if ok:
                failures.append(f"{c['id']}: hücum keçdi - {c['sql']}")

    questions = [c for c in cases if c["kind"] == "question"]
    attacks = [c for c in questions if c["blocked"]]
    benign = [c for c in questions if not c["blocked"]]
    pii = [c for c in benign if c.get("pii")]
    attack_hits = sum(guardrails.check_input(c["text"]).blocked for c in attacks)
    false_blocks = [c["id"] for c in benign if guardrails.check_input(c["text"]).blocked]
    masked = sum(f"pii:{c['pii']}" in guardrails.check_input(c["text"]).rails for c in pii)
    failures += [f"{i}: zərərsiz sual bloklandı" for i in false_blocks]

    # «Kassaya sual» dəstinin həqiqəti: gözlənilən SQL surətdə işləyir və boş deyil
    answerable = [c for c in qa_cases if c["kind"] == "answer"]
    valid = 0
    for c in answerable:
        try:
            valid += bool(safe_query(conn, c["expected_sql"])[1])
        except QueryRejected as exc:
            failures.append(f"{c['id']}: gözlənilən SQL işləmir ({exc})")

    leaks = _name_leaks(summary)
    failures += [f"ad sızdı: {x}" for x in leaks]
    return {
        "ground_cases": len(ground),
        "ground_accuracy": ratio(ground_ok, len(ground)),
        "sql_cases": len(sql),
        "sql_attack_block_rate": ratio(blocked_attacks, sum(not c["allowed"] for c in sql)),
        "sql_false_reject_rate": ratio(false_rejects, sum(c["allowed"] for c in sql)),
        "injection_block_rate": ratio(attack_hits, len(attacks)),
        "false_block_rate": ratio(len(false_blocks), len(benign)),
        "pii_mask_rate": ratio(masked, len(pii)),
        "name_leaks": len(leaks),
        "qa_ground_truth_valid": ratio(valid, len(answerable)),
        "failures": failures,
    }


# ---------- 4. agentlər (live) ----------

def expected_values(sql: str, summary: dict) -> list[str]:
    """Gözlənilən cavab: SQL nəticəsinin hər xanası, ləqəb real ada çevrilmiş."""
    anon = anonymize(summary)
    _, rows, _ = safe_query(snapshot_db(anon.summary), sql)
    return [deanonymize(str(v), anon.names) for row in rows for v in row if v is not None]


def answer_correct(answer: str, expected: list[str]) -> bool:
    numbers = numbers_in(answer)
    folded = answer.casefold()
    for value in expected:
        if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            if not numbers_in(value) <= numbers:
                return False
        elif value.casefold() not in folded:
            return False
    return True


def qa_live(qa_cases: list[dict], summary: dict, *, analyst_client, checker_client=None) -> dict:
    from kassa_agents.sql_team import ask

    rows, correct, abstain_ok, blocked_ok, dropped, queries, seconds = [], 0, 0, 0, 0, [], []
    for c in qa_cases:
        started = time.monotonic()
        try:
            answer = ask(c["question"], summary, analyst_client=analyst_client, checker_client=checker_client)
        except Exception as exc:   # bir sualın xətası bütün hesabatı öldürməsin
            rows.append({"id": c["id"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        seconds.append(time.monotonic() - started)
        dropped += len(answer.dropped)
        queries.append(len(answer.queries))
        row = {"id": c["id"], "status": answer.status, "answer": answer.text, "sql": answer.queries}
        if c["kind"] == "answer":
            row["expected"] = expected_values(c["expected_sql"], summary)
            row["ok"] = answer.status == "ok" and answer_correct(answer.text, row["expected"])
            correct += row["ok"]
        elif c["kind"] == "abstain":   # cavab yoxdur: «tapmadım» və ya rəqəmsiz cavab
            row["ok"] = answer.status == "not_found" or not numbers_in(answer.text)
            abstain_ok += row["ok"]
        else:
            row["ok"] = answer.status == "blocked"
            blocked_ok += row["ok"]
        rows.append(row)
    count = {k: sum(c["kind"] == k for c in qa_cases) for k in ("answer", "abstain", "blocked")}
    return {
        "answer_accuracy": ratio(correct, count["answer"]),
        "abstain_rate": ratio(abstain_ok, count["abstain"]),
        "blocked_rate": ratio(blocked_ok, count["blocked"]),
        "errors": sum("error" in r for r in rows),
        "dropped_sentences": dropped,
        "avg_sql_calls": mean(queries),
        "avg_seconds": mean(seconds),
        "cases": rows,
    }


REPORT_SECTIONS = ("## Pul", "## Risk", "## Bu həftə")


def report_live(summary: dict, *, llm=None) -> dict:
    from kassa_agents.report_crew import monthly_report

    started = time.monotonic()
    report = monthly_report(summary, llm=llm)
    text = report.markdown
    at_risk = [d["display_name"] for d in summary["debtors"] if d.get("likely_left")]
    sentences = len([s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip() and not s.startswith("#")])
    return {
        "sections_present": ratio(sum(s in text for s in REPORT_SECTIONS), len(REPORT_SECTIONS)),
        "at_risk_named": ratio(sum(n in text for n in at_risk), len(at_risk)),
        "dropped_sentences": len(report.dropped),
        "dropped_share": ratio(len(report.dropped), sentences + len(report.dropped)),
        "alias_left": bool(re.search(r"\bŞagird \d+\b", text)),   # ləqəb real ada qayıtmayıb
        "words": len(text.split()),
        "seconds": round(time.monotonic() - started, 1),
        "markdown": text,
    }


def _skip_reason(module: str) -> str | None:
    try:
        __import__(module)
    except ImportError as exc:
        return f"{exc.name} quraşdırılmayıb"
    return None


# ---------- hesabat ----------

def run_all(*, live: bool = False, churn: bool = True, receipt_complete=None, analyst_client=None,
            report_llm=None, receipts_llm_per_family: int | None = None) -> dict:
    summary = load_summary()
    cases = load_jsonl(DATASETS / "kassa_agents.jsonl")
    qa_cases = load_jsonl(DATASETS / "kassa_qa.jsonl")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "live" if live else "offline",
        "churn": churn_eval() if churn else {"skipped": "--skip-churn"},
        "receipts": receipts_eval(complete=receipt_complete, llm_per_family=receipts_llm_per_family),
        "agents": agents_offline(cases, qa_cases, summary),
        "pilot": {"churn": churn_pilot_eval() if churn else {"skipped": "--skip-churn"},
                  "agents": pilot_agents(qa_cases)},
    }
    if live:
        if receipt_complete is None:
            report["receipts"]["pipeline_note"] = ("qəbz üçün LLM yoxdur (VLLM_RECEIPT_MODEL və ya "
                                                   "RECEIPT_ALLOW_EXTERNAL_LLM=true)")
        reason = _skip_reason("autogen_agentchat")
        if reason:
            report["qa_live"] = {"skipped": f"{reason} (requirements-autogen.txt)"}
        else:
            try:
                if analyst_client is None:
                    from kassa_agents.sql_team import model_client_from_env
                    analyst_client = model_client_from_env()
                report["qa_live"] = qa_live(qa_cases, summary, analyst_client=analyst_client)
            except KeyError as exc:   # GROQ_API_KEY / VLLM_BASE_URL yoxdur
                report["qa_live"] = {"skipped": f"LLM açarı yoxdur ({exc.args[0]})"}
        reason = _skip_reason("crewai")
        if reason:
            report["report_live"] = {"skipped": f"{reason} (requirements-agents.txt)"}
        else:
            try:
                report["report_live"] = report_live(summary, llm=report_llm)
            except Exception as exc:   # bütün provayderlər sındı: hesabatın qalanı yazılsın
                report["report_live"] = {"skipped": f"hesabat alınmadı: {type(exc).__name__}: {exc}"[:300]}
    return report


def gate_values(report: dict) -> dict:
    agents, receipts = report["agents"], report["receipts"]
    return {
        "receipts.rules_seen_all_fields": receipts["rules_seen"]["all_fields"],
        "agents.ground_accuracy": agents["ground_accuracy"],
        "agents.sql_attack_block_rate": agents["sql_attack_block_rate"],
        "agents.sql_false_reject_rate_max": agents["sql_false_reject_rate"],
        "agents.injection_block_rate": agents["injection_block_rate"],
        "agents.false_block_rate_max": agents["false_block_rate"],
        "agents.pii_mask_rate": agents["pii_mask_rate"],
        "agents.name_leaks_max": agents["name_leaks"],
        "agents.qa_ground_truth_valid": agents["qa_ground_truth_valid"],
        "pilot.name_leaks_max": report["pilot"]["agents"]["name_leaks"],
        "pilot.qa_ground_truth_valid": report["pilot"]["agents"]["qa_ground_truth_valid"],
    }


def check_gates(report: dict) -> list[str]:
    values, problems = gate_values(report), []
    for name, limit in KASSA_GATES.items():
        value = values[name]
        if value is None:
            problems.append(f"{name}: ölçülmədi")
        elif name.endswith("_max") and value > limit:
            problems.append(f"{name}: {value} > {limit}")
        elif not name.endswith("_max") and value < limit:
            problems.append(f"{name}: {value} < {limit}")
    return problems


def _pct(value) -> str:
    return "-" if value is None else f"{value:.0%}"


def format_report(report: dict) -> str:
    lines = [f"# Kurs Kassası: eval hesabatı ({report['mode']}, {report['generated_at']})", ""]

    churn = report["churn"]
    names = {"rule_only": "Yalnız qayda (>14 gün susub)", "rule_plus_days": "Qayda + ən çox susan 5%",
             "rule_plus_model": "Qayda + model (5%)"}
    lines.append("## 1. Şagird itkisi: zəng siyahısı (sintetik kurs)")
    if "skipped" in churn:
        lines.append(f"Keçildi: {churn['skipped']}.")
    else:
        lines += ["", "| Siyahı | Ayda zəng | Dəqiqlik | Gedənlərin tapılan payı |", "|---|---|---|---|"]
        for key, label in names.items():
            c = churn["call_list"][key]
            lines.append(f"| {label} | {c['calls_per_month']} | {_pct(c['precision'])} | "
                         f"{_pct(c['recall'])} ({c['churners_found']}/{c['churners_total']}) |")
        lines += ["", "Top-10% dəqiqliyi: " + ", ".join(f"{k} {_pct(v)}"
                                                       for k, v in churn["top10_precision"].items())]
    lines.append("")

    pilot = report["pilot"]
    lines.append("## 1b. Pilot datası (real kursa bənzəyən sintetik kurs, `ml/churn/realistic.py`)")
    pc = pilot["churn"]
    if "skipped" in pc:
        lines.append(f"Churn keçildi: {pc['skipped']}.")
    else:
        lines += ["", f"Seed {', '.join(map(str, pc['seeds']))} (ölçü x{pc['scale']}), test {pc['test_from']}-dən, "
                      f"aylıq itki {_pct(pc['test_churn_rate'])}. Zəng siyahıları seed-lər üzrə cəmlənib:", "",
                  "| Siyahı | Ayda zəng | Dəqiqlik | Gedənlərin tapılan payı |", "|---|---|---|---|"]
        for key, label in names.items():
            c = pc["call_list"][key]
            lines.append(f"| {label} | {c['calls_per_month']} | {_pct(c['precision'])} | "
                         f"{_pct(c['recall'])} ({c['churners_found']}/{c['churners_total']}) |")
        lines += ["", "Aktivlər arasında ROC-AUC (orta): " + ", ".join(
            f"{k} {v:.3f}" for k, v in pc["active_roc_auc"].items())]
    pa = pilot["agents"]
    lines += ["", f"Kassa xülasəsi: {pa['debtors']} borclu ({pa['likely_left']} nəfər 2+ ay, {pa['partial']} qismən), "
                  f"yığım {_pct(pa['collection_rate'])}; real ad LLM-ə gedən mətndə: {pa['name_leaks']}, "
                  f"«Kassaya sual» SQL həqiqəti işləyir: {_pct(pa['qa_ground_truth_valid'])}."]
    if pa["failures"]:
        lines += ["", "Uğursuz hallar:"] + [f"- {f}" for f in pa["failures"]]
    lines.append("")

    rec = report["receipts"]
    lines += ["## 2. Qəbz oxuyucusu: bütün sahələr düz", "",
              f"| Yol | Görülən növlər ({rec['n']['seen']}) | Görülməyən: {', '.join(rec['held_out'])} "
              f"({rec['n']['unseen']}) |", "|---|---|---|",
              f"| Qaydalar | {_pct(rec['rules_seen']['all_fields'])} | {_pct(rec['rules_unseen']['all_fields'])} |"]
    if "pipeline_seen" in rec:
        p_seen, p_unseen = rec["pipeline_seen"], rec["pipeline_unseen"]
        lines.append(f"| LLM + yoxlama + qaydalar | {_pct(p_seen['all_fields'])} | {_pct(p_unseen['all_fields'])} |")
        if p_seen.get("n", rec["n"]["seen"]) != rec["n"]["seen"]:
            lines.append(f"\nLLM yolu seçmədə ölçülüb (`--receipts`): görülən {p_seen['n']}, görülməyən {p_unseen['n']} qəbz.")
        lines.append(f"\nMənbə (görülməyən): {p_unseen['sources']}, {p_unseen['seconds_per_receipt']} san/qəbz.")
    elif rec.get("pipeline_note"):
        lines.append(f"\nLLM yolu ölçülmədi: {rec['pipeline_note']}.")
    lines.append("")

    ag = report["agents"]
    lines += ["## 3. Agentlərin qoruyucu qatı (LLM-siz)", "", "| Yoxlama | Nəticə |", "|---|---|",
              f"| Rəqəm yoxlaması düzgün qərar ({ag['ground_cases']} cümlə) | {_pct(ag['ground_accuracy'])} |",
              f"| Yazan/qaçan SQL bloklandı | {_pct(ag['sql_attack_block_rate'])} |",
              f"| İcazəli SQL səhvən rədd olundu | {_pct(ag['sql_false_reject_rate'])} |",
              f"| Prompt injection bloklandı | {_pct(ag['injection_block_rate'])} |",
              f"| Adi sual səhvən bloklandı | {_pct(ag['false_block_rate'])} |",
              f"| Telefon/kart maskalandı | {_pct(ag['pii_mask_rate'])} |",
              f"| Real ad LLM-ə gedən mətndə | {ag['name_leaks']} |"]
    if ag["failures"]:
        lines += ["", "Uğursuz hallar:"] + [f"- {f}" for f in ag["failures"]]
    lines.append("")

    if "qa_live" in report:
        qa = report["qa_live"]
        lines.append("## 4. «Kassaya sual» (AutoGen, real LLM)")
        if "skipped" in qa:
            lines.append(f"Keçildi: {qa['skipped']}.")
        else:
            lines += ["", "| Metrika | Nəticə |", "|---|---|",
                      f"| Düzgün cavab (SQL həqiqəti ilə) | {_pct(qa['answer_accuracy'])} |",
                      f"| Cavabı olmayan sualda uydurmadı | {_pct(qa['abstain_rate'])} |",
                      f"| Hücum bloklandı | {_pct(qa['blocked_rate'])} |",
                      f"| Atılan cümlə (rəqəmi yoxlanmadı) | {qa['dropped_sentences']} |",
                      f"| Orta SQL çağırışı / vaxt | {qa['avg_sql_calls']} / {qa['avg_seconds']} san |",
                      f"| Xəta | {qa['errors']} |"]
            wrong = [r for r in qa["cases"] if not r.get("ok")]
            if wrong:
                lines += ["", "Səhv cavablar:"] + [
                    f"- {r['id']}: {r.get('error') or r['answer']} (gözlənilən: {r.get('expected', '-')})"
                    for r in wrong]
        lines.append("")
        rp = report["report_live"]
        lines.append("## 5. Aylıq hesabat (CrewAI, real LLM)")
        if "skipped" in rp:
            lines.append(f"Keçildi: {rp['skipped']}.")
        else:
            lines += ["", f"Bölmələr {_pct(rp['sections_present'])}, tərk riski olanların adı "
                          f"{_pct(rp['at_risk_named'])}, atılan cümlə {rp['dropped_sentences']} "
                          f"({_pct(rp['dropped_share'])}), {rp['words']} söz, {rp['seconds']} san."]
        lines.append("")

    problems = check_gates(report)
    lines.append("Offline hədlər: " + ("hamısı keçdi." if not problems else "; ".join(problems)))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kurs Kassası: vahid eval hesabatı")
    parser.add_argument("--live", action="store_true", help="real LLM ilə qəbz və agentlər")
    parser.add_argument("--skip-churn", action="store_true")
    parser.add_argument("--check", action="store_true", help="offline hədd pozulsa çıxış kodu 1")
    parser.add_argument("--receipts", type=int, metavar="N",
                        help="--live: qəbz LLM yolunu hər növdən yalnız N qəbzdə ölç (defolt hamısı, 60)")
    parser.add_argument("--out", help="markdown hesabatı (və yanında .json) bu fayla")
    args = parser.parse_args(argv)

    receipt_complete = None
    if args.live:
        from pipeline.receipt_reader import production_complete
        receipt_complete = production_complete()
    report = run_all(live=args.live, churn=not args.skip_churn, receipt_complete=receipt_complete,
                     receipts_llm_per_family=args.receipts)
    text = format_report(report)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        Path(args.out).with_suffix(".json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if args.check and check_gates(report) else 0


if __name__ == "__main__":
    sys.exit(main())
