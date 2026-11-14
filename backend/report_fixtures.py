"""
SYNTHETIC data for testing the PDF report builder (Phase 28).

Every number, name and shape here is invented for the tests. None of it is a real analysis result,
so never show a PDF made from this data as if it were one.
"""

from datetime import datetime, timezone

UTC = timezone.utc
BOUNDS = [93.40, 26.30, 93.46, 26.35]          # west, south, east, north


def _box(west, south, east, north):
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north],
                                                [west, south]]]}


def _feature(geometry, **properties):
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


ANALYSIS = {
    "analysis_id": 7, "event_id": 3, "image_id": 7, "source_id": 1,
    "original_filename": "SYNTHETIC_chip_S1Hand.tif", "status": "completed",
    "created_at": datetime(2026, 11, 10, 9, 30, tzinfo=UTC),
    "model_name": "unet_flood_best.pth", "threshold": 0.5, "baseline_method": "jrc",
    "height_px": 512, "width_px": 512, "crs": "EPSG:4326", "bounds_wgs84": BOUNDS,
    "valid_area_km2": 25.0, "nodata_area_km2": 0.0, "water_pixels": 40000, "water_area_km2": 4.0,
    "water_pct_of_valid": 16.0, "permanent_water_area_km2": 1.0, "new_flood_area_km2": 3.0,
    "new_flood_pct_of_valid": 12.0, "new_flood_share_of_water_pct": 75.0, "mean_confidence": 0.82,
    "area_method": "test", "severity": None, "zone_count": 3, "warnings": [],
    "mask_url": "/api/analyses/7/mask", "zones_url": "/api/analyses/7/zones",
}

EVENT = {"name": "SYNTHETIC test flood", "region_name": "Test valley", "country": "Nowhere",
         "status": "active", "start_date": "2026-10-27", "end_date": None,
         "description": "Invented for the tests. <b>Markup</b> & odd characters: অসম"}

ZONES = collection(
    _feature(_box(93.41, 26.31, 93.43, 26.33), zone_type="permanent_water"),
    _feature(_box(93.43, 26.32, 93.45, 26.34), zone_type="new_flood"),
    _feature(_box(93.44, 26.30, 93.455, 26.31), zone_type="new_flood"),
)

LAYERS = {
    "villages": collection(
        _feature({"type": "Point", "coordinates": [93.425, 26.34]}, name="Test village A", relation="inside",
                 distance_m=0),
        _feature({"type": "Point", "coordinates": [93.405, 26.345]}, name=None, relation="near", distance_m=310)),
    "roads": collection(
        _feature({"type": "LineString", "coordinates": [[93.43, 26.325], [93.45, 26.335]]}, name="Test road",
                 category="trunk", flooded_length_km=1.234, on_bridge=False),
        _feature({"type": "LineString", "coordinates": [[93.41, 26.32], [93.43, 26.32]]}, name=None,
                 category="trunk", flooded_length_km=0.058, on_bridge=True, source_ref="way/1")),
    "farmland": collection(_feature(_box(93.435, 26.335, 93.445, 26.345), flooded_area_km2=0.2)),
    "infrastructure": collection(
        _feature({"type": "Point", "coordinates": [93.44, 26.33]}, name="Test clinic", category="clinic",
                 relation="inside", distance_m=0),
        _feature({"type": "Point", "coordinates": [93.41, 26.34]}, name="Test school", category="school",
                 relation="near", distance_m=420)),
}

SUMMARY = {
    "analysis_id": 7, "zone_type": "new_flood", "compared_against": "new flood: water that is not on the baseline layer",
    "baseline_method": "jrc", "last_computed_at": datetime(2026, 11, 10, 10, 0, tzinfo=UTC),
    "villages": {"count": 2, "inside": 1, "near": 1},
    "roads": {"count": 1, "flooded_length_km": 1.234, "bridges": {"count": 1, "length_km": 0.058}},
    "farmland": {"count": 1, "flooded_area_km2": 0.2},
    "infrastructure": {"count": 2, "inside": 1, "near": 1,
                       "by_category": {"clinic": {"inside": 1, "near": 0}, "school": {"inside": 0, "near": 1}}},
    "note": "test",
}

ACTIONS = [
    {"action_id": 1, "event_id": 3, "title": "Close the test bridge", "description": None,
     "action_type": "road_closure", "priority": "high", "status": "planned", "longitude": 93.43, "latitude": 26.32,
     "assigned_to": 1, "assigned_to_username": "admin", "created_by": 1,
     "due_at": datetime(2026, 11, 12, 8, 0, tzinfo=UTC), "created_at": datetime(2026, 11, 10, tzinfo=UTC),
     "updated_at": datetime(2026, 11, 10, tzinfo=UTC)},
    {"action_id": 2, "event_id": 3, "title": "Far away <pin>", "description": None, "action_type": "shelter",
     "priority": "critical", "status": "in_progress", "longitude": 95.0, "latitude": 27.0, "assigned_to": None,
     "assigned_to_username": None, "created_by": 1, "due_at": None, "created_at": datetime(2026, 11, 10, tzinfo=UTC),
     "updated_at": datetime(2026, 11, 10, tzinfo=UTC)},
]


def sample_data(with_impact=True, with_actions=True, baseline=True):
    """A fresh copy of the synthetic report data (the builder must not change it, and tests may)."""
    import copy
    from backend.services import severity as severity_rules

    analysis = copy.deepcopy(ANALYSIS)
    summary = copy.deepcopy(SUMMARY)
    if not baseline:
        analysis.update(baseline_method="none", permanent_water_area_km2=None, new_flood_area_km2=None,
                        new_flood_pct_of_valid=None)
        summary.update(zone_type="water", baseline_method="none")
    if not with_impact:
        summary["last_computed_at"] = None
    impact = {"summary": summary, "layers": copy.deepcopy(LAYERS) if with_impact else None}
    return {
        "generated_at": datetime(2026, 11, 14, 4, 0, tzinfo=UTC), "generated_by": "viewer_x",
        "analysis": analysis, "event": copy.deepcopy(EVENT), "source_name": "SYNTHETIC source",
        "acquired_at": None, "zones": copy.deepcopy(ZONES), "impact": impact,
        "severity": severity_rules.classify(analysis, summary),
        "actions": copy.deepcopy(ACTIONS) if with_actions else [],
    }
