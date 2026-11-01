"""GeoFlood AI backend - request and response shapes for accounts."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["viewer", "analyst", "admin"]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int                         # seconds


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    email: str
    full_name: Optional[str]
    role: Role
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    # The password has no length limits here on purpose: its rules are checked in the service, so a
    # rejected password is never repeated back in the error response.
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=255)
    password: str
    full_name: Optional[str] = Field(None, max_length=100)
    role: Role = "viewer"


class UserUpdate(BaseModel):
    """Send only what should change. For full_name, send an empty string to clear it."""
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    full_name: Optional[str] = Field(None, max_length=100)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
