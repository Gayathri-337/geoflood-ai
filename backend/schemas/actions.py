"""GeoFlood AI backend - request and response shapes for emergency actions."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ActionType = Literal["evacuation", "rescue", "shelter", "relief_distribution", "road_closure", "medical", "other"]
Priority = Literal["low", "medium", "high", "critical"]
Status = Literal["planned", "in_progress", "completed", "cancelled"]
MAX_BIGINT = 2 ** 63 - 1


def _as_aware(value):
    """A time without a time zone is taken as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class LocationIn(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class ActionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    action_type: ActionType
    priority: Priority = "medium"
    status: Status = "planned"
    location: Optional[LocationIn] = None
    assigned_to: Optional[int] = Field(None, ge=1, le=MAX_BIGINT)
    due_at: Optional[datetime] = None

    @field_validator("due_at")
    @classmethod
    def due_at_has_a_zone(cls, value):
        return _as_aware(value)


class ActionUpdate(BaseModel):
    """Send only what should change. Send null to clear description, location, assigned_to or due_at."""
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    action_type: Optional[ActionType] = None
    priority: Optional[Priority] = None
    status: Optional[Status] = None
    location: Optional[LocationIn] = None
    assigned_to: Optional[int] = Field(None, ge=1, le=MAX_BIGINT)
    due_at: Optional[datetime] = None

    @field_validator("due_at")
    @classmethod
    def due_at_has_a_zone(cls, value):
        return _as_aware(value)

    @model_validator(mode="after")
    def required_fields_are_not_null(self):
        for name in ("title", "action_type", "priority", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ActionOut(BaseModel):
    action_id: int
    event_id: int
    title: str
    description: Optional[str]
    action_type: ActionType
    priority: Priority
    status: Status
    longitude: Optional[float]
    latitude: Optional[float]
    assigned_to: Optional[int]
    assigned_to_username: Optional[str]
    created_by: Optional[int]
    due_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
