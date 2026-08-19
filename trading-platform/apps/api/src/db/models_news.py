"""
News and Catalyst Database Models.

Stores raw news articles, LLM-processed events, and catalyst scores.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from apps.api.src.core.database import Base


class NewsSource(Base):
    """News provider source configuration."""
    __tablename__ = "news_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    config_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    articles = relationship("NewsArticle", back_populates="source")


class NewsArticle(Base):
    """Raw news article data."""
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("news_sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)

    # Content
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Timestamps
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    revision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # external_id is the provider's source_event_id. Timing remains NULL until
    # supplied by the source; ingestion must not fabricate availability.

    # Processing status
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    source = relationship("NewsSource", back_populates="articles")
    events = relationship("NewsEvent", back_populates="article", cascade="all, delete-orphan")

    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class TickerNewsLink(Base):
    """Many-to-many link between articles and tickers."""
    __tablename__ = "ticker_news_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("news_articles.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=1.0)

    article = relationship("NewsArticle", backref="ticker_links")


class NewsEvent(Base):
    """LLM-structured event extracted from a news article."""
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("news_articles.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), index=True, nullable=False)

    # LLM Extracted Data
    event_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    # Types: earnings_beat, earnings_miss, guidance_raise, guidance_cut, upgrade, downgrade,
    # acquisition, lawsuit, product_launch, etc.

    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Range: -1.0 (very negative) to 1.0 (very positive)

    importance_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Range: 0.0 (irrelevant) to 1.0 (market moving)

    surprise_magnitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # For earnings/events with numbers: e.g., 0.15 for 15% beat

    expected_duration: Mapped[str] = mapped_column(String(20), default="intraday")
    # intraday, multi_day, multi_week, structural

    # Raw LLM output for debugging/audit
    llm_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_catalysts: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    # e.g., ["revenue_beat", "guidance_raise", "margin_expansion"]

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    article = relationship("NewsArticle", back_populates="events")

    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class CatalystScore(Base):
    """Daily aggregated catalyst score per ticker."""
    __tablename__ = "catalyst_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Aggregated Metrics
    net_sentiment: Mapped[float] = mapped_column(Float, default=0.0)
    # Weighted sum of sentiment * importance for the day

    max_importance: Mapped[float] = mapped_column(Float, default=0.0)
    # Highest single event importance that day

    event_count: Mapped[int] = mapped_column(Integer, default=0)
    bullish_events: Mapped[int] = mapped_column(Integer, default=0)
    bearish_events: Mapped[int] = mapped_column(Integer, default=0)

    # Composite Score (0-100)
    composite_score: Mapped[float] = mapped_column(Float, default=50.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        {'sqlite_autoincrement': True},
    )
