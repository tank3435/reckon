"""
LocationProfile: a user-queried location with geocoordinates.
SurvivalResource: a nearby resource associated with a location query.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from reckon.db import Base


class ResourceType(str):
    FRESHWATER = "freshwater"
    EVACUATION_ROUTE = "evacuation_route"
    NUCLEAR_TARGET = "nuclear_target"
    SHELTER = "shelter"
    HOSPITAL = "hospital"
    FOOD_CACHE = "food_cache"


class LocationProfile(Base):
    """Cached geocoding result for a city/zip query."""

    __tablename__ = "location_profiles"
    __table_args__ = (Index("ix_location_query", "query"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), default="")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    country_code: Mapped[str] = mapped_column(String(8), default="")
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class SurvivalResource(Base):
    """A survival-relevant resource near a location."""

    __tablename__ = "survival_resources"
    __table_args__ = (
        Index("ix_resource_location", "location_id"),
        Index("ix_resource_type", "resource_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(128), default="")
