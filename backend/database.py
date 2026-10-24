"""
GeoFlood AI backend - database connection.

The engine is created on first use (not at import time), so importing the app never
needs a running database. get_db() is a FastAPI dependency: it gives each request its
own session and closes it afterwards.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping: test a pooled connection before using it, so a restarted PostgreSQL recovers
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False)


def get_db() -> Iterator[Session]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
