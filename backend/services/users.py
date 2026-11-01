"""GeoFlood AI backend - user accounts. All SQL for the users table lives here."""

import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.services.passwords import check_password_rules, hash_password

ROLES = ("viewer", "analyst", "admin")                  # lowest to highest
ROLE_RANK = {role: rank for rank, role in enumerate(ROLES)}

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,49}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PUBLIC_COLUMNS = "user_id, username, email, full_name, role, is_active, created_at"
UPDATABLE = ("role", "is_active", "full_name")          # the only columns an update may touch


def normalize_username(value: str) -> str:
    return value.strip().lower()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def _clean_name(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def create_user(db: Session, *, username: str, email: str, password: str,
                role: str = "viewer", full_name: Optional[str] = None) -> dict:
    """
    Insert a user and return its public fields. Does NOT commit.
    Raises ValueError for invalid input (before touching the database) and
    sqlalchemy IntegrityError if the username or email is already taken.
    """
    username, email, full_name = normalize_username(username), normalize_email(email), _clean_name(full_name)
    if not USERNAME_PATTERN.match(username):
        raise ValueError("The username must be 3-50 characters: lowercase letters, digits, '.', '_' or '-', "
                         "starting with a letter or digit.")
    if len(email) > 255 or not EMAIL_PATTERN.match(email):
        raise ValueError("The email address is not valid.")
    if full_name is not None and len(full_name) > 100:
        raise ValueError("The full name must be at most 100 characters.")
    if role not in ROLE_RANK:
        raise ValueError(f"The role must be one of: {', '.join(ROLES)}.")
    check_password_rules(password, username)

    row = db.execute(
        text(f"INSERT INTO users (username, email, password_hash, full_name, role) "
             f"VALUES (:username, :email, :hash, :full_name, :role) RETURNING {PUBLIC_COLUMNS}"),
        {"username": username, "email": email, "hash": hash_password(password),
         "full_name": full_name, "role": role}).mappings().one()
    return dict(row)


def get_by_id(db: Session, user_id: int) -> Optional[dict]:
    row = db.execute(text(f"SELECT {PUBLIC_COLUMNS} FROM users WHERE user_id = :id"),
                     {"id": user_id}).mappings().first()
    return dict(row) if row else None


def get_for_login(db: Session, username: str) -> Optional[dict]:
    """Like get_by_id but by username and including the password hash. Never send this to a client."""
    row = db.execute(text(f"SELECT {PUBLIC_COLUMNS}, password_hash FROM users WHERE username = :u"),
                     {"u": username}).mappings().first()
    return dict(row) if row else None


def list_users(db: Session, limit: int, offset: int) -> list[dict]:
    rows = db.execute(text(f"SELECT {PUBLIC_COLUMNS} FROM users ORDER BY user_id LIMIT :limit OFFSET :offset"),
                      {"limit": limit, "offset": offset}).mappings()
    return [dict(r) for r in rows]


def count_other_active_admins(db: Session, user_id: int) -> int:
    return db.execute(text("SELECT count(*) FROM users WHERE role = 'admin' AND is_active AND user_id <> :id"),
                      {"id": user_id}).scalar_one()


def update_user(db: Session, user_id: int, changes: dict) -> Optional[dict]:
    """Apply role / is_active / full_name changes. Does NOT commit. Returns None if there is no such user."""
    changes = dict(changes)
    if "full_name" in changes:
        changes["full_name"] = _clean_name(changes["full_name"])      # "" clears the name
    columns = [c for c in UPDATABLE if c in changes]                   # column names come from the constant above
    assignments = ", ".join(f"{c} = :{c}" for c in columns)
    row = db.execute(text(f"UPDATE users SET {assignments} WHERE user_id = :id RETURNING {PUBLIC_COLUMNS}"),
                     {**{c: changes[c] for c in columns}, "id": user_id}).mappings().first()
    return dict(row) if row else None


def set_password(db: Session, user_id: int, new_password: str, username: str) -> None:
    """Check the rules, hash and store a new password. Does NOT commit. Raises ValueError for a weak one."""
    check_password_rules(new_password, username)
    db.execute(text("UPDATE users SET password_hash = :h WHERE user_id = :id"),
               {"h": hash_password(new_password), "id": user_id})
