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
    roads: int
    farmland: int
    infrastructure: int


class VillageSummary(BaseModel):
    count: int
    inside: int
    near: int


class RoadSummary(BaseModel):
    count: int
    flooded_length_km: float


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

