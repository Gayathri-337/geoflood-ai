"""GeoFlood AI backend - login, current user, password change."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database import get_db
from backend.schemas.auth import PasswordChange, TokenOut, UserOut
from backend.security import AuthUser, create_access_token, current_user
from backend.services import users as user_service
from backend.services.passwords import DUMMY_HASH, MAX_LENGTH, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

BAD_LOGIN = "Incorrect username or password."


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings)):
    """Log in with a username and password (form fields). Returns a bearer token."""
    row = user_service.get_for_login(db, user_service.normalize_username(form.username))
    # One password check always runs, even for an unknown user, so the response time
    # does not reveal which usernames exist.
    stored = row["password_hash"] if row else DUMMY_HASH
    password_ok = len(form.password) <= MAX_LENGTH and verify_password(form.password, stored)
    if row is None or not password_ok:
        raise HTTPException(401, BAD_LOGIN, headers={"WWW-Authenticate": "Bearer"})
    if not row["is_active"]:
        raise HTTPException(403, "This account is disabled. Contact an administrator.")
    token, expires_in = create_access_token(row["user_id"], settings)
    return TokenOut(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserOut)
def me(user: AuthUser = Depends(current_user)):
    """Who is logged in?"""
    return asdict(user)


@router.post("/change-password", status_code=204, response_class=Response)
def change_password(payload: PasswordChange,
                    user: AuthUser = Depends(current_user),
                    db: Session = Depends(get_db)):
    """Change your own password. Tokens issued earlier stay valid until they expire."""
    row = user_service.get_for_login(db, user.username)
    if row is None or not verify_password(payload.current_password, row["password_hash"]):
        raise HTTPException(400, "The current password is incorrect.")
    if payload.new_password == payload.current_password:
        raise HTTPException(422, "The new password must be different from the current one.")
    try:
        user_service.set_password(db, user.user_id, payload.new_password, user.username)
    except ValueError as err:
        raise HTTPException(422, str(err))
    db.commit()
    return Response(status_code=204)
