"""Kurs Kassası, addım 3: sklearn ilə öyrətmə, qayda ilə müqayisə, JSON ixracı.

sklearn yalnız öyrətmə üçündür (`requirements-ml.txt`, CI-da ayrıca quraşdırılır),
server onu quraşdırmır. Saf Python hesablaması: `test_churn_model.py`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ml.churn import dataset, model as churn_model, synth

UTC = timezone.utc

sklearn = pytest.importorskip("sklearn")
train = pytest.importorskip("ml.churn.train")


@pytest.fixture(scope="module")
def rows():
    return dataset.build(synth.generate(500, seed=11), train.FIRST, train.LAST)


@pytest.fixture(scope="module")
def result(rows):
    return train.run(rows)


def test_split_is_by_time(result):
    report, _ = result
    assert max(report["train_months"]) < min(report["test_months"])
    assert min(report["test_months"]) == train.TEST_FROM


def test_c_is_selected_on_train_months_only(rows):
    # Test aylarını tamamilə dəyişsək belə seçim eyni qalmalıdır.
    tr, te = dataset.time_split(rows, train.TEST_FROM)
    flipped = [{**r, "churned": 1 - r["churned"]} for r in te]
    assert train.select_c(tr) == train.select_c(dataset.time_split(tr + flipped, train.TEST_FROM)[0])


def test_logreg_ranks_well_on_synthetic(result):
    m = result[0]["models"]["logistic_regression"]
    assert m["roc_auc"] > 0.9
    assert m["pr_auc"] > 0.7
    assert m["active_roc_auc"] > 0.75


def test_report_includes_rule_and_other_models(result):
    assert set(result[0]["models"]) == {
        "rule_days_since_activity", "logistic_regression", "random_forest", "gradient_boosting"}


def test_call_list_extra_calls_find_more_churners(result):
    c = result[0]["call_list"]
    assert c["rule_plus_model"]["recall"] > c["rule_only"]["recall"]
    assert c["rule_plus_model"]["calls_per_month"] == c["rule_plus_days"]["calls_per_month"]
    assert c["rule_only"]["precision"] > 0.8


def test_days_since_activity_is_the_strongest_signal(result):
    # Addım 1-in gözləntisi: sadə qayda güclü bazadır. Model də eyni əlamətə söykənir.
    assert result[0]["logreg_weights"][0]["feature"] == "days_since_activity"
    assert result[0]["logreg_weights"][0]["weight"] > 0


def test_export_matches_sklearn_probabilities(rows, result):
    _, logreg = result
    exported = churn_model.validate(
        train.export_logreg(logreg, c=1.0, trained_on=["2025-10-01"], synthetic=True))
    sample = rows[::97]
    x, _, _ = train.matrix(sample)
    expected = logreg.predict_proba(x)[:, 1]
    for r, p in zip(sample, expected):
        assert churn_model.risk(exported, r) == pytest.approx(float(p), abs=1e-9)
    assert exported["synthetic"] is True


def test_cli_writes_report_and_model(tmp_path, capsys):
    assert train.main(["--students", "300", "--seed", "5", "--out", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "churn_report.json").read_text(encoding="utf-8"))
    assert report["data"]["source"] == "synthetic"
    churn_model.load(str(tmp_path / "churn_model.json"))
    out = capsys.readouterr().out
    assert "Zəng siyahısı" in out and "logistic_regression" in out


def test_snapshot_dates_still_monthly():
    # Train/test sərhədi ayın 1-i ilə eyni formatda olmalıdır (mətn müqayisəsi).
    dates = dataset.snapshot_dates(datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC))
    assert [d.isoformat()[:10] for d in dates] == ["2026-02-01", train.TEST_FROM]
