from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SymbolCache(Base):
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    instrument_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # columns added via run_startup_migrations on existing deployments
    exchange: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    alpha_vantage_match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=True)
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, server_default=func.now(), onupdate=func.now()
    )
    # PRD-06: fundamental metadata (added via startup migration)
    sector: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    market_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    beta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    week_52_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    week_52_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    employees: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    market_cap_category: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fundamentals_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
