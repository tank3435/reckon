"""
Indicator: a single raw data point from an external source.
Baseline: the historical reference distribution for an indicator.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from reckon.db import Base


class Tier(str, enum.Enum):
    ECONOMIC = "economic"
    POLITICAL = "political"
    MILITARY = "military"
    EXISTENTIAL = "existential"


class Indicator(Base):
    __tablename__ = "indicators"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_indicator_source_id"),
        Index("ix_indicator_tier_collected_at", "tier", "collected_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Categorization
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    # Value
    raw_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(64), default="")
    # Metadata
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class Baseline(Base):
    """Historical mean and stddev for a named indicator, used for z-score scoring."""

    __tablename__ = "baselines"
    __table_args__ = (UniqueConstraint("indicator_name", name="uq_baseline_indicator"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    indicator_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    stddev: Mapped[float] = mapped_column(Float, nullable=False)
    # Weight within its tier (0.0–1.0); tier weights are in config
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
