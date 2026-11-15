"""Churn modelinin sklearn-SİZ hesablanması (server üçün).

`ml/churn/train.py` LogisticRegression-u JSON-a çıxarır: hər əlamətin orta
qiyməti, miqyası, əmsalı və sərbəst hədd. Burada eyni hesab saf Python ilə
təkrarlanır: `p = 1 / (1 + exp(-(b + Σ w_i * (x_i - mean_i) / scale_i)))`.
Server sklearn/numpy quraşdırmır (VPS diski kiçikdir, bax CLAUDE.md).
"""

from __future__ import annotations

import json
import math

from .dataset import FEATURES


class ModelError(ValueError):
    pass


def validate(model: dict) -> dict:
    if model.get("kind") != "churn_logreg":
        raise ModelError("churn modeli deyil")
    if model.get("features") != FEATURES:
        # Əlamət sırası dəyişibsə köhnə əmsallar səhv əlamətə vurular: səssiz səhv olmasın.
        raise ModelError("əlamət siyahısı bu kodla uyğun gəlmir")
    n = len(FEATURES)
    if not all(len(model.get(k, [])) == n for k in ("mean", "scale", "coef")):
        raise ModelError("əmsal sayı səhvdir")
    if any(s <= 0 for s in model["scale"]):
        raise ModelError("miqyas müsbət olmalıdır")
    return model


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return validate(json.load(f))


def risk(model: dict, features: dict) -> float:
    """0..1: bu şagirdin növbəti 30 gündə getmə ehtimalı (modelin fikrincə)."""
    z = model["intercept"]
    for name, mean, scale, coef in zip(FEATURES, model["mean"], model["scale"], model["coef"]):
        z += coef * (float(features[name]) - mean) / scale
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)  # böyük mənfi z-də daşmasın
    return e / (1.0 + e)
