"""GeoFlood AI backend - the response of a prediction run."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

DETECTS = "surface water (rivers and lakes included), not only newly flooded land"


class PredictionOut(BaseModel):
    # allow field names that start with "model_"
    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    original_filename: str
    created_at: datetime
    processing_seconds: float

    model_checkpoint: str
    threshold: float
    detects: str = DETECTS

    height_px: int
    width_px: int
    crs: str
    bounds_wgs84: list[float]            # [west, south, east, north] in degrees

    valid_pixels: int
    water_pixels: int
    mean_water_confidence: float         # the model's average certainty on water pixels, not an accuracy
    valid_area_km2: float
    nodata_area_km2: float
    water_area_km2: float
    water_pct_of_valid: float            # share of the valid AREA that is water
    area_method: str

    warnings: list[str]
    mask_url: str
