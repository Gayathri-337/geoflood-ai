"""GeoFlood AI backend - login tokens and the 'who is calling?' dependencies."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database import get_db
from backend.services import users as user_service

ALGORITHM = "HS256"
MAX_BIGINT = 2 ** 63 - 1
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
_BEARER = {"WWW-Authenticate": "Bearer"}


@dataclass(frozen=True)
class AuthUser:
    """The logged-in user, as stored in the database."""
    user_id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime


def create_access_token(user_id: int, settings: Settings,
                        expires_delta: Optional[timedelta] = None) -> tuple[str, int]:
    """Return (token, lifetime in seconds). The token holds only the user id and the expiry time."""
    delta = expires_delta if expires_delta is not None else timedelta(minutes=settings.access_token_minutes)
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": str(user_id), "iat": now, "exp": now + delta},
                       settings.secret_key, algorithm=ALGORITHM)
    return token, int(delta.total_seconds())


def decode_access_token(token: str, settings: Settings) -> int:
    """Return the user id in a valid token. Raises jwt.InvalidTokenError or ValueError otherwise."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM],
                         options={"require": ["exp", "sub"]})
    user_id = int(payload["sub"])
    if not 0 < user_id <= MAX_BIGINT:
        raise ValueError("user id out of range")
    return user_id


def current_user(token: Optional[str] = Depends(oauth2_scheme),
                 db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)) -> AuthUser:
    """The logged-in user, or a 401. The role and active flag are read from the database on every request."""
    if not token:
        raise HTTPException(401, "Not logged in.", headers=_BEARER)
    try:
        user_id = decode_access_token(token, settings)
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, "Your session is invalid or has expired. Please log in again.", headers=_BEARER)
    row = user_service.get_by_id(db, user_id)
    if row is None or not row["is_active"]:
        raise HTTPException(401, "Your session is invalid or has expired. Please log in again.", headers=_BEARER)
    return AuthUser(**row)


def require_role(minimum: str):
    """A dependency that allows users with the given role or a higher one."""
    needed = user_service.ROLE_RANK[minimum]

    def dependency(user: AuthUser = Depends(current_user)) -> AuthUser:
        if user_service.ROLE_RANK[user.role] < needed:
            raise HTTPException(403, f"This action needs the '{minimum}' role or higher.")
        return user

    return dependency


require_analyst = require_role("analyst")
require_admin = require_role("admin")

