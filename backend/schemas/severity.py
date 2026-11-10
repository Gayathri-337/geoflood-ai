"""GeoFlood AI backend - response shape of the severity classification."""

from typing import Literal, Optional

from pydantic import BaseModel

Level = Literal["low", "moderate", "high", "severe"]


class IndicatorOut(BaseModel):
    key: str
    label: str
    unit: str
    value: Optional[float]            # None when the impact has not been computed
    level: Optional[Level]
    thresholds: dict[str, Optional[float]]


class SeverityOut(BaseModel):
    analysis_id: int
    level: Level
    driven_by: list[str]              # the indicator keys that decided the overall level
    impact_included: bool
    stored_severity: Optional[Level]  # what is saved in the database (may differ from `level`)
    indicators: list[IndicatorOut]
    note: str
