"""
GeoFlood AI - Phase 8: evaluation.

Loads the trained checkpoint and evaluates it on the val, test and bolivia
splits. Outputs go to ai/results/:
  metrics.json             all numbers
  threshold_sweep_val.csv  validation metrics at many thresholds
  per_country_test.csv     test metrics per country
  per_chip_results.csv     one row per chip
  test_examples.png        best / middle / worst test chips
  india_test_examples.png  India chips spread from best to worst
  bolivia_examples.png     Bolivia chips (unseen region)

The threshold is chosen on the VALIDATION set only.

Usage (from project root):  python -m ai.src.evaluate
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from matplotlib.colors import ListedColormap
from torch.utils.data import DataLoader

from ai.src import config
from ai.src.dataset import FloodDataset
from ai.src.metrics import ConfusionMeter
from ai.src.model import UNet

SEP = "=" * 70
SPLITS = ["val", "test", "bolivia"]
MIN_GAIN = 0.01          # a tuned threshold must beat 0.5 by this much (val IoU)
MIN_FLOOD_PCT = 1.0      # chips with less flood than this are skipped in example pictures


def parse_args():
    p = argparse.ArgumentParser(description="Evaluate the GeoFlood U-Net")
    p.add_argument("--checkpoint", default=str(config.MODELS_DIR / "unet_flood_best.pth"))
    p.add_argument("--out-dir", default=str(config.ROOT / "ai" / "results"))
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    return p.parse_args()


# ---------------------------------------------------------------- model / inference
def load_model(path, device):
    ckpt = torch.load(path, map_location=device)
    mc = ckpt["model_config"]
    model = UNet(mc["in_channels"], mc["base_channels"]).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    return model, ckpt


@torch.no_grad()
def predict_split(model, split, device):
    """Run the model on every chip of a split. Returns names, logits (float16), masks (uint8)."""
    ds = FloodDataset(split)
    loader = DataLoader(ds, batch_size=config.EVAL_BATCH_SIZE, shuffle=False, num_workers=0)
    logits, masks, names = [], [], []
    for images, m, n in loader:
        logits.append(model(images.to(device)).cpu().half())
        masks.append(m.to(torch.uint8))
        names.extend(n)
    return names, torch.cat(logits), torch.cat(masks)


# ---------------------------------------------------------------- metrics
def compute_metrics(logits, masks, threshold, idx=None):
    """Pooled metrics over all chips (or the chips listed in idx)."""
    if idx is not None:
        logits, masks = logits[idx], masks[idx]
    meter = ConfusionMeter(threshold=threshold)
    for i in range(0, len(masks), 10):
        meter.update(logits[i:i + 10].float(), masks[i:i + 10].long())
    r = meter.compute()
    r.update({"chips": len(masks), "tp": meter.tp, "fp": meter.fp, "fn": meter.fn, "tn": meter.tn})
    return r


def sweep_thresholds(logits, masks):
    rows = []
    for t in np.round(np.arange(0.10, 0.91, 0.05), 2):
        r = compute_metrics(logits, masks, float(t))
        rows.append({"threshold": float(t), "iou": r["iou"], "dice": r["dice"],
                     "precision": r["precision"], "recall": r["recall"]})
    return pd.DataFrame(rows)


def chip_table(names, logits, masks, thr):
    """Per-chip numbers, used for per-country scores, false alarms and picking pictures."""
    rows = []
    for i, name in enumerate(names):
        m = masks[i].long()
        valid = m != config.IGNORE_INDEX
        truth = (m == 1) & valid
        pred = (torch.sigmoid(logits[i, 0].float()) > thr) & valid
        tp = int((pred & truth).sum())
        fp = int((pred & ~truth).sum())
        fn = int((~pred & truth).sum())
        n_valid, flood, predicted = int(valid.sum()), int(truth.sum()), int(pred.sum())
        union = tp + fp + fn
        rows.append({
            "chip": name,
            "country": name.split("_")[0],
            "valid_px": n_valid,
            "flood_px": flood,
            "pred_px": predicted,
            "flood_pct": 100 * flood / n_valid if n_valid else float("nan"),
            "pred_pct": 100 * predicted / n_valid if n_valid else float("nan"),
            "iou": tp / union if union else float("nan"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- printing
def print_metrics_table(title, rows):
    print(f"\n{title}")
    print(f"  {'split':<9}{'chips':>6}{'IoU':>9}{'Dice':>9}{'Precision':>11}{'Recall':>9}{'F1':>9}")
    for label, r in rows:
        print(f"  {label:<9}{r['chips']:>6}{r['iou']:>9.4f}{r['dice']:>9.4f}"
              f"{r['precision']:>11.4f}{r['recall']:>9.4f}{r['f1']:>9.4f}")


# ---------------------------------------------------------------- pictures
def eligible_rows(df):
    d = df[(df.flood_pct >= MIN_FLOOD_PCT) & df.iou.notna()].sort_values("iou", ascending=False)
    return d.to_dict("records")


def mixed_selection(rows):
    """2 best, 2 middle and 2 worst chips by IoU."""
    if len(rows) <= 6:
        return rows
    mid = len(rows) // 2
    return rows[:2] + rows[mid - 1:mid + 1] + rows[-2:]


def spaced_selection(rows, n):
    """n chips evenly spread from best to worst IoU (no cherry-picking)."""
    if len(rows) <= n:
        return rows
    idx = np.linspace(0, len(rows) - 1, n).round().astype(int)
    return [rows[i] for i in idx]


def save_examples(split, names, logits, masks, rows, thr, path, title):
    if not rows:
        print(f"  (no suitable chips for {path.name}, skipped)")
        return
    ds = FloodDataset(split)
    cmap3 = ListedColormap(["white", "royalblue", "lightgray"])          # dry, flood, ignore
    cmap5 = ListedColormap(["white", "limegreen", "red", "orange", "lightgray"])
    fig, axes = plt.subplots(len(rows), 4, figsize=(15, 3.6 * len(rows)))
    axes = np.atleast_2d(axes)

    for r, row in enumerate(rows):
        i = names.index(row["chip"])           # same sorted order as the dataset
        img = ds[i][0]
        m = masks[i].long().numpy()
        pred = (torch.sigmoid(logits[i, 0].float()) > thr).numpy()
        valid = m != config.IGNORE_INDEX
        truth = m == 1

        gt_code = np.where(~valid, 2, truth.astype(int))
        pr_code = np.where(~valid, 2, pred.astype(int))
        err = np.zeros(m.shape, dtype=int)
        err[pred & truth & valid] = 1      # true positive
        err[pred & ~truth & valid] = 2     # false positive
        err[~pred & truth & valid] = 3     # missed flood
        err[~valid] = 4

        axes[r, 0].imshow(img[0], cmap="gray", vmin=0, vmax=1)
        axes[r, 1].imshow(gt_code, cmap=cmap3, vmin=0, vmax=2)
        axes[r, 2].imshow(pr_code, cmap=cmap3, vmin=0, vmax=2)
        axes[r, 3].imshow(err, cmap=cmap5, vmin=0, vmax=4)
        axes[r, 0].set_ylabel(f"{row['chip']}\nIoU {row['iou']:.2f}", fontsize=9)
        if r == 0:
            for c, t in enumerate(["Radar (VV band)", "Ground truth (blue = flood)",
                                   "Prediction (blue = flood)",
                                   "Errors: green=correct, red=false alarm, orange=missed"]):
                axes[r, c].set_title(t, fontsize=9)
        for c in range(4):
            axes[r, c].set_xticks([])
            axes[r, c].set_yticks([])

    fig.suptitle(title + "   (light gray = no-data, ignored)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    print(f"  Saved: {path}")


# ---------------------------------------------------------------- main
def main():
    args = parse_args()
    device = torch.device(args.device)
    ckpt_path = Path(args.checkpoint)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(SEP)
    print("  GeoFlood AI - Phase 8 Evaluation")
    print(SEP)

    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}\n"
                                "Put unet_flood_best.pth in ai/models/ (see Phase 7).")

    model, ckpt = load_model(ckpt_path, device)
    print(f"\nCheckpoint : {ckpt_path.name}  (saved at epoch {ckpt['epoch']})")
    if [list(r) for r in config.CLIP_RANGES] != ckpt["clip_ranges"]:
        print("  [WARN] normalisation ranges in config.py differ from those used in training!")

    print("\nRunning the model on val, test and bolivia (CPU: this can take a few minutes)...")
    preds = {}
    for s in SPLITS:
        preds[s] = predict_split(model, s, device)
        print(f"  {s:<8} done ({len(preds[s][0])} chips)")

    # 1. Sanity check: reproduce the validation IoU from the training log
    names, lg, mk = preds["val"]
    r = compute_metrics(lg, mk, ckpt["threshold"])
    expected = ckpt["val_metrics"]["iou"]
    status = "OK" if abs(r["iou"] - expected) < 0.005 else "WARN - does not match training log"
    print(f"\n--- Sanity check ---")
    print(f"  Validation IoU now: {r['iou']:.4f}   training log: {expected:.4f}   [{status}]")

    # 2. Threshold sweep on VALIDATION only
    sweep = sweep_thresholds(lg, mk)
    sweep.to_csv(out_dir / "threshold_sweep_val.csv", index=False)
    print("\n--- Threshold sweep (validation set only) ---")
    print(sweep.round(4).to_string(index=False))

    base_iou = float(sweep.loc[sweep.threshold == 0.5, "iou"].iloc[0])
    best_row = sweep.loc[sweep["iou"].idxmax()]
    gain = float(best_row["iou"]) - base_iou
    chosen = float(best_row["threshold"]) if gain >= MIN_GAIN else 0.5
    print(f"\n  Best validation threshold: {best_row['threshold']:.2f}  (gain over 0.5: {gain:+.4f})")
    print(f"  Recommended threshold    : {chosen:.2f}"
          + ("" if chosen != 0.5 else "   (gain below 0.01, so we keep the standard 0.5)"))

    # 3. Main metrics
    all_metrics = {}
    for thr in sorted({0.5, chosen}):
        rows = [(s, compute_metrics(preds[s][1], preds[s][2], thr)) for s in SPLITS]
        all_metrics[f"{thr:.2f}"] = {s: r for s, r in rows}
        tag = "  <- recommended" if thr == chosen else ""
        print_metrics_table(f"=== Metrics at threshold {thr:.2f}{tag} ===", rows)
    print("\n  Note: Dice and F1 are the same formula for binary pixels, so they are equal.")
    print("  Val was used to pick the epoch and threshold (optimistic). Test and Bolivia were not.")

    # 4. Per-chip tables, per-country scores, false alarms
    tables = {s: chip_table(*preds[s][:1], preds[s][1], preds[s][2], chosen) for s in SPLITS}
    all_chips = pd.concat([t.assign(split=s) for s, t in tables.items()])
    all_chips.to_csv(out_dir / "per_chip_results.csv", index=False)

    t_names, t_lg, t_mk = preds["test"]
    country_rows = []
    for country in sorted(set(n.split("_")[0] for n in t_names)):
        idx = [i for i, n in enumerate(t_names) if n.startswith(country + "_")]
        r = compute_metrics(t_lg, t_mk, chosen, idx)
        pct = tables["test"].loc[idx, "flood_pct"].mean()
        country_rows.append({"country": country, "chips": r["chips"], "mean_flood_pct": pct,
                             "iou": r["iou"], "dice": r["dice"],
                             "precision": r["precision"], "recall": r["recall"]})
    country_df = pd.DataFrame(country_rows)
    country_df.to_csv(out_dir / "per_country_test.csv", index=False)
    print(f"\n=== Test set per country (threshold {chosen:.2f}) ===")
    print(country_df.round(4).to_string(index=False))
    print("  (few chips per country: treat these as rough hints, not precise scores)")

    print("\n=== False alarms on chips with NO flood ===")
    false_alarms = {}
    for s in SPLITS:
        free = tables[s][tables[s].flood_px == 0]
        if free.empty:
            print(f"  {s:<8}: no flood-free chips")
            continue
        info = {"flood_free_chips": len(free),
                "chips_with_over_0.5pct_predicted_flood": int((free.pred_pct > 0.5).sum()),
                "mean_predicted_flood_pct": float(free.pred_pct.mean())}
        false_alarms[s] = info
        print(f"  {s:<8}: {info['flood_free_chips']} flood-free chips, "
              f"{info['chips_with_over_0.5pct_predicted_flood']} with >0.5% predicted flood, "
              f"mean predicted {info['mean_predicted_flood_pct']:.2f}%")

    # 5. Pictures
    print("\n=== Pictures ===")
    t_rows = eligible_rows(tables["test"])
    save_examples("test", t_names, t_lg, t_mk, mixed_selection(t_rows), chosen,
                  out_dir / "test_examples.png",
                  "Test set: 2 best, 2 middle, 2 worst chips by IoU")

    india = [r for r in t_rows if r["country"] == "India"]
    save_examples("test", t_names, t_lg, t_mk, spaced_selection(india, 4), chosen,
                  out_dir / "india_test_examples.png",
                  "India test chips spread from best to worst IoU")

    b_names, b_lg, b_mk = preds["bolivia"]
    b_rows = eligible_rows(tables["bolivia"])
    save_examples("bolivia", b_names, b_lg, b_mk, spaced_selection(b_rows, 4), chosen,
                  out_dir / "bolivia_examples.png",
                  "Bolivia (region never seen in training) spread from best to worst IoU")

    # 6. Save everything
    results = {
        "checkpoint": ckpt_path.name,
        "best_epoch": ckpt["epoch"],
        "recommended_threshold": chosen,
        "metrics": all_metrics,
        "per_country_test": country_df.to_dict("records"),
        "false_alarms": false_alarms,
        "threshold_sweep_val": sweep.to_dict("records"),
    }
    with open(out_dir / "metrics.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll results saved in: {out_dir}")
    print(SEP)


if __name__ == "__main__":
    main()
