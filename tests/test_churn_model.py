"""Kurs Kassası, addım 3: churn modelinin sklearn-SİZ hesablanması (`ml/churn/model.py`).

Öyrətmə testləri: `test_churn_train.py`.
"""

from __future__ import annotations

import json
import math

import pytest

from ml.churn import dataset, model as churn_model


def _toy_model(**extra) -> dict:
    n = len(dataset.FEATURES)
    m = {
        "kind": "churn_logreg", "version": 1, "features": list(dataset.FEATURES),
        "mean": [0.0] * n, "scale": [1.0] * n, "coef": [0.0] * n, "intercept": 0.0,
        "synthetic": True,
    }
    m.update(extra)
    return m


def _features(**values) -> dict:
    f = {k: 0.0 for k in dataset.FEATURES}
    f.update(values)
    return f


# ---------- saf Python hesablama (sklearn lazım deyil) ----------

def test_zero_model_gives_half():
    assert churn_model.risk(_toy_model(), _features()) == 0.5


def test_risk_follows_logistic_formula():
    i = dataset.FEATURES.index("days_since_activity")
    coef = [0.0] * len(dataset.FEATURES)
    coef[i] = 2.0
    mean = [0.0] * len(dataset.FEATURES)
    mean[i] = 5.0
    scale = [1.0] * len(dataset.FEATURES)
    scale[i] = 10.0
    m = _toy_model(coef=coef, mean=mean, scale=scale, intercept=-1.0)
    z = -1.0 + 2.0 * (25 - 5) / 10
    assert churn_model.risk(m, _features(days_since_activity=25)) == pytest.approx(1 / (1 + math.exp(-z)))


def test_risk_does_not_overflow():
    i = dataset.FEATURES.index("days_since_activity")
    coef = [0.0] * len(dataset.FEATURES)
    coef[i] = 1000.0
    m = _toy_model(coef=coef)
    assert churn_model.risk(m, _features(days_since_activity=-5)) == pytest.approx(0.0, abs=1e-300)
    assert churn_model.risk(m, _features(days_since_activity=5)) == 1.0


@pytest.mark.parametrize("broken", [
    {"kind": "difficulty"},
    {"features": list(reversed(dataset.FEATURES))},
    {"coef": [0.0]},
    {"scale": [0.0] * len(dataset.FEATURES)},
])
def test_validate_rejects_mismatched_models(broken):
    with pytest.raises(churn_model.ModelError):
        churn_model.validate(_toy_model(**broken))


def test_load_roundtrip(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(_toy_model()), encoding="utf-8")
    assert churn_model.load(str(path))["kind"] == "churn_logreg"
