"""
GeoFlood AI backend - saving analyses to PostgreSQL and reading them back (Phase 17a).

All SQL for analyses lives here. The caller (the router) owns the transaction: it commits on
success and rolls back on failure.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import RasterioError
from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import ROOT
from backend.services.uploads import UploadRejected
from gis.mask_to_polygons import mask_to_polygons


# ------------------------------------------------------------------ paths and files
def stored_path(path) -> str:
    """A path as stored in the database: relative to the project root when inside it."""
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_stored(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else ROOT / p


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ baseline layer
def read_baseline(baseline_path, image_path) -> np.ndarray:
    """
    Read a baseline water layer and check it sits exactly on the image's grid.
    Returns a uint8 array: 1 = water, 0 = anything else.
    """
    try:
        with rasterio.open(baseline_path) as b, rasterio.open(image_path) as a:
            if b.count != 1:
                raise UploadRejected(422, f"The baseline layer has {b.count} band(s); it must have "
                                          "exactly 1 band (1 = water).")
            if b.crs is None or b.crs != a.crs:
                raise UploadRejected(422, "The baseline layer uses a different coordinate system "
                                          "than the image.")
            if (b.height, b.width) != (a.height, a.width):
                raise UploadRejected(422, f"The baseline layer must have the same size as the image "
                                          f"({a.width} x {a.height} pixels).")
            tolerance = 1e-6 if a.crs.is_geographic else 0.01
            if not np.allclose(tuple(b.bounds), tuple(a.bounds), rtol=0, atol=tolerance):
                raise UploadRejected(422, "The baseline layer does not cover exactly the same area "
                                          "as the image.")
            data = b.read(1)
    except RasterioError:
        raise UploadRejected(422, "The baseline file could not be read as a GeoTIFF image.")
    return (data == 1).astype(np.uint8)


# ------------------------------------------------------------------ polygons
def build_zones(mask, probability, transform, crs, permanent=None) -> list[dict]:
    """
    Turn the water mask into polygons, one list entry per polygon.
    Without a baseline every polygon is 'water'. With one, water is split into
    'permanent_water' (on the baseline) and 'new_flood' (not on the baseline).
    """
    water = mask == 1
    if permanent is None:
        classes = {"water": water}
    else:
        classes = {"permanent_water": water & (permanent == 1),
                   "new_flood": water & (permanent != 1)}

    zones = []
    for zone_type, flag in classes.items():
        gdf = mask_to_polygons(flag.astype(np.uint8), transform, crs, probability)
        if gdf.empty:
            continue
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)                 # the database stores longitude/latitude
        for row in gdf.itertuples(index=False):
            zones.append({
                "zone_type": zone_type,
                "poly_no": int(row.poly_id),
                "n_pixels": int(row.n_pixels),
                "mean_confidence": None if np.isnan(row.mean_prob) else float(row.mean_prob),
                "wkb": row.geometry.wkb,
            })
    return zones


# ------------------------------------------------------------------ writing
def store_analysis(db: Session, *, event_id, source_id, file_name, input_path, band_count,
                   result, areas, baseline_method, zones) -> int:
    """Insert the image, the analysis and its zones. Does NOT commit. Returns analysis_id."""
    stats = result.stats
    west, south, east, north = transform_bounds(
        result.crs, "EPSG:4326",
        *array_bounds(stats["height"], stats["width"], result.transform))
    epsg = result.crs.to_epsg()

    image_id = db.execute(text("""
        INSERT INTO satellite_images (event_id, source_id, image_role, file_name, file_path,
                                      file_sha256, width_px, height_px, band_count, crs, footprint)
        VALUES (:event_id, :source_id, 'event', :file_name, :file_path, :sha, :w, :h, :bands, :crs,
                ST_MakeEnvelope(:west, :south, :east, :north, 4326))
        RETURNING image_id"""), {
        "event_id": event_id, "source_id": source_id, "file_name": file_name,
        "file_path": stored_path(input_path), "sha": sha256_of(input_path),
        "w": stats["width"], "h": stats["height"], "bands": band_count,
        "crs": f"EPSG:{epsg}" if epsg else "custom",
        "west": west, "south": south, "east": east, "north": north,
    }).scalar_one()

    analysis_id = db.execute(text("""
        INSERT INTO flood_analysis (
            image_id, baseline_method, model_name, threshold, status,
            valid_area_km2, nodata_area_km2, water_pixels, water_area_km2, water_pct_of_valid,
            permanent_water_area_km2, new_flood_area_km2, new_flood_pct_of_valid,
            mean_confidence, area_method, mask_path, probability_path, warnings)
        VALUES (
            :image_id, :baseline_method, :model_name, :threshold, 'completed',
            :valid, :nodata, :water_px, :water, :water_pct,
            :perm, :new, :new_pct,
            :confidence, :method, :mask_path, :prob_path, CAST(:warnings AS jsonb))
        RETURNING analysis_id"""), {
        "image_id": image_id, "baseline_method": baseline_method,
        "model_name": stats["model_checkpoint"], "threshold": stats["threshold"],
        "valid": areas["valid_area_km2"], "nodata": areas["nodata_area_km2"],
        "water_px": areas["water_pixels"], "water": areas["water_area_km2"],
        "water_pct": areas["water_pct_of_valid"],
        "perm": areas["permanent_water_area_km2"], "new": areas["new_flood_area_km2"],
        "new_pct": areas["new_flood_pct_of_valid"],
        "confidence": stats["mean_flood_confidence"], "method": areas["area_method"],
        "mask_path": stored_path(result.mask_path), "prob_path": stored_path(result.probability_path),
        "warnings": json.dumps(stats["warnings"]),
    }).scalar_one()

    if zones:
        db.execute(text("""
            INSERT INTO flood_zones (analysis_id, zone_type, poly_no, n_pixels, area_km2,
                                     mean_confidence, geom)
            VALUES (:analysis_id, :zone_type, :poly_no, :n_pixels, 0, :mean_confidence,
                    ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromWKB(:wkb, 4326)), 3)))"""),
            [{**z, "analysis_id": analysis_id} for z in zones])
        # the real area, measured by PostGIS on the spheroid
        db.execute(text("UPDATE flood_zones "
                        "SET area_km2 = round((ST_Area(geom::geography) / 1000000.0)::numeric, 6) "
                        "WHERE analysis_id = :aid"), {"aid": analysis_id})
    return analysis_id


# ------------------------------------------------------------------ reading
ANALYSIS_SELECT = """
    SELECT a.analysis_id, i.event_id, a.image_id, i.source_id, i.file_name,
           a.status, a.created_at, a.model_name, a.threshold, a.baseline_method,
           i.width_px, i.height_px, i.crs,
           ST_XMin(i.footprint) AS west, ST_YMin(i.footprint) AS south,
           ST_XMax(i.footprint) AS east, ST_YMax(i.footprint) AS north,
           a.valid_area_km2, a.nodata_area_km2, a.water_pixels, a.water_area_km2,
           a.water_pct_of_valid, a.permanent_water_area_km2, a.new_flood_area_km2,
           a.new_flood_pct_of_valid, a.mean_confidence, a.area_method, a.severity, a.warnings,
           (SELECT count(*) FROM flood_zones z WHERE z.analysis_id = a.analysis_id) AS zone_count
      FROM flood_analysis a
      JOIN satellite_images i ON i.image_id = a.image_id
"""


def _f(value):
    return None if value is None else float(value)


def to_analysis_dict(row) -> dict:
    water, new = _f(row["water_area_km2"]), _f(row["new_flood_area_km2"])
    warnings = row["warnings"]
    if isinstance(warnings, str):
        warnings = json.loads(warnings)
    aid = row["analysis_id"]
    return {
        "analysis_id": aid, "event_id": row["event_id"], "image_id": row["image_id"],
        "source_id": row["source_id"], "original_filename": row["file_name"],
        "status": row["status"], "created_at": row["created_at"],
        "model_name": row["model_name"], "threshold": float(row["threshold"]),
        "baseline_method": row["baseline_method"],
        "height_px": row["height_px"], "width_px": row["width_px"], "crs": row["crs"],
        "bounds_wgs84": [round(float(row[k]), 6) for k in ("west", "south", "east", "north")],
        "valid_area_km2": _f(row["valid_area_km2"]), "nodata_area_km2": _f(row["nodata_area_km2"]),
        "water_pixels": row["water_pixels"], "water_area_km2": water,
        "water_pct_of_valid": _f(row["water_pct_of_valid"]),
        "permanent_water_area_km2": _f(row["permanent_water_area_km2"]),
        "new_flood_area_km2": new, "new_flood_pct_of_valid": _f(row["new_flood_pct_of_valid"]),
        "new_flood_share_of_water_pct": round(100 * new / water, 3) if new is not None and water else None,
        "mean_confidence": _f(row["mean_confidence"]), "area_method": row["area_method"],
        "severity": row["severity"],
        "zone_count": int(row["zone_count"]), "warnings": warnings or [],
        "mask_url": f"/api/analyses/{aid}/mask", "zones_url": f"/api/analyses/{aid}/zones",
    }


def fetch_analysis(db: Session, analysis_id: int):
    row = db.execute(text(ANALYSIS_SELECT + " WHERE a.analysis_id = :id"),
                     {"id": analysis_id}).mappings().first()
    return to_analysis_dict(row) if row else None


def list_analyses(db: Session, event_id, limit: int, offset: int) -> list[dict]:
    sql = ANALYSIS_SELECT
    params = {"limit": limit, "offset": offset}
    if event_id is not None:
        sql += " WHERE i.event_id = :event_id"
        params["event_id"] = event_id
    sql += " ORDER BY a.analysis_id DESC LIMIT :limit OFFSET :offset"
    return [to_analysis_dict(r) for r in db.execute(text(sql), params).mappings()]
