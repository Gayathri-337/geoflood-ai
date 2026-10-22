"""
GeoFlood AI - Phase 12: area calculation.

    from gis.area_calculator import analyze_water
    stats = analyze_water(mask, transform, crs, permanent=None)

mask      : uint8 array, 0 = not water, 1 = water, 255 = no data
permanent : optional uint8 array of the same shape, 1 = permanent water (baseline layer, e.g. JRC)

Areas come from counting pixels, using the exact area of each pixel:
  * geographic rasters (degrees): exact WGS84 ellipsoid area of each pixel row
  * projected rasters (metres)  : pixel width x height from the transform

"new_flood" = predicted water that is NOT on the baseline layer. This is an approximation:
it also contains seasonal water, shifted channels and anything the baseline missed.

Command line (project root):
    python -m gis.area_calculator --mask a_floodmask.tif [--permanent a_JRCWaterHand.tif]
"""

import argparse
import json

import numpy as np
import rasterio
from pyproj import CRS

NODATA = 255

WGS84_A = 6378137.0                       # equatorial radius in metres
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
WGS84_E = float(np.sqrt(WGS84_E2))


def _as_pyproj(crs):
    """Accept a rasterio CRS, a pyproj CRS or a string such as 'EPSG:4326'."""
    if hasattr(crs, "to_wkt"):
        return CRS.from_wkt(crs.to_wkt())
    return CRS.from_user_input(crs)


def _q(lat_deg):
    """Authalic function q(latitude) of the WGS84 ellipsoid (Snyder, Map Projections, eq. 3-12)."""
    s = np.sin(np.radians(lat_deg))
    e = WGS84_E
    return (1 - WGS84_E2) * (s / (1 - WGS84_E2 * s ** 2)
                             - (1 / (2 * e)) * np.log((1 - e * s) / (1 + e * s)))


def geographic_cell_area_km2(lat_a, lat_b, dlon_deg):
    """Exact ellipsoidal area (km2) of the cell between two latitudes and dlon_deg of longitude."""
    dlon = np.radians(abs(dlon_deg))
    return 0.5 * WGS84_A ** 2 * dlon * np.abs(_q(lat_b) - _q(lat_a)) / 1e6


def row_areas_km2(transform, crs, height):
    """Area (km2) of ONE pixel in each row of a raster, as a float array of length `height`."""
    if crs is None:
        raise ValueError("The raster has no coordinate system, so areas cannot be computed.")
    pcrs = _as_pyproj(crs)

    if pcrs.is_geographic:
        if abs(transform.b) > 1e-12 or abs(transform.d) > 1e-12:
            raise ValueError("Rotated geographic rasters are not supported.")
        rows = np.arange(height)
        lat_top = transform.f + rows * transform.e
        lat_bottom = transform.f + (rows + 1) * transform.e
        return geographic_cell_area_km2(lat_top, lat_bottom, transform.a)

    if not pcrs.is_projected:
        raise ValueError("Unsupported coordinate system: expected a geographic or projected CRS.")
    metres_per_unit = pcrs.axis_info[0].unit_conversion_factor
    cell_m2 = abs(transform.a * transform.e - transform.b * transform.d) * metres_per_unit ** 2
    return np.full(height, cell_m2 / 1e6)


def mask_area_km2(flag, transform, crs):
    """Area (km2) covered by the True pixels of a 2-D boolean array."""
    flag = np.asarray(flag, dtype=bool)
    rows = row_areas_km2(transform, crs, flag.shape[0])
    return float((flag.sum(axis=1) * rows).sum())


def polygon_area_km2(gdf):
    """Area (km2) of a GeoDataFrame's polygons, measured in the local UTM zone (cross-check)."""
    if gdf.empty:
        return 0.0
    if gdf.crs is None:
        raise ValueError("The polygons have no coordinate system.")
    return float(gdf.to_crs(gdf.estimate_utm_crs()).geometry.area.sum() / 1e6)


def _r6(x):
    return round(float(x), 6)


def analyze_water(mask, transform, crs, permanent=None):
    """Area statistics for a water mask. Returns a dict of plain Python numbers (JSON-safe)."""
    mask = np.asarray(mask)
    if mask.ndim != 2:
        raise ValueError(f"mask must be 2-D, got shape {mask.shape}")

    rows = row_areas_km2(transform, crs, mask.shape[0])

    def area(flag):
        return float((flag.sum(axis=1) * rows).sum())

    valid = mask != NODATA
    water = mask == 1
    valid_km2, water_km2 = area(valid), area(water)

    out = {
        "valid_area_km2": _r6(valid_km2),
        "nodata_area_km2": _r6(area(~valid)),
        "water_pixels": int(water.sum()),
        "water_area_km2": _r6(water_km2),
        "water_pct_of_valid": round(100 * water_km2 / valid_km2, 3) if valid_km2 else 0.0,
        "permanent_water_area_km2": None,
        "new_flood_area_km2": None,
        "new_flood_pct_of_valid": None,
        "new_flood_share_of_water_pct": None,
        "area_method": ("WGS84 ellipsoid, exact per pixel row" if _as_pyproj(crs).is_geographic
                        else "projected pixel size"),
    }

    if permanent is not None:
        permanent = np.asarray(permanent)
        if permanent.shape != mask.shape:
            raise ValueError(f"permanent layer shape {permanent.shape} != mask shape {mask.shape}")
        perm_km2 = area(water & (permanent == 1))
        new_km2 = area(water & (permanent != 1))
        out["permanent_water_area_km2"] = _r6(perm_km2)
        out["new_flood_area_km2"] = _r6(new_km2)
        out["new_flood_pct_of_valid"] = round(100 * new_km2 / valid_km2, 3) if valid_km2 else 0.0
        out["new_flood_share_of_water_pct"] = round(100 * new_km2 / water_km2, 3) if water_km2 else 0.0
    return out


def main():
    p = argparse.ArgumentParser(description="Water / new-flood area of a mask GeoTIFF")
    p.add_argument("--mask", required=True)
    p.add_argument("--permanent", default=None, help="optional permanent-water GeoTIFF (1 = water)")
    args = p.parse_args()

    with rasterio.open(args.mask) as src:
        mask, transform, crs = src.read(1), src.transform, src.crs
    permanent = None
    if args.permanent:
        with rasterio.open(args.permanent) as src:
            permanent = src.read(1)
    print(json.dumps(analyze_water(mask, transform, crs, permanent), indent=2))


if __name__ == "__main__":
    main()
