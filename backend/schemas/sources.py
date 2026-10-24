"""GeoFlood AI backend - response shape for satellite sources."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: int
    name: str
    platform: str
    sensor_type: str
    provider: Optional[str]
    description: Optional[str]
    created_at: datetime
