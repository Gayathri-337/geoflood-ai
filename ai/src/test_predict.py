"""
GeoFlood AI - Phase 9 test for predict.py.

The key check: running the full pipeline on a raw GeoTIFF must reproduce the
IoU that evaluate.py measured for the same chip.

Usage (from project root):  python -m ai.src.test_predict
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from ai.src import config
from ai.src.predict import FloodPredictor

SEP = "=" * 66


def iou_against_label(mask, label):
    """mask: 0/1/255 from the predictor; label: raw -1/0/1."""
    valid = (label != -1) & (mask != 255)
    tp = int(((mask == 1) & (label == 1) & valid).sum())
    fp = int(((mask == 1) & (label != 1) & valid).sum())
    fn = int(((mask != 1) & (label == 1) & valid).sum())
    return tp / (tp + fp + fn)


def write_tif(path, array, nodata=None, crs="EPSG:4326", transform=None):
    h, w = array.shape[1:]
    transform = transform or from_origin(78.0, 17.0, 0.001, 0.001)
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=array.shape[0],
                       dtype="float32", crs=crs, transform=transform, nodata=nodata) as dst:
        dst.write(array.astype("float32"))


def pick_india_test_chip():
    csv = config.ROOT / "ai" / "results" / "per_chip_results.csv"
    if not csv.exists():
        raise FileNotFoundError("Run python -m ai.src.evaluate first (it creates per_chip_results.csv)")
    df = pd.read_csv(csv)
    df = df[(df.split == "test") & (df.country == "India") & df.iou.notna()].sort_values("iou")
    row = df.iloc[len(df) // 2]          # the median India test chip, not a cherry-picked one
    return row["chip"], float(row["iou"])


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 9 Prediction Test")
    print(SEP)

    predictor = FloodPredictor()
    print(f"\nModel: {predictor.checkpoint_name}   device: {predictor.device}   "
          f"threshold: {predictor.threshold}")

    chip, eval_iou = pick_india_test_chip()
    tif = config.IMG_DIR / f"{chip}_S1Hand.tif"
    with rasterio.open(config.LBL_DIR / f"{chip}_LabelHand.tif") as src:
        label = src.read(1)
    print(f"Test chip: {chip}  (IoU recorded by evaluate.py: {eval_iou:.4f})")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        print("\n--- 1. End-to-end on a raw GeoTIFF ---")
        res = predictor.predict_file(tif, out_dir=tmp)
        my_iou = iou_against_label(res.mask, label)
        print(f"  IoU from predict.py: {my_iou:.4f}")
        assert abs(my_iou - eval_iou) < 0.005, "does not match evaluate.py!"
        print("  [OK] matches the evaluation result")
        print(f"  Stats: flood {res.stats['flood_pct_of_valid']}% of valid pixels, "
              f"mean confidence {res.stats['mean_flood_confidence']}")

        print("\n--- 2. Georeferencing preserved ---")
        with rasterio.open(tif) as a, rasterio.open(res.mask_path) as b:
            assert a.crs == b.crs and a.transform == b.transform
            assert (a.height, a.width) == (b.height, b.width)
            print(f"  [OK] CRS {b.crs}, same transform and size as the input")
            print(f"       bounds {tuple(round(v, 4) for v in b.bounds)}")
        assert res.probability_path.exists()
        print("  [OK] probability map saved too")

        print("\n--- 3. Tiling a chip into 256x256 tiles ---")
        small = FloodPredictor(tile_size=256, overlap=64).predict_file(tif)
        tiled_iou = iou_against_label(small.mask, label)
        diff = abs(tiled_iou - my_iou)
        print(f"  IoU single pass {my_iou:.4f} vs tiled {tiled_iou:.4f}  (difference {diff:.4f})")
        assert small.mask.shape == res.mask.shape
        print("  [OK] same output size" + ("" if diff < 0.05 else
              "   [NOTE] difference above 0.05: tell me this number"))

        print("\n--- 4. Image size not divisible by 16 ---")
        with rasterio.open(tif) as src:
            raw = src.read().astype("float32")
        prob, valid = predictor.predict_array(raw[:, :500, :470])
        assert prob.shape == (500, 470) and valid.shape == (500, 470)
        print(f"  [OK] 500x470 input gives a 500x470 output")

        print("\n--- 5. No-data pixels are respected ---")
        with rasterio.open(tif) as src:
            transform, crs = src.transform, src.crs
        holed = raw.copy()
        holed[:, 100:150, 100:150] = -9999.0
        holed_path = tmp / "holed.tif"
        write_tif(holed_path, holed, nodata=-9999.0, crs=crs, transform=transform)
        r = predictor.predict_file(holed_path)
        assert (r.mask[100:150, 100:150] == 255).all()
        print("  [OK] a block marked as no-data comes out as 255 in the mask")

        print("\n--- 6. Bad inputs ---")
        three = tmp / "three_bands.tif"
        write_tif(three, np.random.randn(3, 64, 64))
        try:
            predictor.predict_file(three)
            raise AssertionError("3-band file should have been rejected")
        except ValueError as err:
            print(f"  [OK] 3-band file rejected: {err}")
        try:
            predictor.predict_file(tmp / "missing.tif")
            raise AssertionError("missing file should have raised")
        except FileNotFoundError:
            print("  [OK] missing file rejected")
        notdb = tmp / "not_db.tif"
        write_tif(notdb, np.random.uniform(0, 255, (2, 70, 50)))
        r = predictor.predict_file(notdb)
        assert r.mask.shape == (70, 50) and r.stats["warnings"]
        print(f"  [OK] 0-255 image (70x50) still runs, with warning: {r.stats['warnings'][0]}")

    print("\n" + SEP)
    print("  All prediction tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
