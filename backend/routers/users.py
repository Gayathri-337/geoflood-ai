"""GeoFlood AI backend - user management (admins only)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas.auth import UserCreate, UserOut, UserUpdate
from backend.security import MAX_BIGINT, require_admin
from backend.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
def list_users(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db)):
    return user_service.list_users(db, limit, offset)


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """Create an account. The default role is 'viewer' (the lowest)."""
    try:
        created = user_service.create_user(
            db, username=payload.username, email=payload.email, password=payload.password,
            role=payload.role, full_name=payload.full_name)
        db.commit()
    except ValueError as err:
        db.rollback()
        raise HTTPException(422, str(err))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A user with this username or email already exists.")
    return created


@router.patch("/{user_id}", response_model=UserOut)
def update_user(payload: UserUpdate,
                user_id: int = PathParam(ge=1, le=MAX_BIGINT),
                db: Session = Depends(get_db)):
    """Change a user's role, active status or full name."""
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(422, "Nothing to update: send role, is_active or full_name.")
    target = user_service.get_by_id(db, user_id)
    if target is None:
        raise HTTPException(404, f"User {user_id} not found")

    stops_being_active_admin = (target["role"] == "admin" and target["is_active"]
                                and (changes.get("role", "admin") != "admin"
                                     or changes.get("is_active", True) is False))
    if stops_being_active_admin and user_service.count_other_active_admins(db, user_id) == 0:
        raise HTTPException(409, "There must always be at least one active admin.")

    updated = user_service.update_user(db, user_id, changes)
    db.commit()
    return updated
