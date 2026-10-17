"""
GeoFlood AI - Phase 10: generate water/flood masks for many chips.

For every chip in a split (optionally only one country) this saves, under
<out-dir>/<split>/ :
  <chip>_floodmask.tif   0 = not water, 1 = water, 255 = no data (georeferenced)
  <chip>_floodprob.tif   water probability (georeferenced)
  overlays/<chip>.png    radar | prediction | ground truth, with lon/lat axes
  summary.csv            one row per chip
  chip_locations.png     where the chips are, coloured by predicted water %

NOTE: the model detects surface WATER (rivers included), not flood-only water.

Examples (from project root):
  python -m ai.src.generate_masks --split test --country India
  python -m ai.src.generate_masks --split bolivia
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

from ai.src import config
from ai.src.predict import FloodPredictor

SEP = "=" * 66


def parse_args():
    p = argparse.ArgumentParser(description="Generate masks for a split of the dataset")
    p.add_argument("--split", default="test", choices=list(config.SPLIT_FILES))
    p.add_argument("--country", default=None, help="only chips starting with this name, e.g. India")
    p.add_argument("--limit", type=int, default=0, help="process at most this many chips (0 = all)")
    p.add_argument("--out-dir", default=str(config.ROOT / "ai" / "results" / "predictions"))
    return p.parse_args()


def iou_vs_label(mask, label):
    """mask: 0/1/255 from the predictor; label: raw -1/0/1. NaN if the label has no water."""
    valid = (label != -1) & (mask != config.IGNORE_INDEX)
    tp = int(((mask == 1) & (label == 1) & valid).sum())
    fp = int(((mask == 1) & (label != 1) & valid).sum())
    fn = int(((mask != 1) & (label == 1) & valid).sum())
    union = tp + fp + fn
    return tp / union if union else float("nan")


def save_overlay(path, chip, radar_db, mask, label, bounds, iou):
    """Three panels placed in real lon/lat coordinates."""
    extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
    band = radar_db[0]
    lo, hi = np.nanpercentile(band, [2, 98])

    pred_water = np.ma.masked_where(mask != 1, np.ones(mask.shape))
    true_water = np.ma.masked_where(label != 1, np.ones(label.shape))

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2), sharex=True, sharey=True)
    titles = ["Radar (VV band, dB)", "Predicted water (blue)", "Ground truth water (blue)"]
    for ax, title in zip(axes, titles):
        ax.imshow(band, cmap="gray", vmin=lo, vmax=hi, extent=extent)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Longitude")
    axes[0].set_ylabel("Latitude")
    axes[1].imshow(pred_water, cmap="winter_r", alpha=0.65, extent=extent, vmin=0, vmax=1)
    axes[2].imshow(true_water, cmap="winter_r", alpha=0.65, extent=extent, vmin=0, vmax=1)

    iou_text = f"IoU vs label: {iou:.2f}" if not np.isnan(iou) else "no water in label"
    fig.suptitle(f"{chip}   |   {iou_text}", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)


def save_location_map(df, path, title):
    fig, ax = plt.subplots(figsize=(7, 6))
    sc = ax.scatter(df.lon, df.lat, c=df.water_pct, cmap="Blues", edgecolor="k", s=140, vmin=0, vmax=100)
    for _, r in df.iterrows():
        ax.annotate(r.chip.split("_")[1], (r.lon, r.lat), fontsize=6, xytext=(4, 4),
                    textcoords="offset points")
    fig.colorbar(sc, label="Predicted water (% of valid pixels)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    args = parse_args()
    out = Path(args.out_dir) / args.split
    (out / "overlays").mkdir(parents=True, exist_ok=True)

    print(SEP)
    print(f"  GeoFlood AI - Phase 10 Mask Generation  ({args.split}"
          + (f", {args.country}" if args.country else "") + ")")
    print(SEP)

    pairs = pd.read_csv(config.SPLIT_DIR / config.SPLIT_FILES[args.split], header=None)
    if args.country:
        pairs = pairs[pairs[0].str.startswith(args.country + "_")]
    if args.limit:
        pairs = pairs.head(args.limit)
    if pairs.empty:
        raise SystemExit("No chips matched. Check --split and --country (e.g. India, Ghana).")

    predictor = FloodPredictor()
    print(f"\nModel {predictor.checkpoint_name} on {predictor.device}; {len(pairs)} chips\n")

    rows = []
    for k, (img_name, lbl_name) in enumerate(zip(pairs[0], pairs[1]), start=1):
        chip = img_name.replace("_S1Hand.tif", "")
        tif = config.IMG_DIR / img_name
        res = predictor.predict_file(tif, out_dir=out)

        with rasterio.open(tif) as src:
            radar = src.read().astype("float32")
            bounds = src.bounds
        with rasterio.open(config.LBL_DIR / lbl_name) as src:
            label = src.read(1)

        iou = iou_vs_label(res.mask, label)
        save_overlay(out / "overlays" / f"{chip}.png", chip, radar, res.mask, label, bounds, iou)

        label_valid = label != -1
        rows.append({
            "chip": chip,
            "lon": (bounds.left + bounds.right) / 2,
            "lat": (bounds.bottom + bounds.top) / 2,
            "water_pct": res.stats["flood_pct_of_valid"],
            "label_water_pct": round(100 * (label == 1).sum() / max(label_valid.sum(), 1), 3),
            "mean_confidence": res.stats["mean_flood_confidence"],
            "iou_vs_label": round(iou, 4) if not np.isnan(iou) else np.nan,
            "warnings": "; ".join(res.stats["warnings"]),
        })
        print(f"  [{k:>3}/{len(pairs)}] {chip:<22} predicted water {res.stats['flood_pct_of_valid']:>6.2f}%"
              f"   label {rows[-1]['label_water_pct']:>6.2f}%   IoU {rows[-1]['iou_vs_label']}")

    df = pd.DataFrame(rows)
    df.to_csv(out / "summary.csv", index=False)
    save_location_map(df, out / "chip_locations.png",
                      f"{args.split} chips" + (f" ({args.country})" if args.country else ""))

    print("\n--- Summary ---")
    print(f"  Chips processed          : {len(df)}")
    print(f"  Mean predicted water     : {df.water_pct.mean():.2f}%")
    print(f"  Mean ground-truth water  : {df.label_water_pct.mean():.2f}%")
    print(f"  Mean IoU over chips      : {df.iou_vs_label.mean():.4f}  (average of per-chip IoU, "
          "differs from the pooled IoU in Phase 8)")
    if args.split == "train":
        print("  [NOTE] the model trained on these chips: IoU here is optimistic, don't report it.")
    print(f"\nSaved in: {out}")
    print(SEP)


if __name__ == "__main__":
    main()
