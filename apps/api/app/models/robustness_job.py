from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RobustnessJob(Base):
    __tablename__ = "robustness_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|completed|failed
    strategy_payload: Mapped[Any] = mapped_column(JSON)
    tests_requested: Mapped[Any] = mapped_column(JSON)  # list[str]
    peer_tickers: Mapped[Any] = mapped_column(JSON, nullable=True)
    parameter_grid: Mapped[Any] = mapped_column(JSON, nullable=True)
    results: Mapped[Any] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
