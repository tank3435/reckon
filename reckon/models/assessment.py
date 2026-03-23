"""
RiskAssessment: immutable record produced by a scoring run.
TierScore: per-tier breakdown stored with each assessment.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from reckon.db import Base


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Composite score 0–100 (higher = worse)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Human-readable severity label
    severity_label: Mapped[str] = mapped_column(String(32), nullable=False)
    # Prose summary and response recommendations (Markdown)
    summary: Mapped[str] = mapped_column(Text, default="")
    recommendations: Mapped[str] = mapped_column(Text, default="")
    # How many indicators fed into this run
    indicator_count: Mapped[int] = mapped_column(Integer, default=0)
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    tier_scores: Mapped[list["TierScore"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class TierScore(Base):
    __tablename__ = "tier_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    indicator_count: Mapped[int] = mapped_column(Integer, default=0)

    assessment: Mapped["RiskAssessment"] = relationship(back_populates="tier_scores")
