"""Çətinlik modelini PyTorch ilə öyrədir və serverin oxuduğu JSON-a yazır (gün 15).

    pip install -r requirements-ml.txt                  # torch yalnız burada
    python -m ml.train_difficulty --csv cetinlik.csv --out difficulty_model.json
    python -m ml.train_difficulty --synthetic 600 --out /tmp/demo.json   # real data yoxdursa

Model: 14 əlamət → 16 neyron (ReLU) → 1 (sigmoid) = sualın düzgün cavablanma ehtimalı.
İtki: yumşaq hədəfli binary cross-entropy, hər sual CAVAB SAYI ilə çəkilir (40
cavablı sualın faizi 5 cavablıdan etibarlıdır). Validasiya itkisi 30 epoxa
yaxşılaşmasa öyrətmə dayanır və ən yaxşı çəkilər saxlanılır.

Hesabatda model iki bazaya qarşı müqayisə olunur: «hamısına orta faiz» (MAE) və
AI-nın öz səviyyəsi (səviyyə düzgünlüyü). Model bunları keçmirsə, onu serverə
qoymağın mənası yoxdur - skript bunu açıq yazır.
"""

from __future__ import annotations

import argparse
import json
import random
import sys

from ml.data import Row, read_csv, synthetic
from pipeline.difficulty_features import FEATURES
from pipeline.difficulty_model import DEFAULT_THRESHOLDS

HIDDEN = 16


def true_level(accuracy: float, thresholds=DEFAULT_THRESHOLDS) -> str:
    if accuracy >= thresholds["asan"]:
        return "asan"
    return "çətin" if accuracy < thresholds["cetin"] else "orta"


def split(rows: list[Row], val_share: float, seed: int) -> tuple[list[Row], list[Row]]:
    shuffled = rows[:]
    random.Random(seed).shuffle(shuffled)
    cut = max(1, int(len(shuffled) * (1 - val_share)))
    return shuffled[:cut], shuffled[cut:] or shuffled[:1]


def train(rows: list[Row], *, epochs: int = 600, patience: int = 30, lr: float = 0.01, seed: int = 0,
          val_share: float = 0.2, synthetic_data: bool = False) -> dict:
    import torch
    from torch import nn

    if len(rows) < 20:
        raise ValueError(f"Öyrətmək üçün ən azı 20 sual lazımdır, var: {len(rows)}")
    torch.manual_seed(seed)
    train_rows, val_rows = split(rows, val_share, seed)

    def tensors(part):
        x = torch.tensor([r.features for r in part], dtype=torch.float32)
        y = torch.tensor([[r.accuracy] for r in part], dtype=torch.float32)
        w = torch.tensor([[float(r.answers)] for r in part], dtype=torch.float32)
        return x, y, w

    x_tr, y_tr, w_tr = tensors(train_rows)
    x_va, y_va, w_va = tensors(val_rows)
    mean = x_tr.mean(dim=0)
    std = x_tr.std(dim=0).clamp(min=1e-6)
    norm = lambda x: (x - mean) / std  # noqa: E731

    model = nn.Sequential(nn.Linear(len(FEATURES), HIDDEN), nn.ReLU(), nn.Linear(HIDDEN, 1))
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-3)
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")

    def weighted_loss(x, y, w):
        return (loss_fn(model(norm(x)), y) * w).sum() / w.sum()

    best, best_state, stale, history = float("inf"), None, 0, []
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        loss = weighted_loss(x_tr, y_tr, w_tr)
        loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            val = weighted_loss(x_va, y_va, w_va).item()
        history.append((round(loss.item(), 4), round(val, 4)))
        if val < best - 1e-5:
            best, stale = val, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= patience:
                break
    model.load_state_dict(best_state)
    model.eval()

    with torch.no_grad():
        pred = torch.sigmoid(model(norm(x_va))).squeeze(1).tolist()
    actual = [r.accuracy for r in val_rows]
    weights = [r.answers for r in val_rows]
    train_mean = sum(r.accuracy * r.answers for r in train_rows) / sum(r.answers for r in train_rows)

    def wmae(values):
        return sum(abs(p - a) * w for p, a, w in zip(values, actual, weights)) / sum(weights)

    levels = [true_level(a) for a in actual]
    ai_levels = [r.ai_level or "orta" for r in val_rows]
    metrics = {
        "train_size": len(train_rows), "val_size": len(val_rows), "epochs": len(history),
        "val_loss": round(best, 4),
        "mae": round(wmae(pred), 4),
        "baseline_mae_mean": round(wmae([train_mean] * len(actual)), 4),
        "level_accuracy": round(sum(true_level(p) == t for p, t in zip(pred, levels)) / len(levels), 3),
        "baseline_level_accuracy_ai": round(sum(a == t for a, t in zip(ai_levels, levels)) / len(levels), 3),
    }
    metrics["beats_baselines"] = (metrics["mae"] < metrics["baseline_mae_mean"]
                                  and metrics["level_accuracy"] >= metrics["baseline_level_accuracy_ai"])

    linear1, linear2 = model[0], model[2]
    return {
        "features": FEATURES,
        "mean": mean.tolist(), "std": std.tolist(),
        "layers": [{"w": linear1.weight.tolist(), "b": linear1.bias.tolist()},
                   {"w": linear2.weight.tolist(), "b": linear2.bias.tolist()}],
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "trained_on": len(rows), "synthetic": synthetic_data, "metrics": metrics,
        "history": history[-5:],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sual çətinliyi modeli (PyTorch)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", help="deploy/export_difficulty_data.py-nin çıxardığı CSV")
    source.add_argument("--synthetic", type=int, help="N suallıq sintetik demo dəsti")
    parser.add_argument("--out", required=True, help="model JSON faylı")
    parser.add_argument("--epochs", type=int, default=600)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    rows = read_csv(args.csv) if args.csv else synthetic(args.synthetic, seed=args.seed)
    model = train(rows, epochs=args.epochs, seed=args.seed, synthetic_data=args.csv is None)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(model, fh, ensure_ascii=False)
    m = model["metrics"]
    print(f"Öyrədildi: {m['train_size']} sual, yoxlama {m['val_size']}, {m['epochs']} epoxa")
    print(f"MAE (düzgün faiz xətası): {m['mae']:.3f}  ·  baza «orta faiz»: {m['baseline_mae_mean']:.3f}")
    print(f"Səviyyə düzgünlüyü: {m['level_accuracy']:.0%}  ·  baza «AI-nın səviyyəsi»: "
          f"{m['baseline_level_accuracy_ai']:.0%}")
    if model["synthetic"]:
        print("DİQQƏT: sintetik dəst - bu model serverdə göstərilmir.")
    elif not m["beats_baselines"]:
        print("DİQQƏT: model bazaları keçmir - serverə qoyma, daha çox cavab yığ.")
    print(f"Model: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
