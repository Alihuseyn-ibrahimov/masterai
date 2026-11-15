"""Addım 4: feature engineering (#44) + PyTorch (5-ci ay #34) müqayisəsi.

    python -m ml.churn.deep --students 800 --seed 7 --out /tmp/kassa-deep

Eyni vaxta görə bölgüdə (train 2025-10..2026-02, test 2026-03..06) beş yanaşma:

1. Qayda: «neçə gündür susub» (addım 3-ün ən güclü bazası);
2. LogReg, 9 əsas əlamət (addım 3);
3. LogReg, + 11 trend əlaməti (`dataset.ENGINEERED`);
4. MLP (PyTorch), eyni 20 əlamət;
5. GRU (PyTorch): son 6 ayın xam aylıq sırası + 9 əsas əlamət.

PyTorch modellərində erkən dayanma TRAIN-in son ayı üzərindədir (test aylarına
baxılmır); seed sabitdir, CPU-da nəticə təkrarlanır. torch serverə QOYULMUR
(`requirements-ml.txt`), CI bu testləri keçir (çətinlik modelinin eyni qaydası).
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
import torch
from torch import nn

from . import dataset, sequence, synth, train

HIDDEN = 16
EPOCHS = 60
PATIENCE = 8
LR = 0.01


def _matrix(rows: list[dict], features: list[str]) -> np.ndarray:
    return np.array([[float(r[k]) for k in features] for r in rows], dtype=np.float32)


class _Standard:
    def __init__(self, x: np.ndarray) -> None:
        self.mean = x.mean(axis=0)
        self.std = x.std(axis=0)
        self.std[self.std == 0] = 1.0

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean) / self.std).astype(np.float32)


class MLP(nn.Module):
    def __init__(self, n_in: int) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_in, 32), nn.ReLU(), nn.Dropout(0.1),
                                 nn.Linear(32, HIDDEN), nn.ReLU(), nn.Linear(HIDDEN, 1))

    def forward(self, x: torch.Tensor, seq: torch.Tensor | None = None) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class GRUModel(nn.Module):
    """Aylıq sıra GRU-dan keçir, son gizli vəziyyət cədvəl əlamətləri ilə birləşir."""

    def __init__(self, n_static: int, n_step: int) -> None:
        super().__init__()
        self.gru = nn.GRU(n_step, HIDDEN, batch_first=True)
        self.head = nn.Sequential(nn.Linear(HIDDEN + n_static, HIDDEN), nn.ReLU(), nn.Linear(HIDDEN, 1))

    def forward(self, x: torch.Tensor, seq: torch.Tensor | None = None) -> torch.Tensor:
        _, h = self.gru(seq)
        return self.head(torch.cat([h[-1], x], dim=1)).squeeze(-1)


def fit(model: nn.Module, x: np.ndarray, y: np.ndarray, snaps: np.ndarray,
        seq: np.ndarray | None = None, seed: int = 0) -> nn.Module:
    """Train-in son ayı validasiyadır (erkən dayanma), sonra ən yaxşı çəkilər qaytarılır."""
    torch.manual_seed(seed)
    val = snaps == max(snaps.tolist())
    fit_idx, val_idx = np.where(~val)[0], np.where(val)[0]
    pos = max(float(y[fit_idx].sum()), 1.0)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor((len(fit_idx) - pos) / pos))
    opt = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-4)
    tx, ty = torch.from_numpy(x), torch.from_numpy(y.astype(np.float32))
    ts = torch.from_numpy(seq) if seq is not None else None
    gen = torch.Generator().manual_seed(seed)
    best, best_state, waited = float("inf"), None, 0
    for _ in range(EPOCHS):
        model.train()
        order = torch.from_numpy(fit_idx)[torch.randperm(len(fit_idx), generator=gen)]
        for batch in order.split(128):
            opt.zero_grad()
            out = model(tx[batch], ts[batch] if ts is not None else None)
            loss_fn(out, ty[batch]).backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            vi = torch.from_numpy(val_idx)
            v = loss_fn(model(tx[vi], ts[vi] if ts is not None else None), ty[vi]).item()
        if v < best - 1e-4:
            best, waited = v, 0
            best_state = {k: t.clone() for k, t in model.state_dict().items()}
        else:
            waited += 1
            if waited >= PATIENCE:
                break
    model.load_state_dict(best_state)
    return model


def predict(model: nn.Module, x: np.ndarray, seq: np.ndarray | None = None) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        out = model(torch.from_numpy(x), torch.from_numpy(seq) if seq is not None else None)
    return torch.sigmoid(out).numpy()


def run(tables, rows: list[dict], test_from: str = train.TEST_FROM, seed: int = 0) -> dict:
    torch.set_num_threads(1)
    seqs = np.array(sequence.build_sequences(tables, rows), dtype=np.float32)
    snaps_all = np.array([r["snapshot"] for r in rows])
    tr_mask = snaps_all < test_from
    tr = [r for r, m in zip(rows, tr_mask) if m]
    te = [r for r, m in zip(rows, tr_mask) if not m]
    y_tr = np.array([r["churned"] for r in tr])
    y_te = np.array([r["churned"] for r in te])
    s_tr, s_te = snaps_all[tr_mask], snaps_all[~tr_mask]
    dsa = np.array([r["days_since_activity"] for r in te], dtype=float)

    scores: dict[str, np.ndarray] = {"rule_days_since_activity": dsa}
    for name, feats in (("logreg_base", dataset.FEATURES), ("logreg_engineered", dataset.FEATURES_V2)):
        x_tr, x_te = _matrix(tr, feats), _matrix(te, feats)
        c, _ = train.select_c(tr, features=feats)
        scores[name] = train.make_logreg(c).fit(x_tr, y_tr).predict_proba(x_te)[:, 1]

    std2 = _Standard(_matrix(tr, dataset.FEATURES_V2))
    mlp = fit(MLP(len(dataset.FEATURES_V2)), std2(_matrix(tr, dataset.FEATURES_V2)), y_tr, s_tr, seed=seed)
    scores["mlp_engineered"] = predict(mlp, std2(_matrix(te, dataset.FEATURES_V2)))

    std1 = _Standard(_matrix(tr, dataset.FEATURES))
    gru = fit(GRUModel(len(dataset.FEATURES), len(sequence.STEP_FEATURES)),
              std1(_matrix(tr, dataset.FEATURES)), y_tr, s_tr, seq=seqs[tr_mask], seed=seed)
    scores["gru_sequence"] = predict(gru, std1(_matrix(te, dataset.FEATURES)), seqs[~tr_mask])

    report = {"rows": {"train": len(tr), "test": len(te)}, "models": {}, "call_list": {}}
    for name, score in scores.items():
        report["models"][name] = train.ranking_metrics(y_te, score, s_te, dsa)
        report["call_list"][name] = train.call_list(y_te, score if name != "rule_days_since_activity" else dsa,
                                                    s_te, dsa)
    report["call_list"]["rule_only"] = train.call_list(y_te, None, s_te, dsa)
    return report


def _print(report: dict) -> None:
    print(f"Train {report['rows']['train']} sətir, test {report['rows']['test']} sətir\n")
    print(f"{'model':26} {'ROC-AUC':>8} {'PR-AUC':>7} {'aktivlərdə AUC':>15} {'zəng siyahısı tapdı':>20}")
    for name, m in report["models"].items():
        c = report["call_list"][name]
        print(f"{name:26} {m['roc_auc']:8.3f} {m['pr_auc']:7.3f} {m['active_roc_auc']:15.3f} "
              f"{c['churners_found']:>9}/{c['churners_total']} ({c['recall']:.0%})")
    r = report["call_list"]["rule_only"]
    print(f"\nYalnız qayda: ayda {r['calls_per_month']} zəng, {r['churners_found']}/{r['churners_total']}; "
          f"digərləri ayda {report['call_list']['gru_sequence']['calls_per_month']} zəng.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Churn: feature engineering + PyTorch müqayisəsi")
    parser.add_argument("--students", type=int, default=800)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    tables = synth.generate(args.students, seed=args.seed)
    rows = dataset.build(tables, train.FIRST, train.LAST)
    report = run(tables, rows)
    report["data"] = {"source": "synthetic", "students": args.students, "seed": args.seed}
    _print(report)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "deep_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
