"""
GeoFlood AI - Phase 12 test: area calculation.

Part 1: formulas checked against independent references, and synthetic masks with known answers.
Part 2: the 14 India test chips from Phase 10: water / permanent / new-flood areas, polygon
        cross-check, and a four-panel picture. Writes ai/results/area/.

Usage (project root):  python -m gis.test_area
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Geod
from rasterio.transform import from_origin
from shapely.geometry import box

from ai.src import config
from gis.area_calculator import (analyze_water, geographic_cell_area_km2, mask_area_km2,
                                 polygon_area_km2, row_areas_km2)
from gis.mask_to_polygons import label_water_bodies, mask_file_to_polygons

SEP = "=" * 70
PRED_DIR = config.ROOT / "ai" / "results" / "predictions" / "test"
JRC_DIR = config.RAW_DIR / "JRCWaterHand"
OUT_DIR = config.ROOT / "ai" / "results" / "area"


def test_formulas():
    # 1. Against pyproj's geodesic solver (an independent implementation)
    lon1, lat1, lon2, lat2 = 92.0, 26.0, 92.1, 26.1
    geod = Geod(ellps="WGS84")
    
    ref = abs(geod.polygon_area_perimeter([lon1, lon2, lon2, lon1], [lat1, lat1, lat2, lat2])[0]) / 1e6

    mine = float(geographic_cell_area_km2(lat1, lat2, lon2 - lon1))
    rel = abs(mine - ref) / ref
    assert rel < 1e-4, f"formula differs from pyproj by {rel:.2e}"
    print(f"  [OK] 0.1 x 0.1 degree box near 26N: mine {mine:.4f} km2, pyproj {ref:.4f} km2 "
          f"(relative difference {rel:.1e})")

    # 2. The same 0.01-degree square used in Phase 1 (which measured 1.1772 km2 via UTM 44N)
    hyd = float(geographic_cell_area_km2(17.38, 17.39, 0.01))
    assert abs(hyd - 1.1772) / 1.1772 < 0.005
    print(f"  [OK] Phase 1 square: {hyd:.4f} km2 here vs 1.1772 km2 via UTM "
          f"(UTM distorts area by roughly 0.1% at that spot)")

    # 3. Per-row areas add up to the whole box, and rows get smaller towards the pole
    t = from_origin(92.0, 26.1, 0.1 / 1000, 0.1 / 1000)
    rows = row_areas_km2(t, "EPSG:4326", 1000)
    assert abs(rows.sum() * 1000 - mine) / mine < 1e-6
    assert rows[0] < rows[-1]
    print("  [OK] 1000 pixel rows sum to the box area; the northern (top) row is smaller than the southern")


def test_synthetic():
    t = from_origin(500000.0, 2900000.0, 10.0, 10.0)      # 10 m pixels, UTM 46N
    crs = "EPSG:32646"

    only = np.zeros((100, 100), np.uint8)
    only[:30, :100] = 1
    area = mask_area_km2(only == 1, t, crs)
    assert abs(area - 0.3) < 1e-9
    print("  [OK] projected raster: 3000 pixels of 10 m x 10 m = 0.3 km2")

    mask = np.zeros((100, 100), np.uint8)
    mask[10:50, 10:50] = 1                  # 1600 water pixels
    mask[0:5, :] = 255                      # 500 no-data pixels
    perm = np.zeros((100, 100), np.uint8)
    perm[10:20, 10:50] = 1                  # 400 px of the water is permanent
    perm[60:70, 60:70] = 1                  # permanent water elsewhere must NOT count

    r = analyze_water(mask, t, crs, perm)
    expect = {"valid_area_km2": 0.95, "nodata_area_km2": 0.05, "water_area_km2": 0.16,
              "permanent_water_area_km2": 0.04, "new_flood_area_km2": 0.12,
              "new_flood_share_of_water_pct": 75.0}
    for key, value in expect.items():
        assert abs(r[key] - value) < 1e-9, f"{key}: {r[key]} != {value}"
    assert abs(r["permanent_water_area_km2"] + r["new_flood_area_km2"] - r["water_area_km2"]) < 1e-9
    print("  [OK] split: water 0.16 = permanent 0.04 + new flood 0.12 km2; no-data excluded; "
          "permanent water outside the mask ignored")

    r = analyze_water(mask, t, crs, None)
    assert r["new_flood_area_km2"] is None and r["permanent_water_area_km2"] is None
    print("  [OK] without a baseline layer the new-flood fields are None (not zero)")

    for bad, label in [((mask, t, None), "no CRS"),
                       ((mask, t, crs, np.zeros((10, 10))), "wrong-size baseline")]:
        try:
            analyze_water(*bad)
            raise AssertionError(f"{label} should have been rejected")
        except ValueError:
            pass
    print("  [OK] missing CRS and mismatched baseline are rejected")


def add_counts(c, pred, truth, valid):
    c["tp"] += int((pred & truth & valid).sum())
    c["fp"] += int((pred & ~truth & valid).sum())
    c["fn"] += int((~pred & truth & valid).sum())


def iou(c):
    u = c["tp"] + c["fp"] + c["fn"]
    return c["tp"] / u if u else float("nan")


def save_split_picture(chip, mask, jrc, path):
    with rasterio.open(config.IMG_DIR / f"{chip}_S1Hand.tif") as src:
        radar, b = src.read(1).astype("float32"), src.bounds
    extent = (b.left, b.right, b.bottom, b.top)
    lo, hi = np.nanpercentile(radar, [2, 98])
    water = mask == 1
    perm, new = water & (jrc == 1), water & (jrc != 1)

    def overlay(ax, flag, color):
        rgba = np.zeros(flag.shape + (4,))
        rgba[flag] = color
        ax.imshow(rgba, extent=extent)

    fig, axes = plt.subplots(1, 4, figsize=(18, 4.8), sharex=True, sharey=True)
    for ax in axes:
        ax.imshow(radar, cmap="gray", vmin=lo, vmax=hi, extent=extent)
        ax.set_xlabel("Longitude")
    overlay(axes[1], water, (0.1, 0.3, 1.0, 0.6))
    overlay(axes[2], jrc == 1, (0.0, 0.7, 0.0, 0.6))
    overlay(axes[3], perm, (0.0, 0.7, 0.0, 0.6))
    overlay(axes[3], new, (1.0, 0.0, 0.0, 0.6))
    for ax, title in zip(axes, ["Radar (VV)", "Predicted water (blue)", "JRC baseline water (green)",
                                "Green = predicted on baseline, red = new flood"]):
        ax.set_title(title, fontsize=10)
    axes[0].set_ylabel("Latitude")
    fig.suptitle(chip)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)
    print(f"  Saved picture: {path}")


def test_real():
    masks = sorted(PRED_DIR.glob("India_*_floodmask.tif"))
    if not masks or not JRC_DIR.exists():
        print("  Missing India masks or the JRC folder. Run generate_masks (Phase 10) and "
              "download_jrc (Phase 11) first.")
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows, c_water, c_new = [], dict(tp=0, fp=0, fn=0), dict(tp=0, fp=0, fn=0)
    first = None
    for mp in masks:
        chip = mp.name.replace("_S1Hand_floodmask.tif", "")
        with rasterio.open(mp) as src:
            mask, transform, crs, bounds = src.read(1), src.transform, src.crs, src.bounds
        with rasterio.open(JRC_DIR / f"{chip}_JRCWaterHand.tif") as src:
            jrc = src.read(1)
        with rasterio.open(config.LBL_DIR / f"{chip}_LabelHand.tif") as src:
            label = src.read(1)
        label_mask = np.where(label == -1, 255, label).astype("uint8")

        pred = analyze_water(mask, transform, crs, jrc)
        truth = analyze_water(label_mask, transform, crs, jrc)

        labels, _ = label_water_bodies(mask)
        kept_km2 = mask_area_km2(labels > 0, transform, crs)
        poly_km2 = polygon_area_km2(mask_file_to_polygons(mp))

        valid = (mask != config.IGNORE_INDEX) & (label != -1)
        p_water, t_water, not_jrc = mask == 1, label == 1, jrc != 1
        add_counts(c_water, p_water, t_water, valid)
        add_counts(c_new, p_water & not_jrc, t_water & not_jrc, valid)

        if first is None:
            first = (chip, mask, jrc, pred, bounds, transform)
        rows.append({
            "chip": chip, "valid_km2": pred["valid_area_km2"], "water_km2": pred["water_area_km2"],
            "permanent_km2": pred["permanent_water_area_km2"], "new_flood_km2": pred["new_flood_area_km2"],
            "label_water_km2": truth["water_area_km2"], "label_new_km2": truth["new_flood_area_km2"],
            "kept_km2": kept_km2, "polygon_km2": poly_km2,
            "poly_ratio": poly_km2 / kept_km2 if kept_km2 > 0 else float("nan"),
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "area_india_test.csv", index=False)

    # Chip footprint: raster method vs UTM polygon method
    chip0, mask0, jrc0, pred0, bounds0, _ = first
    total = pred0["valid_area_km2"] + pred0["nodata_area_km2"]
    utm_total = polygon_area_km2(gpd.GeoDataFrame(geometry=[box(*bounds0)], crs="EPSG:4326"))
    rel = abs(total - utm_total) / utm_total
    assert rel < 0.005
    print(f"\n  Chip footprint ({chip0}): {total:.3f} km2 by pixel counting, {utm_total:.3f} km2 via UTM "
          f"(difference {100 * rel:.2f}%); one pixel = {total * 1e6 / mask0.size:.1f} m2")

    print(f"\n  {'chip':<16}{'valid':>8}{'water':>8}{'perm.':>8}{'new':>8}{'lbl water':>11}{'lbl new':>9}{'poly/mask':>11}")
    for r in rows:
        print(f"  {r['chip']:<16}{r['valid_km2']:>8.2f}{r['water_km2']:>8.3f}{r['permanent_km2']:>8.3f}"
              f"{r['new_flood_km2']:>8.3f}{r['label_water_km2']:>11.3f}{r['label_new_km2']:>9.3f}"
              f"{r['poly_ratio']:>11.3f}")
    print("  (all areas in km2; 'perm.' = predicted water lying on the JRC layer, 'new' = the rest,")
    print("   'lbl' columns use the hand label instead of the prediction, 'poly/mask' = UTM polygon area")
    print("   divided by the cleaned-mask area)")

    big = df[df.kept_km2 > 1.0]
    worst = (big.poly_ratio - 1).abs().max()
    print(f"\n  Polygon vs mask area on chips with over 1 km2 of water: worst difference {100 * worst:.2f}%  "
          + ("[OK]" if worst < 0.03 else "[NOTE] above 3%: tell me this number"))

    iou_w, iou_n = iou(c_water), iou(c_new)
    print(f"\n  Pooled IoU over these {len(df)} India chips:")
    print(f"    total water                      : {iou_w:.4f}")
    print(f"    new flood (water not in JRC)     : {iou_n:.4f}")
    csv = config.ROOT / "ai" / "results" / "per_country_test.csv"
    if csv.exists():
        ref = float(pd.read_csv(csv).query("country == 'India'")["iou"].iloc[0])
        assert abs(iou_w - ref) < 0.005, f"does not reproduce Phase 8 ({ref:.4f})"
        print(f"  [OK] total-water IoU reproduces the Phase 8 India figure ({ref:.4f})")
    print("    ('new flood' is compared with label-minus-JRC, which is itself only an approximation,")
    print("     so this number measures agreement, not independent proof of flooding)")

    tw, tp_, tn = df.water_km2.sum(), df.permanent_km2.sum(), df.new_flood_km2.sum()
    print(f"\n  All 14 chips together: predicted water {tw:.2f} km2 = {tp_:.2f} on the JRC layer "
          f"+ {tn:.2f} new ({100 * tn / tw:.1f}% of the water)")

    pic = "India_591317"
    if pic in set(df.chip):
        with rasterio.open(PRED_DIR / f"{pic}_S1Hand_floodmask.tif") as src:
            m = src.read(1)
        with rasterio.open(JRC_DIR / f"{pic}_JRCWaterHand.tif") as src:
            j = src.read(1)
        save_split_picture(pic, m, j, OUT_DIR / f"{pic}_split.png")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 12 Area Calculation Test")
    print(SEP)
    print("\n--- Part 1a: formulas against independent references ---")
    test_formulas()
    print("\n--- Part 1b: synthetic masks with known answers ---")
    test_synthetic()
    print("\n--- Part 2: India test chips (Phase 10 masks + JRC layer) ---")
    test_real()
    print("\n" + SEP)
    print("  Area tests finished.")
    print(SEP)


if __name__ == "__main__":
    main()
