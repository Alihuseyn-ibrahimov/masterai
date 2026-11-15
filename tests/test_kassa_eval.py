"""Kurs Kassası, addım 7: vahid eval hesabatı (offline hədlər CI-da, live yollar saxta LLM ilə)."""

import json

import pytest

from evals import kassa
from evals.kassa import (
    DATASETS, KASSA_GATES, agents_offline, answer_correct, check_gates, expected_values, format_report,
    load_jsonl, load_summary, receipts_eval,
)


@pytest.fixture(scope="module")
def offline_report():
    return kassa.run_all(churn=False)


def test_offline_gates_hold(offline_report):
    assert check_gates(offline_report) == []
    assert offline_report["agents"]["failures"] == []
    assert set(KASSA_GATES) == set(kassa.gate_values(offline_report))


def test_report_is_markdown_with_all_offline_sections(offline_report):
    text = format_report(offline_report)
    for heading in ("## 1. Şagird itkisi", "## 2. Qəbz oxuyucusu", "## 3. Agentlərin qoruyucu qatı"):
        assert heading in text
    assert "Keçildi: --skip-churn." in text and "Offline hədlər: hamısı keçdi." in text


def test_dataset_shape():
    cases = load_jsonl(DATASETS / "kassa_agents.jsonl")
    qa = load_jsonl(DATASETS / "kassa_qa.jsonl")
    assert len({c["id"] for c in cases}) == len(cases) and len({c["id"] for c in qa}) == len(qa)
    kinds = {c["kind"] for c in cases}
    assert kinds == {"ground", "sql", "question"}
    assert sum(c["kind"] == "ground" and not c["keep"] for c in cases) >= 5
    assert sum(c["kind"] == "sql" and not c["allowed"] for c in cases) >= 8
    assert {c["kind"] for c in qa} == {"answer", "abstain", "blocked"}


def test_gate_catches_a_broken_guard(monkeypatch):
    """Hədd həqiqətən işləyir: rəqəm yoxlamasını söndürəndə hesabat qırmızı olur."""
    monkeypatch.setattr(kassa, "ground_report", lambda text, allowed: (text, []))
    agents = agents_offline(load_jsonl(DATASETS / "kassa_agents.jsonl"),
                            load_jsonl(DATASETS / "kassa_qa.jsonl"), load_summary())
    assert agents["ground_accuracy"] < 1.0 and any("g09" in f for f in agents["failures"])


def test_name_leak_detector_finds_a_leak(monkeypatch):
    monkeypatch.setattr(kassa, "alias_names", lambda text, names: text)
    assert kassa._name_leaks(load_summary())   # ad sualda qalanda tutulur


def test_expected_values_and_answer_matching():
    summary = load_summary()
    assert expected_values("SELECT amount FROM debtors WHERE student = 'Şagird 1'", summary) == ["300"]
    assert expected_values("SELECT student FROM debtors WHERE likely_left = 1", summary) == \
        ["Kamran Əliyev", "Elvin Quliyev"]
    assert answer_correct("Kamran Əliyevin borcu 300 AZN-dir.", ["Kamran Əliyev", "300"])
    assert answer_correct("Cəmi 3 150 AZN yığılıb.", ["3150"])
    assert not answer_correct("Borc 3000 AZN-dir.", ["300"])
    assert not answer_correct("Elvin Quliyev.", ["Kamran Əliyev", "Elvin Quliyev"])


def test_receipts_live_path_uses_llm_and_falls_back():
    from ml.receipts import synth

    def fake(system, user):
        sample = next(s for s in samples if s["text"] in user)
        return json.dumps(sample["label"], ensure_ascii=False) if "ewallet" != sample["family"] else "pozuq"

    samples = synth.generate(4, 3)
    out = receipts_eval(per_family=4, seed=3, complete=fake)
    assert out["pipeline_seen"]["all_fields"] == 1.0          # düzgün JSON + grounded
    assert out["pipeline_unseen"]["sources"]["llm"] == 4      # messenger LLM-dən
    assert out["pipeline_unseen"]["sources"]["llm"] + out["pipeline_unseen"]["sources"]["rules"] \
        + out["pipeline_unseen"]["sources"]["none"] == 8     # ewallet qaydalara düşdü


def test_main_writes_markdown_and_json(tmp_path, capsys):
    out = tmp_path / "kassa.md"
    assert kassa.main(["--skip-churn", "--check", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Kurs Kassası: eval hesabatı")
    assert json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["mode"] == "offline"


def test_churn_section_with_sklearn():
    pytest.importorskip("sklearn")
    churn = kassa.churn_eval(students=150, seed=3)
    assert set(churn["call_list"]) == {"rule_only", "rule_plus_days", "rule_plus_model"}
    assert "rule_days_since_activity" in churn["top10_precision"]


# ---------- live yollar saxta LLM ilə (öz venv-lərində) ----------

def test_qa_live_scores_against_sql_truth():
    pytest.importorskip("autogen_agentchat")
    from autogen_core import FunctionCall
    from autogen_core.models import CreateResult, RequestUsage
    from autogen_ext.models.replay import ReplayChatCompletionClient

    info = {"vision": False, "function_calling": True, "json_output": False, "family": "unknown",
            "structured_output": False}
    usage = RequestUsage(prompt_tokens=0, completion_tokens=0)

    def call(sql):
        return CreateResult(finish_reason="function_calls", usage=usage, cached=False,
                            content=[FunctionCall(id="1", name="run_sql", arguments=json.dumps({"sql": sql}))])

    cases = [c for c in load_jsonl(DATASETS / "kassa_qa.jsonl") if c["id"] in ("a04", "a06", "n01", "b01")]
    analyst = ReplayChatCompletionClient([
        call("SELECT amount FROM debtors WHERE student = 'Şagird 1'"), "Şagird 1: 300 AZN.",
        call("SELECT net FROM months WHERE month = '2026-10'"), "1670 AZN.",
        call("SELECT count(*) FROM debtors WHERE likely_left = 1"), "Bilmirəm.",
    ], model_info=info)
    checker = ReplayChatCompletionClient([
        "Şagird 1-in borcu 300 AZN-dir.\nYEKUN",
        "Oktyabrda xalis qalıq 1760 AZN idi.\nYEKUN",           # səhv rəqəm: atılır → not_found
        "Gələn ay 2 şagird gedəcək.\nYEKUN",                      # proqnoz: atılır
    ], model_info=info)
    qa = kassa.qa_live(cases, load_summary(), analyst_client=analyst, checker_client=checker)
    by_id = {r["id"]: r for r in qa["cases"]}
    assert by_id["a04"]["ok"] and by_id["a04"]["answer"] == "Kamran Əliyev-in borcu 300 AZN-dir."
    assert not by_id["a06"]["ok"] and by_id["a06"]["status"] == "not_found"
    assert by_id["n01"]["ok"] and by_id["b01"]["ok"]
    assert qa["answer_accuracy"] == 0.5 and qa["abstain_rate"] == 1.0 and qa["blocked_rate"] == 1.0
    assert qa["dropped_sentences"] == 2 and qa["errors"] == 0


def test_report_live_measures_sections_and_names():
    pytest.importorskip("crewai")
    from course_planner.crew import MasterAILLM

    def fake(system, user):
        if "Hesabat redaktoru" in system:
            return ("Final Answer: ## Pul\nYığım 75%-dir. Gələn ay 4200 AZN olacaq.\n## Risk\n"
                    "Şagird 1 və Şagird 3 tərk riskindədir.\n## Bu həftə\n- Şagird 3-ə zəng et.")
        return "Final Answer: qeyd"

    rp = kassa.report_live(load_summary(), llm=MasterAILLM(completers={"x": fake}, order=["x"]))
    assert rp["sections_present"] == 1.0 and rp["at_risk_named"] == 1.0
    assert rp["dropped_sentences"] == 1 and not rp["alias_left"]
