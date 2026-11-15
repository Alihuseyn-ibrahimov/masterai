"""Kurs Kassası, addım 4: trend əlamətləri + PyTorch (MLP, GRU) müqayisəsi.

torch serverə qoyulmur və CI-da quraşdırılmır: bu testlər orada keçilir
(çətinlik modelinin eyni qaydası, `requirements-ml.txt`).
"""

from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("sklearn")

from ml.churn import dataset, deep, synth, train  # noqa: E402


@pytest.fixture(scope="module")
def world():
    tables = synth.generate(400, seed=5)
    return tables, dataset.build(tables, train.FIRST, train.LAST)


@pytest.fixture(scope="module")
def report(world):
    return deep.run(*world)


def test_all_approaches_are_compared(report):
    assert set(report["models"]) == {"rule_days_since_activity", "logreg_base", "logreg_engineered",
                                     "mlp_engineered", "gru_sequence"}
    assert "rule_only" in report["call_list"]


def test_neural_models_learn_something(report):
    for name in ("mlp_engineered", "gru_sequence"):
        assert report["models"][name]["roc_auc"] > 0.85, name


def test_same_extra_call_budget_for_every_model(report):
    budgets = {c["calls_per_month"] for k, c in report["call_list"].items() if k != "rule_only"}
    assert len(budgets) == 1


def test_training_is_reproducible(world):
    assert deep.run(*world)["models"]["gru_sequence"] == deep.run(*world)["models"]["gru_sequence"]


def test_cli(tmp_path, capsys):
    assert deep.main(["--students", "250", "--seed", "4", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "deep_report.json").exists()
    assert "gru_sequence" in capsys.readouterr().out
