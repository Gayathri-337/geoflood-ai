"""
GeoFlood AI backend - SQLAlchemy models.

Only the two tables used in Phase 15. The geometry columns of disaster_events
(area_of_interest) and the audit column created_by are left out on purpose; they are added
when the map endpoints are built in Phase 17. Unmapped columns stay NULL on insert.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SatelliteSource(Base):
    __tablename__ = "satellite_sources"

    source_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    platform: Mapped[str] = mapped_column(String(50))
    sensor_type: Mapped[str] = mapped_column(String(10))
    provider: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DisasterEvent(Base):
    __tablename__ = "disaster_events"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    region_name: Mapped[Optional[str]] = mapped_column(String(150))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(12))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
