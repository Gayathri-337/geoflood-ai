"""
GeoFlood AI - Phase 11 test: mask -> polygons.

Part 1 uses synthetic masks whose correct answers are known.
Part 2 converts the India test masks from Phase 10 into GeoJSON files
(ai/results/polygons/), checks them, and draws two overlay pictures.

Usage (project root):  python -m gis.test_polygons
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import box

from ai.src import config
from gis.mask_to_polygons import (label_water_bodies, mask_file_to_polygons,
                                  mask_to_polygons, save_geojson)

SEP = "=" * 66
PRED_DIR = config.ROOT / "ai" / "results" / "predictions" / "test"
OUT_DIR = config.ROOT / "ai" / "results" / "polygons"


def test_synthetic():
    pixel = 0.001
    transform = from_origin(78.0, 17.0, pixel, pixel)   # west, north, pixel width, pixel height
    crs = "EPSG:4326"

    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:50, 10:50] = 1        # A: 40 x 40 = 1600 pixels
    mask[25:27, 25:27] = 0        # a 2 x 2 hole inside A (4 pixels)
    mask[60:90, 5:20] = 1         # B: 30 x 15 = 450 pixels
    mask[70:74, 70:74] = 1        # speckle: 16 pixels
    mask[0:8, 80:100] = 255       # a no-data block
    prob = np.where(mask == 1, 0.9, 0.1).astype("float32")

    gdf = mask_to_polygons(mask, transform, crs, prob, min_pixels=25, min_hole_pixels=25,
                           simplify_pixels=1.0)

    assert len(gdf) == 2, f"expected 2 polygons, got {len(gdf)}"
    assert gdf.n_pixels.tolist() == [1596, 450], gdf.n_pixels.tolist()
    assert gdf.poly_id.tolist() == [1, 2]
    print(f"  [OK] 2 polygons with sizes {gdf.n_pixels.tolist()}: the 16-pixel speckle was removed")

    a = gdf.geometry.iloc[0]
    assert len(a.interiors) == 0
    assert abs(a.area - 1600 * pixel ** 2) < 1e-9
    print("  [OK] the tiny hole was filled (polygon A has no holes, area = 1600 pixels)")

    assert np.allclose(a.bounds, [78.010, 16.950, 78.050, 16.990], atol=1e-9)
    print(f"  [OK] georeferencing: polygon A spans {tuple(round(v, 3) for v in a.bounds)}, as expected")

    assert not gdf.intersects(box(78.080, 16.992, 78.100, 17.0)).any()
    print("  [OK] the no-data block produced no polygon")

    assert np.allclose(gdf.mean_prob, 0.9)
    print("  [OK] mean probability per polygon = 0.9")

    # A disk shows what smoothing does to a curved edge
    yy, xx = np.ogrid[:100, :100]
    disk = (((yy - 50) ** 2 + (xx - 50) ** 2) <= 30 ** 2).astype(np.uint8)
    raw = mask_to_polygons(disk, transform, crs, simplify_pixels=0, min_hole_pixels=0)
    smooth = mask_to_polygons(disk, transform, crs, simplify_pixels=1.0)
    raw_poly, smooth_poly = raw.geometry.iloc[0], smooth.geometry.iloc[0]
    assert abs(raw_poly.area / pixel ** 2 - disk.sum()) < 0.5, "raw polygon should match the pixels exactly"
    v_raw, v_smooth = len(raw_poly.exterior.coords), len(smooth_poly.exterior.coords)
    change = abs(smooth_poly.area - raw_poly.area) / raw_poly.area
    assert v_smooth < v_raw and change < 0.05
    print(f"  [OK] smoothing a disk: {v_raw} -> {v_smooth} vertices, area changed {100 * change:.2f}%")

    for name, arr in [("no water", np.zeros((50, 50), np.uint8)),
                      ("all no-data", np.full((50, 50), 255, np.uint8))]:
        g = mask_to_polygons(arr, transform, crs)
        assert len(g) == 0 and set(g.columns) == {"poly_id", "n_pixels", "mean_prob", "geometry"}
        assert g.crs is not None
    print("  [OK] masks with no water give an empty table without crashing")


def save_polygon_png(chip, gdf, path):
    with rasterio.open(config.IMG_DIR / f"{chip}_S1Hand.tif") as src:
        band, b = src.read(1).astype("float32"), src.bounds
    lo, hi = np.nanpercentile(band, [2, 98])
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(band, cmap="gray", vmin=lo, vmax=hi, extent=(b.left, b.right, b.bottom, b.top))
    gdf.plot(ax=ax, facecolor=(0.1, 0.3, 1.0, 0.35), edgecolor="red", linewidth=0.8)
    ax.set_xlim(b.left, b.right)
    ax.set_ylim(b.bottom, b.top)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"{chip}: {len(gdf)} water polygons (red outlines)")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    print(f"  Saved picture: {path}")


def test_real():
    masks = sorted(PRED_DIR.glob("India_*_floodmask.tif"))
    if not masks:
        print("  No India masks found. Run: python -m ai.src.generate_masks --split test --country India")
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows, collected, by_chip = [], [], {}
    for mp in masks:
        chip = mp.name.replace("_S1Hand_floodmask.tif", "")
        pp = mp.with_name(mp.name.replace("_floodmask", "_floodprob"))
        with rasterio.open(mp) as src:
            mask, transform = src.read(1), src.transform

        gdf = mask_file_to_polygons(mp, pp if pp.exists() else None)
        labels, _ = label_water_bodies(mask)
        kept = labels > 0

        if len(gdf):
            burned = rasterize(((g, 1) for g in gdf.geometry), out_shape=mask.shape,
                               transform=transform, fill=0, dtype="uint8") == 1
            iou = float((kept & burned).sum() / (kept | burned).sum())
            save_geojson(gdf, OUT_DIR / f"{chip}.geojson")
            collected.append(gdf.assign(chip=chip))
            by_chip[chip] = gdf
        else:
            iou = float("nan")
        rows.append({"chip": chip, "water_px": int((mask == 1).sum()),
                     "kept_px": int(kept.sum()), "polygons": len(gdf), "roundtrip_iou": iou})

    print(f"\n  {'chip':<18}{'water_px':>10}{'kept_px':>10}{'polygons':>10}{'roundtrip_IoU':>15}")
    for r in rows:
        print(f"  {r['chip']:<18}{r['water_px']:>10}{r['kept_px']:>10}{r['polygons']:>10}"
              f"{r['roundtrip_iou']:>15.3f}")
    print("  (round-trip IoU: polygons turned back into pixels vs the cleaned mask; 1.0 = identical)")

    combined = gpd.GeoDataFrame(pd.concat(collected, ignore_index=True), geometry="geometry",
                                crs=collected[0].crs)
    out = OUT_DIR / "india_test_water.geojson"
    save_geojson(combined, out)
    back = gpd.read_file(out)
    assert len(back) == len(combined) and back.crs.to_epsg() == 4326
    print(f"\n  [OK] combined GeoJSON re-read: {len(back)} polygons from {len(collected)} chips, "
          f"CRS {back.crs.to_epsg()}, file {out.stat().st_size / 1024:.0f} KB")

    for chip in ("India_591317", "India_747992"):
        if chip in by_chip:
            save_polygon_png(chip, by_chip[chip], OUT_DIR / f"{chip}_polygons.png")


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 11 Polygon Test")
    print(SEP)
    print("\n--- Part 1: synthetic masks with known answers ---")
    test_synthetic()
    print("\n--- Part 2: India test masks from Phase 10 ---")
    test_real()
    print("\n" + SEP)
    print("  Polygon tests finished.")
    print(SEP)


if __name__ == "__main__":
    main()
