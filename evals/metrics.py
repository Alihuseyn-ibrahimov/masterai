"""Qiymətləndirmə metrikaları - təmiz funksiyalar, LLM-siz sınanır."""

from __future__ import annotations

import re

from pipeline.rag import _lower

_CITATION = re.compile(r"\[(\d{1,2})\]")


def ratio(hits: int, total: int) -> float | None:
    """Hal yoxdursa `None`: «0 haldan 0» 100% və ya 0% deyil, ölçülməyib."""
    return round(hits / total, 3) if total else None


def hit_at_k(retrieved_keys: list[str], expected: list[str], k: int) -> bool:
    return any(key in expected for key in retrieved_keys[:k])


def reciprocal_rank(retrieved_keys: list[str], expected: list[str]) -> float:
    for rank, key in enumerate(retrieved_keys, start=1):
        if key in expected:
            return 1.0 / rank
    return 0.0


def keyword_recall(answer: str, keywords: list[str]) -> float | None:
    """Gözlənilən açar sözlərin neçəsi cavabda var (Azərbaycan kiçiltməsi ilə)."""
    if not keywords:
        return None
    text = _lower(answer)
    return round(sum(_lower(k) in text for k in keywords) / len(keywords), 3)


def citations_valid(answer: str, passage_count: int) -> bool:
    """Ən azı bir [n] istinadı var və hamısı verilmiş parçalara düşür."""
    numbers = [int(n) for n in _CITATION.findall(answer)]
    return bool(numbers) and all(1 <= n <= passage_count for n in numbers)


def binary_scores(predicted: list[bool], actual: list[bool]) -> dict:
    """«Problemli» sinfi üçün precision / recall / F1."""
    tp = sum(p and a for p, a in zip(predicted, actual))
    fp = sum(p and not a for p, a in zip(predicted, actual))
    fn = sum(a and not p for p, a in zip(predicted, actual))
    tn = sum(not p and not a for p, a in zip(predicted, actual))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and precision + recall else None)
    rnd = lambda v: round(v, 3) if v is not None else None  # noqa: E731
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": rnd(precision), "recall": rnd(recall), "f1": rnd(f1),
            "accuracy": ratio(tp + tn, len(actual))}


def mean(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None
