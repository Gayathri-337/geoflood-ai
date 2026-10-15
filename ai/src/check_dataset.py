
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

# ai/src/check_dataset.py -> parents[2] is the project root
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ai" / "data" / "raw" / "sen1floods11"
IMG_DIR = DATA / "S1Hand"
LBL_DIR = DATA / "LabelHand"
SPLIT_DIR = DATA / "splits"

SEP = "=" * 62


def count_files():
    """Count .tif files in the image and label folders."""
    n_img = len(list(IMG_DIR.glob("*.tif")))
    n_lbl = len(list(LBL_DIR.glob("*.tif")))
    print(f"  Image files (S1Hand)    : {n_img}")
    print(f"  Label files (LabelHand) : {n_lbl}")
    return n_img, n_lbl


def check_splits():
    """Read each split CSV and verify the listed files exist on disk."""
    first_pair = None
    for name in ("train", "valid", "test"):
        csv_path = SPLIT_DIR / f"flood_{name}_data.csv"
        if not csv_path.exists():
            print(f"  [FAIL] Missing {csv_path.name}")
            continue

        # The CSVs may or may not have a header row, so read without one
        # and show the first row so we can see the real format.
        df = pd.read_csv(csv_path, header=None)
        missing = 0
        for img_name, lbl_name in zip(df[0], df[1]):
            if not (IMG_DIR / img_name).exists() or not (LBL_DIR / lbl_name).exists():
                missing += 1

        status = "OK  " if missing == 0 else "FAIL"
        print(f"  [{status}] {name:<6} rows={len(df):<4} missing files={missing}")
        print(f"          first row: {df.iloc[0, 0]}, {df.iloc[0, 1]}")

        if first_pair is None and len(df) > 0:
            first_pair = (df.iloc[0, 0], df.iloc[0, 1])
    return first_pair


def inspect_pair(img_name, lbl_name):
    """Open one image and its label, and describe them."""
    with rasterio.open(IMG_DIR / img_name) as src:
        img = src.read()
        print(f"  Image  : {img_name}")
        print(f"    bands={src.count}  size={src.width}x{src.height}  dtype={src.dtypes[0]}")
        print(f"    CRS={src.crs}")
        print(f"    bounds={tuple(round(b, 4) for b in src.bounds)}")
        for i in range(img.shape[0]):
            band = img[i]
            print(f"    band {i + 1}: min={np.nanmin(band):.2f} max={np.nanmax(band):.2f} "
                  f"mean={np.nanmean(band):.2f} NaNs={int(np.isnan(band).sum())}")

    with rasterio.open(LBL_DIR / lbl_name) as src:
        lbl = src.read(1)
        values, counts = np.unique(lbl, return_counts=True)
        print(f"  Label  : {lbl_name}")
        print(f"    size={src.width}x{src.height}  dtype={src.dtypes[0]}")
        for v, c in zip(values, counts):
            print(f"    value {v}: {c} pixels ({100 * c / lbl.size:.1f}%)")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 2 Dataset Check")
    print(SEP)

    if not DATA.exists():
        print(f"\n  [FAIL] Folder not found: {DATA}")
        print("         Re-run the download commands from Step 2.3.")
        return

    print("\n--- File counts ---")
    count_files()

    print("\n--- Split files ---")
    pair = check_splits()

    if pair:
        print("\n--- Sample inspection ---")
        inspect_pair(*pair)

    print("\n" + SEP)
    print("  Paste this whole output back to me.")
    print(SEP)


if __name__ == "__main__":
    main()

