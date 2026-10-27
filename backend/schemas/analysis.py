"""GeoFlood AI backend - response shapes for analyses and dashboard statistics."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from backend.schemas.prediction import DETECTS


class AnalysisOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())    # allow field names starting with "model_"

    analysis_id: int
    event_id: int
    image_id: int
    source_id: int
    original_filename: str
    status: str
    created_at: datetime

    model_name: str
    threshold: float
    detects: str = DETECTS

    baseline_method: str                    # 'none' or 'jrc'
    height_px: Optional[int]
    width_px: Optional[int]
    crs: Optional[str]
    bounds_wgs84: list[float]               # [west, south, east, north] in degrees

    valid_area_km2: Optional[float]
    nodata_area_km2: Optional[float]
    water_pixels: Optional[int]
    water_area_km2: Optional[float]         # all detected water
    water_pct_of_valid: Optional[float]
    permanent_water_area_km2: Optional[float]     # None when no baseline was given
    new_flood_area_km2: Optional[float]           # None when no baseline was given
    new_flood_pct_of_valid: Optional[float]
    new_flood_share_of_water_pct: Optional[float]
    mean_confidence: Optional[float]        # average model certainty on water pixels, not an accuracy
    area_method: Optional[str]
    severity: Optional[str]                 # filled in Phase 25

    zone_count: int
    warnings: list[str]
    mask_url: str
    zones_url: str


class DashboardOut(BaseModel):
    events: int
    images: int
    analyses_completed: int
    analyses_with_baseline: int
    zone_polygons: int
    total_water_area_km2: float
    total_permanent_water_area_km2: float
    total_new_flood_area_km2: float         # only analyses that had a baseline
    latest_analysis_at: Optional[datetime]
    note: str
