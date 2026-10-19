"""
GeoFlood AI - Phase 11: convert a water/flood mask into GIS polygons.

    from gis.mask_to_polygons import mask_file_to_polygons, save_geojson
    gdf = mask_file_to_polygons("scene_floodmask.tif", "scene_floodprob.tif")
    save_geojson(gdf, "scene.geojson")

Input mask values: 0 = not water, 1 = water, 255 = no data (only 1 becomes a polygon).

Output: a GeoDataFrame with one row per connected water body:
    poly_id    1 = largest
    n_pixels   water pixels in that body (before smoothing)
    mean_prob  mean model probability over those pixels (NaN if none given)
    geometry   Polygon, in the same coordinate system as the input raster

Cleaning: (1) remove tiny blobs, (2) fill tiny holes, (3) smooth staircase edges.
All sizes are in PIXELS, so the same settings work at any resolution.
NOTE: the model detects surface water (rivers included), not flood-only water.

Command line (project root):
    python -m gis.mask_to_polygons --mask a_floodmask.tif --prob a_floodprob.tif --out a.geojson
"""

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from scipy import ndimage
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

DEFAULT_MIN_PIXELS = 25
DEFAULT_MIN_HOLE_PIXELS = 25
DEFAULT_SIMPLIFY_PIXELS = 1.0
COLUMNS = ["poly_id", "n_pixels", "mean_prob"]


def _empty(crs):
    return gpd.GeoDataFrame({c: [] for c in COLUMNS}, geometry=[], crs=crs)


def label_water_bodies(mask, min_pixels=DEFAULT_MIN_PIXELS):
    """
    Find connected water bodies (pixels touching along an edge), drop those smaller
    than min_pixels, and number the rest by size (1 = largest).

    Returns (labels, sizes): labels is an int32 [H, W] array (0 = background),
    sizes[i] is the pixel count of body number i + 1.
    """
    labels, n = ndimage.label(mask == 1)            # default = edge-connected (4-connectivity)
    counts = np.bincount(labels.ravel(), minlength=n + 1)
    keep = [i for i in range(1, n + 1) if counts[i] >= min_pixels]
    keep.sort(key=lambda i: -counts[i])

    remap = np.zeros(n + 1, dtype=np.int32)         # old number -> new number (0 = dropped)
    for new_id, old_id in enumerate(keep, start=1):
        remap[old_id] = new_id
    sizes = np.array([counts[i] for i in keep], dtype=np.int64)
    return remap[labels], sizes


def _drop_small_holes(geom, min_area):
    """Remove interior rings (holes) smaller than min_area."""
    if geom.geom_type == "MultiPolygon":
        return MultiPolygon([_drop_small_holes(p, min_area) for p in geom.geoms])
    holes = [ring for ring in geom.interiors if Polygon(ring).area >= min_area]
    return Polygon(geom.exterior, holes)


def mask_to_polygons(mask, transform, crs, probability=None,
                     min_pixels=DEFAULT_MIN_PIXELS,
                     min_hole_pixels=DEFAULT_MIN_HOLE_PIXELS,
                     simplify_pixels=DEFAULT_SIMPLIFY_PIXELS):
    """Convert a 0/1/255 mask array into a GeoDataFrame of water polygons."""
    if mask.ndim != 2:
        raise ValueError(f"mask must be 2-D, got shape {mask.shape}")
    if probability is not None and probability.shape != mask.shape:
        raise ValueError("probability and mask must have the same shape")

    labels, sizes = label_water_bodies(mask, min_pixels)
    k = len(sizes)
    if k == 0:
        return _empty(crs)

    pixel = abs(transform.a)                        # pixel width in CRS units (degrees or metres)
    hole_area = min_hole_pixels * pixel * pixel
    tolerance = simplify_pixels * pixel

    # Trace the outline of every labelled body
    parts = {}
    for geom_dict, value in shapes(labels, mask=labels > 0, transform=transform, connectivity=4):
        parts.setdefault(int(value), []).append(shape(geom_dict))

    geoms = []
    for pid in range(1, k + 1):
        g = unary_union(parts[pid])
        g = _drop_small_holes(g, hole_area)
        if simplify_pixels > 0:
            g = g.simplify(tolerance, preserve_topology=True)
        geoms.append(g)

    if probability is not None:
        weights = np.nan_to_num(probability, nan=0.0).ravel()
        sums = np.bincount(labels.ravel(), weights=weights, minlength=k + 1)
        mean_prob = np.round(sums[1:] / sizes, 4)
    else:
        mean_prob = np.full(k, np.nan)

    return gpd.GeoDataFrame(
        {"poly_id": np.arange(1, k + 1), "n_pixels": sizes, "mean_prob": mean_prob},
        geometry=geoms, crs=crs,
    )


def mask_file_to_polygons(mask_path, probability_path=None, **kwargs):
    """Read a mask GeoTIFF (and optional probability GeoTIFF) and return polygons."""
    with rasterio.open(mask_path) as src:
        mask, transform, crs = src.read(1), src.transform, src.crs
    prob = None
    if probability_path is not None:
        with rasterio.open(probability_path) as src:
            prob = src.read(1)
    return mask_to_polygons(mask, transform, crs, prob, **kwargs)


def save_geojson(gdf, path):
    """Write GeoJSON (always in longitude/latitude). Returns False if there was nothing to write."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if gdf.empty:
        print(f"  (no polygons, nothing written to {path.name})")
        return False
    out = gdf
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        out = gdf.to_crs(4326)
    out.to_file(path, driver="GeoJSON")
    return True


def main():
    p = argparse.ArgumentParser(description="Convert a flood/water mask GeoTIFF into GeoJSON polygons")
    p.add_argument("--mask", required=True)
    p.add_argument("--prob", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--min-pixels", type=int, default=DEFAULT_MIN_PIXELS)
    p.add_argument("--min-hole-pixels", type=int, default=DEFAULT_MIN_HOLE_PIXELS)
    p.add_argument("--simplify-pixels", type=float, default=DEFAULT_SIMPLIFY_PIXELS)
    args = p.parse_args()

    gdf = mask_file_to_polygons(args.mask, args.prob, min_pixels=args.min_pixels,
                                min_hole_pixels=args.min_hole_pixels,
                                simplify_pixels=args.simplify_pixels)
    print(f"Polygons: {len(gdf)}   CRS: {gdf.crs}")
    if len(gdf):
        print(gdf.drop(columns="geometry").head(10).to_string(index=False))
    if save_geojson(gdf, args.out):
        print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
