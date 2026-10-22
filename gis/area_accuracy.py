"""
GeoFlood AI - area accuracy check on the India test chips.

Predicted and labelled water are compared ONLY on pixels where the label is valid
(label != -1) and the image is valid (mask != 255), so both cover the same ground.

Usage (project root):  python -m gis.area_accuracy
"""

import numpy as np
import pandas as pd
import rasterio

from ai.src import config
from gis.area_calculator import mask_area_km2

PRED_DIR = config.ROOT / "ai" / "results" / "predictions" / "test"
OUT = config.ROOT / "ai" / "results" / "area" / "area_accuracy_india_test.csv"


def main():
    rows = []
    for mp in sorted(PRED_DIR.glob("India_*_floodmask.tif")):
        chip = mp.name.replace("_S1Hand_floodmask.tif", "")
        with rasterio.open(mp) as src:
            mask, transform, crs = src.read(1), src.transform, src.crs
        with rasterio.open(config.LBL_DIR / f"{chip}_LabelHand.tif") as src:
            label = src.read(1)

        valid = (label != -1) & (mask != config.IGNORE_INDEX)
        pred = mask_area_km2((mask == 1) & valid, transform, crs)
        true = mask_area_km2((label == 1) & valid, transform, crs)
        rows.append({
            "chip": chip,
            "compared_area_km2": mask_area_km2(valid, transform, crs),
            "predicted_km2": pred,
            "label_km2": true,
            "error_km2": pred - true,
            "error_pct": 100 * (pred - true) / true if true > 0 else np.nan,
        })

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    print(f"\n  {'chip':<16}{'compared':>10}{'predicted':>11}{'label':>9}{'error':>9}{'error %':>9}")
    for r in rows:
        pct = "" if np.isnan(r["error_pct"]) else f"{r['error_pct']:.0f}"
        print(f"  {r['chip']:<16}{r['compared_area_km2']:>10.2f}{r['predicted_km2']:>11.3f}"
              f"{r['label_km2']:>9.3f}{r['error_km2']:>9.3f}{pct:>9}")

    big = df[df.label_km2 >= 1.0]
    print(f"\n  All 14 chips: predicted {df.predicted_km2.sum():.2f} km2 vs label {df.label_km2.sum():.2f} km2 "
          f"({100 * (df.predicted_km2.sum() / df.label_km2.sum() - 1):+.1f}%)")
    print(f"  Chips with at least 1 km2 of labelled water ({len(big)}): "
          f"mean absolute error {big.error_pct.abs().mean():.1f}%, "
          f"worst {big.error_pct.abs().max():.1f}%")
    print("  Small-water chips have large percentage errors because the denominator is tiny.")
    print(f"\n  Saved: {OUT}")


if __name__ == "__main__":
    main()
