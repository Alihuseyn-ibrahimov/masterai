"""Eval dəsti (gün 13): dəstin bütövlüyü, metrikalar, offline hədlər və live axının sxemi."""

import json
import re

import pytest

from evals import metrics
from evals.run import (
    DATASETS,
    OFFLINE_GATES,
    format_report,
    load_documents,
    load_jsonl,
    main,
    run_all,
    to_question,
)
from pipeline.review_team import FACT_SYSTEM_PROMPT, PEDAGOGUE_SYSTEM_PROMPT
from pipeline.tutor_graph import QUIZ_SYSTEM_PROMPT

DOCS = load_documents()
TUTOR = load_jsonl(DATASETS / "tutor.jsonl")
REVIEW = load_jsonl(DATASETS / "review.jsonl")
KEYS = {d.key for d in DOCS}


# ---- Dəstin bütövlüyü -------------------------------------------------------

def test_ids_unique():
    for cases in (TUTOR, REVIEW):
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids))


def test_tutor_cases_well_formed():
    assert len(TUTOR) >= 25
    for case in TUTOR:
        assert case["expect_kind"] in {"answer", "quiz", "not_found", "offtopic"}, case["id"]
        assert set(case["expect_sources"]) <= KEYS, case["id"]
        if case["expect_kind"] == "answer":
            assert case["expect_sources"] and case["must_include"], case["id"]


def test_tutor_keywords_are_in_expected_source():
    """Açar söz mənbədə yoxdursa, model onu yaza bilməz - hal özü səhvdir."""
    texts = {d.key: metrics._lower(d.text) for d in DOCS}
    for case in TUTOR:
        for keyword in case.get("must_include", []):
            assert any(metrics._lower(keyword) in texts[k] for k in case["expect_sources"]), (case["id"], keyword)


def test_review_cases_well_formed():
    assert {c["label"] for c in REVIEW} == {"ok", "fix"}
    for case in REVIEW:
        assert case["source"] in KEYS, case["id"]
        to_question(case)  # MCQQuestion validasiyası: 5 variant, indeks 0-4
        if case["label"] == "fix":
            assert case["problem"] in {"wrong_answer", "giveaway", "two_correct", "self_answering",
                                       "not_in_material"}, case["id"]


# ---- Metrikalar -------------------------------------------------------------

def test_retrieval_metrics():
    assert metrics.hit_at_k(["a", "b"], ["b"], 1) is False
    assert metrics.hit_at_k(["a", "b"], ["b"], 2) is True
    assert metrics.reciprocal_rank(["a", "b"], ["b"]) == 0.5
    assert metrics.reciprocal_rank(["a"], ["b"]) == 0.0


def test_ratio_none_when_nothing_measured():
    assert metrics.ratio(0, 0) is None
    assert metrics.mean([None, None]) is None
    assert metrics.mean([1, None, 3]) == 2


def test_keyword_recall_uses_azerbaijani_lowercase():
    assert metrics.keyword_recall("İcra hakimiyyətini PREZİDENT həyata keçirir", ["prezident"]) == 1.0
    assert metrics.keyword_recall("Beş il", ["beş", "125"]) == 0.5
    assert metrics.keyword_recall("x", []) is None


def test_citations_valid():
    assert metrics.citations_valid("Fakt [1], digəri [2].", 2)
    assert not metrics.citations_valid("İstinadsız cavab.", 2)
    assert not metrics.citations_valid("Uydurma [5].", 2)


def test_binary_scores():
    s = metrics.binary_scores([True, True, False, False], [True, False, True, False])
    assert (s["tp"], s["fp"], s["fn"], s["tn"]) == (1, 1, 1, 1)
    assert s["precision"] == 0.5 and s["recall"] == 0.5 and s["f1"] == 0.5
    assert metrics.binary_scores([False], [False])["precision"] is None


# ---- Offline hədlər (CI reqressiya qapısı) -----------------------------------

def test_offline_gates_hold():
    report = run_all()
    assert report["gates_broken"] == [], format_report(report)
    assert set(OFFLINE_GATES) == {"tutor.intent_accuracy", "tutor.retrieval_hit_at_1",
                                  "tutor.retrieval_hit_at_k", "review.rules_precision"}


def test_rules_cannot_check_facts():
    """Qaydalar faktı bilmir: səhv cavablı sualların əksəriyyətini qaçırır. Bu, AI
    komandasının niyə lazım olduğunun ölçüsüdür - qaydalar birdən «ağıllansa» dəst yoxlanmalıdır."""
    recall = run_all()["review_offline"]["recall_by_problem"]
    assert recall["giveaway"] == 1.0
    assert recall["wrong_answer"] < 0.5


def test_cli_check_exit_code(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert main(["--check", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["mode"] == "offline"
    assert "niyyət düzgünlüyü" in capsys.readouterr().out


# ---- Live axın (saxta model ilə: real açar CI-da yoxdur) ----------------------

def oracle(system, user):
    """Rolu sistem promptundan tanıyan saxta model."""
    if system.startswith("Sən AI tutorun cavablarını"):
        return '{"score": 4, "reason": "yaxşı"}'
    if system in (FACT_SYSTEM_PROMPT, PEDAGOGUE_SYSTEM_PROMPT):
        numbers = [int(n) for n in re.findall(r"^Sual (\d+):", user, re.MULTILINE)]
        return json.dumps([{"n": n, "ok": n % 2 == 1, "issue": "" if n % 2 else "səhv"} for n in numbers])
    if system == QUIZ_SYSTEM_PROMPT:
        return json.dumps({"question": "S?", "options": ["a", "b", "c", "d", "e"], "correct_index": 0,
                           "explanation": "[1]"})
    if "Redaktor" in system or system.startswith("Sən test redaktorusan"):
        return "{}"
    if "Kvant" in user or "Yaponiya" in user:
        return "MATERIALDA_YOXDUR"
    return "Cavab budur [1]."


@pytest.fixture(scope="module")
def live_report():
    return run_all(live=True, judge=True, completers={"fake": oracle}, order=["fake"])


def test_live_report_shape(live_report):
    tl, rl = live_report["tutor_live"], live_report["review_live"]
    assert live_report["providers"] == ["fake"]
    assert tl["errors"] == 0 and tl["cases"] == len(TUTOR)
    assert tl["citation_validity"] == 1.0
    assert tl["quiz_validity"] == 1.0
    assert tl["judge_faithfulness"] == 4
    assert 0 < tl["abstention_rate"] < 1  # yalnız iki «yoxdur» sualı saxta modeldə tanınır
    assert rl["cases"] == len(REVIEW) and rl["unchecked"] == 0
    assert rl["tp"] + rl["fp"] + rl["fn"] + rl["tn"] == len(REVIEW)
    text = format_report(live_report)
    assert "AI komandası" in text and "sadiqlik" in text


def test_live_tutor_error_is_recorded_not_raised():
    def broken(system, user):
        raise RuntimeError("provider düşdü")

    report = run_all(live=True, completers={"fake": broken}, order=["fake"])
    assert report["tutor_live"]["errors"] > 0  # offtopic halları LLM-siz keçir, qalanı xəta
    assert report["tutor_live"]["kind_accuracy"] < 1
    assert report["review_live"]["unchecked"] == len(REVIEW)
