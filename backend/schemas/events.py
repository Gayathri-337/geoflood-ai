"""GeoFlood AI backend - request and response shapes for events."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

EventStatus = Literal["monitoring", "active", "resolved"]


class EventCreate(BaseModel):
    """What a client sends to create an event."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)
    region_name: Optional[str] = Field(default=None, max_length=150)
    country: Optional[str] = Field(default=None, max_length=100)
    status: EventStatus = "monitoring"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def end_not_before_start(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class EventOut(BaseModel):
    """What the API returns."""
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    name: str
    region_name: Optional[str]
    country: Optional[str]
    status: EventStatus
    start_date: Optional[date]
    end_date: Optional[date]
    description: Optional[str]
    created_at: datetime
