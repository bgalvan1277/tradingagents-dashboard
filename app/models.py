"""SQLAlchemy ORM models for all database tables.

Configured for MySQL (uses JSON instead of JSONB, appropriate string lengths).
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String, Integer, Boolean, Text, Date, DateTime, Numeric,
    ForeignKey, Index,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Ticker(Base):
    """A stock ticker on the watchlist."""
    __tablename__ = "tickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="watching")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    model_tier: Mapped[str] = mapped_column(String(10), default="pro")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    watchlist_entry: Mapped[Optional["WatchlistEntry"]] = relationship(
        back_populates="ticker", uselist=False, cascade="all, delete-orphan"
    )


class WatchlistEntry(Base):
    """Position and grouping for a ticker in the watchlist."""
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tickers.id", ondelete="CASCADE"), unique=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    group_name: Mapped[str] = mapped_column(String(50), default="default")
    frequency: Mapped[str] = mapped_column(String(10), default="daily")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    ticker: Mapped["Ticker"] = relationship(back_populates="watchlist_entry")


class Run(Base):
    """A single analysis run for a ticker on a given date."""
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    run_timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    final_recommendation: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    one_line_thesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0")
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    details: Mapped[Optional["RunDetail"]] = relationship(
        back_populates="run", uselist=False, cascade="all, delete-orphan"
    )
    cost_entries: Mapped[list["CostLog"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_runs_date", "run_date"),
        Index("idx_runs_status", "status"),
    )


class RunDetail(Base):
    """Full agent reports and state for a completed run."""
    __tablename__ = "run_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("runs.id", ondelete="CASCADE"), unique=True
    )

    # Individual analyst reports
    market_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sentiment_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    news_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fundamentals_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Bull/Bear investment debate
    bull_case_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bear_case_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    debate_judge_decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Risk assessment team
    risk_aggressive: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_conservative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_neutral: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_judge_decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Synthesis
    investment_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trader_investment_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_trade_decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Full state for audit (JSON for MySQL instead of JSONB)
    full_state_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    run: Mapped["Run"] = relationship(back_populates="details")


class CostLog(Base):
    """Token usage and cost per LLM call within a run."""
    __tablename__ = "cost_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    run: Mapped[Optional["Run"]] = relationship(back_populates="cost_entries")

    __table_args__ = (
        Index("idx_cost_log_timestamp", "timestamp"),
    )


class CronLog(Base):
    """Log entry for each daily cron execution."""
    __tablename__ = "cron_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tickers_attempted: Mapped[int] = mapped_column(Integer, default=0)
    tickers_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    tickers_failed: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0")
    )
    error_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    duration_seconds: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
