from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save to file, no window needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import ListedColormap

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ai" / "data" / "raw" / "sen1floods11"
IMG_DIR = DATA / "S1Hand"
LBL_DIR = DATA / "LabelHand"
SPLIT_DIR = DATA / "splits"
OUT_DIR = ROOT / "ai" / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEP = "=" * 66


def load_chip(chip_id):
    """Return (image [2,H,W] float32, label [H,W] int16, bounds) for one chip."""
    with rasterio.open(IMG_DIR / f"{chip_id}_S1Hand.tif") as src:
        img = src.read().astype("float32")
        bounds = src.bounds
    with rasterio.open(LBL_DIR / f"{chip_id}_LabelHand.tif") as src:
        lbl = src.read(1)
    return img, lbl, bounds


def collect_stats():
    """Loop over every chip and collect per-chip numbers."""
    rows = []
    band_samples = [[], []]  # subsampled valid pixels for percentile estimates

    chip_ids = sorted(p.name.replace("_S1Hand.tif", "") for p in IMG_DIR.glob("*_S1Hand.tif"))
    for cid in chip_ids:
        img, lbl, bounds = load_chip(cid)

        finite = np.isfinite(img).all(axis=0)
        valid = (lbl != -1) & finite
        n_valid = int(valid.sum())
        n_flood = int(((lbl == 1) & valid).sum())

        rows.append({
            "chip": cid,
            "country": cid.split("_")[0],
            "flood_pct": 100 * n_flood / n_valid if n_valid else np.nan,
            "nodata_pct": 100 * (lbl == -1).mean(),
            "nan_pixels": int((~finite).sum()),
            "lon_center": (bounds.left + bounds.right) / 2,
            "lat_center": (bounds.bottom + bounds.top) / 2,
        })

        # Every 16th valid pixel is enough for percentile estimates
        idx = np.flatnonzero(valid.ravel())[::16]
        for b in range(2):
            band_samples[b].append(img[b].ravel()[idx])

    return pd.DataFrame(rows), [np.concatenate(s) for s in band_samples]


def add_splits(df):
    """Label each chip as train / valid / test / unassigned."""
    chip_to_split = {}
    for name in ("train", "valid", "test"):
        csv = pd.read_csv(SPLIT_DIR / f"flood_{name}_data.csv", header=None)
        for img_name in csv[0]:
            chip_to_split[img_name.replace("_S1Hand.tif", "")] = name
    df["split"] = df["chip"].map(chip_to_split).fillna("unassigned")
    return df


def print_report(df, band_values):
    print(f"\nTotal chips: {len(df)}")

    print("\n--- Chips per country and split ---")
    print(pd.crosstab(df["country"], df["split"], margins=True).to_string())

    print("\n--- Per-country flood statistics ---")
    summary = df.groupby("country").agg(
        chips=("chip", "count"),
        mean_flood_pct=("flood_pct", "mean"),
        zero_flood_chips=("flood_pct", lambda s: int((s == 0).sum())),
        lat=("lat_center", "mean"),
        lon=("lon_center", "mean"),
    ).round(2)
    print(summary.to_string())

    print("\n--- Overall ---")
    print(f"  Mean flood pixels per chip : {df['flood_pct'].mean():.2f}%")
    print(f"  Median flood pixels        : {df['flood_pct'].median():.2f}%")
    print(f"  Chips with NO flood at all : {int((df['flood_pct'] == 0).sum())}")
    print(f"  Chips containing no-data   : {int((df['nodata_pct'] > 0).sum())}")
    print(f"  Chips containing NaNs      : {int((df['nan_pixels'] > 0).sum())}")

    print("\n--- SAR band value ranges (dB, valid pixels only) ---")
    for i, vals in enumerate(band_values, start=1):
        p = np.percentile(vals, [0.5, 50, 99.5])
        print(f"  Band {i}: min={vals.min():.1f}  0.5%={p[0]:.1f}  "
              f"median={p[1]:.1f}  99.5%={p[2]:.1f}  max={vals.max():.1f}")


def save_gallery(df):
    """One example chip per country: the one with the most flood."""
    best = df.loc[df.groupby("country")["flood_pct"].idxmax()].reset_index(drop=True)
    n = len(best)
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
    axes = np.atleast_1d(axes).ravel()

    flood_cmap = ListedColormap(["red"])
    nodata_cmap = ListedColormap(["cyan"])

    for ax, (_, r) in zip(axes, best.iterrows()):
        img, lbl, _ = load_chip(r["chip"])
        band = img[0]
        lo, hi = np.nanpercentile(band, [2, 98])
        ax.imshow(band, cmap="gray", vmin=lo, vmax=hi)
        ax.imshow(np.ma.masked_where(lbl != 1, np.ones_like(lbl)),
                  cmap=flood_cmap, alpha=0.6, vmin=0, vmax=1)
        ax.imshow(np.ma.masked_where(lbl != -1, np.ones_like(lbl)),
                  cmap=nodata_cmap, alpha=0.5, vmin=0, vmax=1)
        ax.set_title(f"{r['country']}  flood={r['flood_pct']:.1f}%", fontsize=10)
        ax.axis("off")

    for ax in axes[n:]:
        ax.axis("off")

    fig.suptitle("Most-flooded chip per country (red = flood, cyan = no data)")
    fig.tight_layout()
    out = OUT_DIR / "explore_gallery.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\nSaved gallery: {out}")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 3 Dataset Exploration")
    print(SEP)

    df, band_values = collect_stats()
    df = add_splits(df)
    print_report(df, band_values)

    csv_out = OUT_DIR / "chip_stats.csv"
    df.to_csv(csv_out, index=False)
    print(f"Saved per-chip table: {csv_out}")

    save_gallery(df)
    print(SEP)


if __name__ == "__main__":
    main()
