"""Kurs Kassası, addım 3: churn modeli (sklearn) və sadə qayda ilə müqayisə.

    python -m ml.churn.train --students 800 --seed 7 --out /tmp/kassa-model

Sual: hər ayın 1-də sahib kimə zəng etsin? İki yanaşma müqayisə olunur:

- **Qayda:** son fəaliyyətdən 14 gündən çox keçib (`days_since_activity > 14`).
  Addım 1-də gözlənildiyi kimi çox güclüdür: gedənlərin çoxu kəsikdən ƏVVƏL susur.
- **Model:** `LogisticRegression` (+ müqayisə üçün `RandomForest`,
  `HistGradientBoosting`). Dəyəri qaydanın heç nə demədiyi yerdədir: hələ aktiv
  (≤14 gün), amma sönən şagirdləri sıralamaq.

Ona görə əsas biznes metrikası «zəng siyahısı»dır: qaydanın tapdıqları + modelin
hələ aktiv şagirdlər arasında ən riskli 5%-i. Bu siyahı qaydanın tək özündən
neçə gedəni ƏLAVƏ tapır?

Leakage (spec §Leakage): bölgü VAXTA görədir, test ayları həmişə sonradır.
`C` parametri yalnız train ayları üzərində genişlənən pəncərə ilə seçilir
(test aylarına baxılmır). Əlamətlər `dataset.features`-dən gəlir (`cut` ilə).

Model JSON-a çıxarılır (`export_logreg`), serverdə `ml/churn/model.py` onu
sklearn-SİZ hesablayır (çətinlik modelinin eyni naxışı, `pipeline/difficulty_model.py`).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import dataset, synth

UTC = timezone.utc
FIRST = datetime(2025, 10, 1, tzinfo=UTC)
LAST = datetime(2026, 6, 1, tzinfo=UTC)
TEST_FROM = "2026-03-01"
RULE_DAYS = 14
TOP_SHARE = 0.10        # hər ay siyahının ölçüsü (modelin tək özü üçün)
EXTRA_SHARE = 0.05      # qaydaya əlavə: aktiv şagirdlərin ən riskli 5%-i
C_GRID = (0.01, 0.1, 1.0, 10.0)
CV_FOLDS = 3

DSA = dataset.FEATURES.index("days_since_activity")


def matrix(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.array([[float(r[k]) for k in dataset.FEATURES] for r in rows])
    y = np.array([int(r["churned"]) for r in rows])
    snaps = np.array([r["snapshot"] for r in rows])
    return x, y, snaps


def make_logreg(c: float = 1.0) -> Pipeline:
    # class_weight: gedənlər ~8%-dir, balanssız sinifdə model hamıya «qalır» deməsin.
    return Pipeline([
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(C=c, class_weight="balanced", max_iter=2000)),
    ])


def other_models() -> dict:
    return {
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=10, class_weight="balanced", random_state=0, n_jobs=1),
        "gradient_boosting": HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.05, max_iter=200, random_state=0),
    }


def select_c(train_rows: list[dict], grid=C_GRID, folds: int = CV_FOLDS) -> tuple[float, dict]:
    """Genişlənən pəncərə: train-in son `folds` ayının hər biri üçün ondan ƏVVƏLKİ
    aylarda öyrən, həmin ayda PR-AUC ölç. Test aylarına toxunulmur."""
    x, y, snaps = matrix(train_rows)
    months = sorted(set(snaps))
    scores: dict[float, list[float]] = {c: [] for c in grid}
    for month in months[-folds:]:
        fit, val = snaps < month, snaps == month
        if y[fit].sum() == 0 or y[val].sum() == 0:
            continue
        for c in grid:
            model = make_logreg(c).fit(x[fit], y[fit])
            scores[c].append(average_precision_score(y[val], model.predict_proba(x[val])[:, 1]))
    mean = {c: float(np.mean(v)) if v else 0.0 for c, v in scores.items()}
    best = max(grid, key=lambda c: (round(mean[c], 4), -c))  # bərabərdə daha sadə (kiçik C)
    return best, mean


def ranking_metrics(y: np.ndarray, score: np.ndarray, snaps: np.ndarray, dsa: np.ndarray) -> dict:
    """Ümumi sıralama + hər ay top-10% siyahı + yalnız HƏLƏ AKTİV şagirdlər arasında AUC."""
    precisions, caught = [], 0
    for month in np.unique(snaps):
        idx = np.where(snaps == month)[0]
        k = max(1, int(round(TOP_SHARE * len(idx))))
        top = idx[np.argsort(-score[idx], kind="stable")[:k]]
        precisions.append(float(y[top].mean()))
        caught += int(y[top].sum())
    active = dsa <= RULE_DAYS
    return {
        "roc_auc": round(float(roc_auc_score(y, score)), 4),
        "pr_auc": round(float(average_precision_score(y, score)), 4),
        "top10_precision": round(float(np.mean(precisions)), 4),
        "top10_recall": round(caught / max(int(y.sum()), 1), 4),
        "active_roc_auc": round(float(roc_auc_score(y[active], score[active])), 4)
        if 0 < y[active].sum() < active.sum() else None,
    }


def call_list(y: np.ndarray, proba: np.ndarray | None, snaps: np.ndarray, dsa: np.ndarray,
              extra_share: float = EXTRA_SHARE) -> dict:
    """Sahibin aylıq zəng siyahısı: qayda (>14 gün) + istəyə görə modelin aktivlər
    arasındakı ən riskli `extra_share` hissəsi."""
    flagged = dsa > RULE_DAYS
    if proba is not None:
        for month in np.unique(snaps):
            idx = np.where((snaps == month) & ~flagged)[0]
            k = int(round(extra_share * len(np.where(snaps == month)[0])))
            if k:
                flagged[idx[np.argsort(-proba[idx], kind="stable")[:k]]] = True
    tp = int((flagged & (y == 1)).sum())
    months = len(np.unique(snaps))
    return {
        "calls_per_month": round(int(flagged.sum()) / months, 1),
        "precision": round(tp / max(int(flagged.sum()), 1), 4),
        "recall": round(tp / max(int(y.sum()), 1), 4),
        "churners_found": tp,
        "churners_total": int(y.sum()),
    }


def export_logreg(model: Pipeline, *, c: float, trained_on: list[str], synthetic: bool) -> dict:
    scale, clf = model.named_steps["scale"], model.named_steps["clf"]
    return {
        "kind": "churn_logreg",
        "version": 1,
        "features": list(dataset.FEATURES),
        "mean": [float(v) for v in scale.mean_],
        "scale": [float(v) for v in scale.scale_],
        "coef": [float(v) for v in clf.coef_[0]],
        "intercept": float(clf.intercept_[0]),
        "C": c,
        "trained_on": trained_on,
        # Sintetik datada öyrədilmiş model real şagirdə HEÇ VAXT göstərilmir
        # (çətinlik modelinin eyni qaydası).
        "synthetic": synthetic,
    }


def run(rows: list[dict], test_from: str = TEST_FROM) -> tuple[dict, Pipeline]:
    train, test = dataset.time_split(rows, test_from)
    x_tr, y_tr, s_tr = matrix(train)
    x_te, y_te, s_te = matrix(test)
    dsa_te = x_te[:, DSA]

    best_c, cv = select_c(train)
    logreg = make_logreg(best_c).fit(x_tr, y_tr)
    proba = logreg.predict_proba(x_te)[:, 1]

    models = {"rule_days_since_activity": ranking_metrics(y_te, dsa_te, s_te, dsa_te),
              "logistic_regression": ranking_metrics(y_te, proba, s_te, dsa_te)}
    for name, model in other_models().items():
        p = model.fit(x_tr, y_tr).predict_proba(x_te)[:, 1]
        models[name] = ranking_metrics(y_te, p, s_te, dsa_te)

    clf = logreg.named_steps["clf"]
    weights = sorted(zip(dataset.FEATURES, clf.coef_[0]), key=lambda kv: -abs(kv[1]))
    report = {
        "rows": {"train": len(train), "test": len(test)},
        "churn_rate": {"train": round(float(y_tr.mean()), 4), "test": round(float(y_te.mean()), 4)},
        "train_months": sorted(set(s_tr.tolist())),
        "test_months": sorted(set(s_te.tolist())),
        "cv_pr_auc_by_C": {str(c): round(v, 4) for c, v in cv.items()},
        "best_C": best_c,
        "models": models,
        # Ədalətli müqayisə: eyni sayda əlavə zəngi model yox, sadəcə «ən çox
        # susan» aktivlər üzrə versək nə olar? Modelin dəyəri bu fərqdir.
        "call_list": {"rule_only": call_list(y_te, None, s_te, dsa_te),
                      "rule_plus_days": call_list(y_te, dsa_te, s_te, dsa_te),
                      "rule_plus_model": call_list(y_te, proba, s_te, dsa_te)},
        # Standartlaşdırılmış əmsallar: işarə və böyüklük müqayisə oluna bilir.
        "logreg_weights": [{"feature": k, "weight": round(float(v), 3)} for k, v in weights],
    }
    return report, logreg


def _print(report: dict) -> None:
    print(f"Train {report['rows']['train']} sətir ({report['train_months'][0]}..{report['train_months'][-1]}), "
          f"test {report['rows']['test']} sətir ({report['test_months'][0]}..{report['test_months'][-1]})")
    print(f"Seçilmiş C = {report['best_C']} (train daxili PR-AUC: {report['cv_pr_auc_by_C']})\n")
    print(f"{'model':28} {'ROC-AUC':>8} {'PR-AUC':>7} {'top10% dəqiq':>13} {'top10% tapdı':>13} {'aktivlərdə AUC':>15}")
    for name, m in report["models"].items():
        active = "-" if m["active_roc_auc"] is None else f"{m['active_roc_auc']:.3f}"
        print(f"{name:28} {m['roc_auc']:8.3f} {m['pr_auc']:7.3f} {m['top10_precision']:13.3f} "
              f"{m['top10_recall']:13.3f} {active:>15}")
    print("\nZəng siyahısı (test ayları):")
    for name, c in report["call_list"].items():
        print(f"  {name:16} ayda {c['calls_per_month']:5} zəng, dəqiqlik {c['precision']:.2f}, "
              f"gedənlərin {c['churners_found']}/{c['churners_total']} ({c['recall']:.0%})")
    print("\nLogReg əmsalları (standartlaşdırılmış):")
    for w in report["logreg_weights"]:
        print(f"  {w['feature']:24} {w['weight']:+.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Churn modeli: qayda vs sklearn")
    parser.add_argument("--students", type=int, default=800)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--test-from", default=TEST_FROM)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    rows = dataset.build(synth.generate(args.students, seed=args.seed), FIRST, LAST)
    report, logreg = run(rows, args.test_from)
    report["data"] = {"source": "synthetic", "students": args.students, "seed": args.seed}
    _print(report)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "churn_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    model = export_logreg(logreg, c=report["best_C"], trained_on=report["train_months"], synthetic=True)
    with open(os.path.join(args.out, "churn_model.json"), "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
