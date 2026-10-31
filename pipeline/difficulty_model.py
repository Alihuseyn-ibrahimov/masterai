"""Sualın çətinliyini proqnozlaşdıran kiçik neyron şəbəkə - yalnız İNFERENS (gün 15).

Model PyTorch ilə öyrədilir (`ml/train_difficulty.py`, noutbukda və ya Colab-da),
çəkilər JSON-a yazılır və server onu bu faylda sadə Python ilə hesablayır.
Səbəb: torch ~800 MB-dır, 1 nüvəli serverə yalnız 14→16→1 ölçülü şəbəkənin
bir neçə vurmasını hesablamaq üçün onu quraşdırmağa dəyməz.

Çıxış: tələbələrin bu sualı DÜZGÜN cavablama ehtimalı (0-1). Səviyyə həddlərlə:
`p >= asan` → asan, `p < cetin` → çətin, arası orta.

JSON forması:
    {"features": [...], "mean": [...], "std": [...],
     "layers": [{"w": [[...], ...], "b": [...]}, ...],     # son qat 1 çıxışlı
     "thresholds": {"asan": 0.75, "cetin": 0.45},
     "trained_on": 120, "synthetic": false, "metrics": {...}}
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

from pipeline.difficulty_features import FEATURES, extract
from pipeline.models import MCQQuestion

DEFAULT_THRESHOLDS = {"asan": 0.75, "cetin": 0.45}


class ModelFileError(ValueError):
    pass


@dataclass
class DifficultyModel:
    mean: list[float]
    std: list[float]
    layers: list[dict]
    thresholds: dict = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    trained_on: int = 0
    synthetic: bool = False
    metrics: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "DifficultyModel":
        if data.get("features") != FEATURES:
            raise ModelFileError("Model başqa əlamət siyahısı ilə öyrədilib - yenidən öyrət")
        layers = data.get("layers") or []
        width = len(FEATURES)
        for layer in layers:
            if any(len(row) != width for row in layer["w"]) or len(layer["b"]) != len(layer["w"]):
                raise ModelFileError("Qat ölçüləri uyğun gəlmir")
            width = len(layer["w"])
        if not layers or width != 1 or len(data["mean"]) != len(FEATURES) or len(data["std"]) != len(FEATURES):
            raise ModelFileError("Model faylı natamamdır")
        return cls(mean=data["mean"], std=data["std"], layers=layers,
                   thresholds={**DEFAULT_THRESHOLDS, **(data.get("thresholds") or {})},
                   trained_on=int(data.get("trained_on", 0)), synthetic=bool(data.get("synthetic")),
                   metrics=data.get("metrics") or {})

    @classmethod
    def load(cls, path: str) -> "DifficultyModel":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def predict_features(self, features: list[float]) -> float:
        x = [(v - m) / (s or 1.0) for v, m, s in zip(features, self.mean, self.std)]
        for i, layer in enumerate(self.layers):
            x = [sum(w * v for w, v in zip(row, x)) + b for row, b in zip(layer["w"], layer["b"])]
            if i < len(self.layers) - 1:
                x = [max(0.0, v) for v in x]  # ReLU
        z = max(-30.0, min(30.0, x[0]))
        return 1.0 / (1.0 + math.exp(-z))

    def predict(self, question: MCQQuestion) -> float:
        return self.predict_features(extract(question))

    def level(self, p_correct: float) -> str:
        if p_correct >= self.thresholds["asan"]:
            return "asan"
        if p_correct < self.thresholds["cetin"]:
            return "çətin"
        return "orta"


_cache: dict[str, tuple[float, DifficultyModel | None]] = {}


def load_cached(path: str | None) -> DifficultyModel | None:
    """Fayl yoxdursa və ya pozuqdursa `None` (proqnoz göstərilmir, xəta yox).
    Fayl dəyişəndə (yeni model yüklənəndə) servisi restart etmək lazım deyil."""
    if not path or not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        model = DifficultyModel.load(path)
    except (OSError, ValueError, KeyError, TypeError):
        model = None
    _cache[path] = (mtime, model)
    return model
