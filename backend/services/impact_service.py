"""
GeoFlood AI backend - impact analysis (Phase 17b).

The spatial work is done by the PostGIS function compute_impact() from database/impact_analysis.sql.
This module calls it and reads the stored results back.
"""

import json
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

COMPARED_AGAINST = {
    "water": "all detected water (no baseline layer was used)",
    "new_flood": "new flood: water that is not on the baseline layer",
}
LAYER_KEYS = {"village": "villages", "road": "roads", "farmland": "farmland",
              "infrastructure": "infrastructure"}

# One query per layer. The layer name from the URL only selects an entry here; it is never put into SQL.
LAYER_SQL = {
    "villages": """
        SELECT f.feature_id, f.name, f.category, f.source_ref, t.relation, t.distance_m,
               t.flooded_area_km2, t.flooded_pct, ST_AsGeoJSON(f.geom, 6) AS geojson
          FROM affected_villages t JOIN reference_features f ON f.feature_id = t.feature_id
         WHERE t.analysis_id = :aid AND t.zone_type = :zone
         ORDER BY f.name, f.feature_id""",
    "roads": """
        SELECT f.feature_id, f.name, f.category, f.source_ref,
               t.flooded_length_km, t.flooded_pct, ST_AsGeoJSON(t.flooded_geom, 6) AS geojson
          FROM affected_roads t JOIN reference_features f ON f.feature_id = t.feature_id
         WHERE t.analysis_id = :aid AND t.zone_type = :zone
         ORDER BY f.name, f.feature_id""",
    "farmland": """
        SELECT f.feature_id, f.name, f.category, f.source_ref,
               t.flooded_area_km2, t.flooded_pct, ST_AsGeoJSON(t.flooded_geom, 6) AS geojson
          FROM agricultural_areas t JOIN reference_features f ON f.feature_id = t.feature_id
         WHERE t.analysis_id = :aid AND t.zone_type = :zone
         ORDER BY f.name, f.feature_id""",
    "infrastructure": """
        SELECT f.feature_id, f.name, f.category, f.source_ref, t.relation, t.distance_m,
               ST_AsGeoJSON(f.geom, 6) AS geojson
          FROM critical_infrastructure t JOIN reference_features f ON f.feature_id = t.feature_id
         WHERE t.analysis_id = :aid AND t.zone_type = :zone
         ORDER BY t.distance_m, f.name, f.feature_id""",
}


def baseline_of(db: Session, analysis_id: int) -> Optional[str]:
    """The baseline method of an analysis, or None when the analysis does not exist."""
    row = db.execute(text("SELECT baseline_method FROM flood_analysis WHERE analysis_id = :id"),
                     {"id": analysis_id}).first()
    return None if row is None else row[0]


def resolve_zone(baseline_method: str, zone_type: Optional[str]) -> str:
    """Compare against new flood when a baseline exists, otherwise against all water."""
    if zone_type:
        return zone_type
    return "water" if baseline_method == "none" else "new_flood"


def run_compute(db: Session, analysis_id: int, zone_type: str, near_m: float) -> dict:
    """Call compute_impact(). The caller commits. The casts make the driver's parameter types explicit."""
    rows = db.execute(
        text("SELECT layer_name, features_affected FROM compute_impact("
             "CAST(:aid AS bigint), CAST(:zone AS text), CAST(:near AS numeric))"),
        {"aid": analysis_id, "zone": zone_type, "near": near_m}).all()
    return {LAYER_KEYS[name]: int(n) for name, n in rows}


def summarize(db: Session, analysis_id: int, zone_type: str) -> dict:
    p = {"aid": analysis_id, "zone": zone_type}

    v = db.execute(text("""
        SELECT count(*) AS n, count(*) FILTER (WHERE relation = 'inside') AS inside_n,
               count(*) FILTER (WHERE relation = 'near') AS near_n, max(created_at) AS last
          FROM affected_villages WHERE analysis_id = :aid AND zone_type = :zone"""), p).mappings().one()
    r = db.execute(text("""
        SELECT count(*) AS n, coalesce(sum(flooded_length_km), 0) AS total, max(created_at) AS last
          FROM affected_roads WHERE analysis_id = :aid AND zone_type = :zone"""), p).mappings().one()
    a = db.execute(text("""
        SELECT count(*) AS n, coalesce(sum(flooded_area_km2), 0) AS total, max(created_at) AS last
          FROM agricultural_areas WHERE analysis_id = :aid AND zone_type = :zone"""), p).mappings().one()
    i = db.execute(text("""
        SELECT count(*) AS n, count(*) FILTER (WHERE relation = 'inside') AS inside_n,
               count(*) FILTER (WHERE relation = 'near') AS near_n, max(created_at) AS last
          FROM critical_infrastructure WHERE analysis_id = :aid AND zone_type = :zone"""), p).mappings().one()

    by_category = defaultdict(lambda: {"inside": 0, "near": 0})
    for row in db.execute(text("""
            SELECT coalesce(f.category, 'unknown') AS category, ci.relation, count(*) AS n
              FROM critical_infrastructure ci JOIN reference_features f ON f.feature_id = ci.feature_id
             WHERE ci.analysis_id = :aid AND ci.zone_type = :zone
             GROUP BY 1, 2"""), p).mappings():
        by_category[row["category"]][row["relation"]] = int(row["n"])

    stamps = [x["last"] for x in (v, r, a, i) if x["last"] is not None]
    return {
        "last_computed_at": max(stamps) if stamps else None,
        "villages": {"count": int(v["n"]), "inside": int(v["inside_n"]), "near": int(v["near_n"])},
        "roads": {"count": int(r["n"]), "flooded_length_km": round(float(r["total"]), 6)},
        "farmland": {"count": int(a["n"]), "flooded_area_km2": round(float(a["total"]), 6)},
        "infrastructure": {"count": int(i["n"]), "inside": int(i["inside_n"]),
                           "near": int(i["near_n"]), "by_category": dict(by_category)},
    }


def _plain(value):
    return float(value) if isinstance(value, Decimal) else value


def layer_geojson(db: Session, analysis_id: int, zone_type: str, layer: str) -> dict:
    features = []
    for row in db.execute(text(LAYER_SQL[layer]), {"aid": analysis_id, "zone": zone_type}).mappings():
        features.append({
            "type": "Feature",
            "geometry": json.loads(row["geojson"]),
            "properties": {k: _plain(v) for k, v in row.items() if k != "geojson"},
        })
    return {"type": "FeatureCollection", "zone_type": zone_type, "features": features}
