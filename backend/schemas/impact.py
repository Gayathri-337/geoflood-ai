"""GeoFlood AI backend - response shapes for impact analysis."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ImpactRunOut(BaseModel):
    analysis_id: int
    zone_type: str                      # 'water' or 'new_flood'
    compared_against: str
    near_m: float                       # distance used for "near the flood" (villages and infrastructure)
    villages: int
    roads: int                          # flooded roads, bridges NOT included
    bridges: int = 0                    # roads on bridges over the detected water (shown, not counted as flooded)
    farmland: int
    infrastructure: int


class VillageSummary(BaseModel):
    count: int
    inside: int
    near: int


class BridgeSummary(BaseModel):
    count: int
    length_km: float                    # length of the bridges that lies over the detected water


class RoadSummary(BaseModel):
    count: int                          # flooded roads, bridges NOT included
    flooded_length_km: float
    bridges: BridgeSummary


class FarmlandSummary(BaseModel):
    count: int
    flooded_area_km2: float


class InfrastructureSummary(BaseModel):
    count: int
    inside: int
    near: int
    by_category: dict[str, dict[str, int]]      # e.g. {"hospital": {"inside": 1, "near": 0}}


class ImpactSummaryOut(BaseModel):
    analysis_id: int
    zone_type: str
    compared_against: str
    baseline_method: str
    last_computed_at: Optional[datetime]
    villages: VillageSummary
    roads: RoadSummary
    farmland: FarmlandSummary
    infrastructure: InfrastructureSummary
    note: str