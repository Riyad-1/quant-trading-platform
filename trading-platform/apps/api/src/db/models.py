"""SQLAlchemy models for the database schema."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Numeric, BigInteger,
    DateTime, Boolean, Text, ForeignKey, Enum as SQLEnum,
    JSON, UniqueConstraint, CheckConstraint, Date, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from apps.api.src.core.database import Base

# Determine PostgreSQL-specific types based on actual dialect being used
# For SQLite compatibility, use standard types since SQLite doesn't support JSONB/ARRAY/TIMESTAMPTZ
try:
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB, TIMESTAMP as TIMESTAMPTZ, ARRAY as PG_ARRAY
    # For now, default to standard types for maximum compatibility with SQLite
    JSONB = JSON
    TIMESTAMPTZ = DateTime(timezone=True)
    ARRAY = list  # Use Python list as fallback
except ImportError:
    JSONB = JSON
    TIMESTAMPTZ = DateTime(timezone=True)
    ARRAY = list


class AssetStatus(enum.Enum):
    active = "active"
    delisted = "delisted"
    suspended = "suspended"


class SignalDirection(enum.Enum):
    long = "long"
    short = "short"
    neutral = "neutral"


class Security(Base):
    """Immutable internal identity for a listed or formerly listed security."""

    __tablename__ = "securities"

    id = Column(Integer, primary_key=True, index=True)
    security_type = Column(
        String(50),
        nullable=False,
        default="COMMON_STOCK",
        server_default="COMMON_STOCK",
    )
    display_name = Column(String(255))
    primary_exchange = Column(String(50))
    currency = Column(String(10))
    country = Column(String(10))
    current_status = Column(
        String(30),
        nullable=False,
        default="UNKNOWN",
        server_default="UNKNOWN",
        index=True,
    )
    figi = Column(String(20), unique=True)
    composite_figi = Column(String(20), unique=True)
    isin = Column(String(20), unique=True)
    cusip = Column(String(20), unique=True)
    provider_identifiers = Column(JSONB)
    created_at = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMPTZ,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    symbols = relationship(
        "SecuritySymbol",
        back_populates="security",
        cascade="all, delete-orphan",
    )
    status_history = relationship(
        "SecurityStatusHistory",
        back_populates="security",
        cascade="all, delete-orphan",
    )
    universe_memberships = relationship(
        "UniverseMembership",
        back_populates="security",
        cascade="all, delete-orphan",
    )
    corporate_actions = relationship(
        "CorporateAction",
        back_populates="security",
        cascade="all, delete-orphan",
    )
    assets = relationship("Asset", back_populates="security")


class SecuritySymbol(Base):
    """Effective-dated symbol using half-open [valid_from, valid_to) ranges."""

    __tablename__ = "security_symbols"
    __table_args__ = (
        UniqueConstraint(
            "security_id",
            "ticker",
            "exchange",
            "valid_from",
            name="uq_security_symbol_start",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_security_symbol_valid_range",
        ),
        Index("ix_security_symbols_lookup", "ticker", "valid_from", "valid_to"),
    )

    id = Column(Integer, primary_key=True)
    security_id = Column(
        Integer,
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker = Column(String(20), nullable=False, index=True)
    exchange = Column(String(50))
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date)
    source = Column(String(100), nullable=False)
    created_at = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)

    security = relationship("Security", back_populates="symbols")


class SecurityStatusHistory(Base):
    """Effective-dated lifecycle/tradability status for a security."""

    __tablename__ = "security_status_history"
    __table_args__ = (
        UniqueConstraint(
            "security_id",
            "valid_from",
            name="uq_security_status_start",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_security_status_valid_range",
        ),
        Index("ix_security_status_lookup", "security_id", "valid_from", "valid_to"),
    )

    id = Column(Integer, primary_key=True)
    security_id = Column(
        Integer,
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(30), nullable=False, index=True)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date)
    source = Column(String(100), nullable=False)
    created_at = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)

    security = relationship("Security", back_populates="status_history")


class UniverseDefinition(Base):
    """Named definition of a research or scanner security universe."""

    __tablename__ = "universe_definitions"

    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    source = Column(String(100), nullable=False)
    methodology = Column(JSONB)
    created_at = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMPTZ,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    memberships = relationship(
        "UniverseMembership",
        back_populates="universe",
        cascade="all, delete-orphan",
    )


class UniverseMembership(Base):
    """Effective-dated membership using half-open [valid_from, valid_to) ranges."""

    __tablename__ = "universe_memberships"
    __table_args__ = (
        UniqueConstraint(
            "universe_id",
            "security_id",
            "valid_from",
            name="uq_universe_membership_start",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_universe_membership_valid_range",
        ),
        Index(
            "ix_universe_membership_lookup",
            "universe_id",
            "valid_from",
            "valid_to",
        ),
    )

    id = Column(Integer, primary_key=True)
    universe_id = Column(
        Integer,
        ForeignKey("universe_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    security_id = Column(
        Integer,
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date)
    source = Column(String(100), nullable=False)
    available_at = Column(TIMESTAMPTZ)
    created_at = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)

    universe = relationship("UniverseDefinition", back_populates="memberships")
    security = relationship("Security", back_populates="universe_memberships")


class CorporateAction(Base):
    """Traceable corporate-action event foundation for later processing."""

    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint("source", "source_event_id", name="uq_corporate_action_source_event"),
        Index("ix_corporate_actions_security_date", "security_id", "effective_date"),
    )

    id = Column(Integer, primary_key=True)
    security_id = Column(
        Integer,
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type = Column(String(30), nullable=False, index=True)
    event_date = Column(Date)
    effective_date = Column(Date, nullable=False, index=True)
    available_at = Column(TIMESTAMPTZ)
    source = Column(String(100), nullable=False)
    source_event_id = Column(String(200))
    action_metadata = Column(JSONB)
    created_at = Column(TIMESTAMPTZ, server_default=func.now(), nullable=False)

    security = relationship("Security", back_populates="corporate_actions")


class Asset(Base):
    """Stock or ETF asset."""
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    security_id = Column(
        Integer,
        ForeignKey("securities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255))
    exchange = Column(String(50))
    sector = Column(String(100), index=True)
    industry = Column(String(100), index=True)
    market_cap = Column(BigInteger)
    status = Column(SQLEnum(AssetStatus), default=AssetStatus.active)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    updated_at = Column(TIMESTAMPTZ, server_default=func.now(), onupdate=func.now())

    # Relationships
    security = relationship("Security", back_populates="assets")
    prices = relationship("PriceDaily", back_populates="asset", cascade="all, delete-orphan")
    features = relationship("FeatureDaily", back_populates="asset", cascade="all, delete-orphan")
    news_events = relationship("LegacyNewsEvent", back_populates="asset", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="asset", cascade="all, delete-orphan")
    positions = relationship("PaperPosition", back_populates="asset")


class PriceDaily(Base):
    """Daily price data (TimescaleDB hypertable)."""
    __tablename__ = "prices_daily"
    __table_args__ = (
        UniqueConstraint('asset_id', 'time', name='uq_asset_time'),
    )

    id = Column(Integer, primary_key=True)
    time = Column(TIMESTAMPTZ, nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    open = Column(Numeric(18, 6))
    high = Column(Numeric(18, 6))
    low = Column(Numeric(18, 6))
    close = Column(Numeric(18, 6))
    volume = Column(BigInteger)
    adjusted_close = Column(Numeric(18, 6))
    dollar_volume = Column(Numeric(24, 6))
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    # Relationship
    asset = relationship("Asset", back_populates="prices")


class FeatureDaily(Base):
    """Calculated features (TimescaleDB hypertable)."""
    __tablename__ = "features_daily"
    __table_args__ = (
        UniqueConstraint('asset_id', 'time', 'feature_name', name='uq_asset_time_feature'),
    )

    id = Column(Integer, primary_key=True)
    time = Column(TIMESTAMPTZ, nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_name = Column(String(100), nullable=False, index=True)
    feature_value = Column(Numeric(18, 8))
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    # Relationship
    asset = relationship("Asset", back_populates="features")


class MarketRegime(Base):
    """Market regime classification."""
    __tablename__ = "market_regimes"

    date = Column(DateTime(timezone=True), primary_key=True)
    regime_label = Column(String(50), nullable=False)
    confidence = Column(Numeric(5, 4))
    metrics_json = Column(JSONB)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())


class LegacyNewsEvent(Base):
    """News events with LLM analysis."""
    __tablename__ = "news_events_v1"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="SET NULL"), index=True)
    published_at = Column(TIMESTAMPTZ, nullable=False, index=True)
    headline = Column(Text)
    summary = Column(Text)
    source = Column(String(100))
    url = Column(Text)
    llm_sentiment = Column(Numeric(5, 4))
    llm_importance = Column(Numeric(5, 4))
    llm_catalysts = Column(JSONB)
    llm_explanation = Column(Text)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    # Relationship
    asset = relationship("Asset", back_populates="news_events")


class Strategy(Base):
    """Trading strategy definition."""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    version = Column(String(20), default="1.0.0")
    parameters = Column(JSONB)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    updated_at = Column(TIMESTAMPTZ, server_default=func.now(), onupdate=func.now())

    # Relationships
    signals = relationship("Signal", back_populates="strategy")
    positions = relationship("PaperPosition", back_populates="strategy")


class Signal(Base):
    """Trading signals generated by strategies/models."""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    generated_at = Column(TIMESTAMPTZ, nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"))
    model_version = Column(String(50))
    score = Column(Numeric(8, 4), index=True)
    direction = Column(SQLEnum(SignalDirection))
    suggested_entry = Column(Numeric(18, 6))
    suggested_stop = Column(Numeric(18, 6))
    suggested_target = Column(Numeric(18, 6))
    expected_return = Column(Numeric(8, 6))
    confidence = Column(String(20))
    explanation = Column(Text)
    signal_metadata = Column(JSONB)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())

    # Relationships
    asset = relationship("Asset", back_populates="signals")
    strategy = relationship("Strategy", back_populates="signals")
    positions = relationship("PaperPosition", back_populates="signal")


class PaperPortfolio(Base):
    """Paper trading portfolio."""
    __tablename__ = "paper_portfolio"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), default="Default Portfolio")
    initial_cash = Column(Numeric(18, 2), nullable=False)
    current_cash = Column(Numeric(18, 2))
    total_equity = Column(Numeric(18, 2))
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    updated_at = Column(TIMESTAMPTZ, server_default=func.now(), onupdate=func.now())

    # Relationships
    positions = relationship("PaperPosition", back_populates="portfolio", cascade="all, delete-orphan")
    snapshots = relationship("PortfolioSnapshot", back_populates="portfolio", cascade="all, delete-orphan")


class PaperPosition(Base):
    """Paper trading position."""
    __tablename__ = "paper_positions"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("paper_portfolio.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    quantity = Column(Numeric(18, 6), nullable=False)
    entry_price = Column(Numeric(18, 6), nullable=False)
    entry_date = Column(TIMESTAMPTZ, nullable=False)
    exit_price = Column(Numeric(18, 6))
    exit_date = Column(TIMESTAMPTZ)
    stop_loss = Column(Numeric(18, 6))
    target_price = Column(Numeric(18, 6))
    status = Column(String(20), default="open", index=True)
    pnl_realized = Column(Numeric(18, 2))
    strategy_id = Column(Integer, ForeignKey("strategies.id"))
    signal_id = Column(Integer, ForeignKey("signals.id"))
    notes = Column(Text)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    updated_at = Column(TIMESTAMPTZ, server_default=func.now(), onupdate=func.now())

    # Relationships
    portfolio = relationship("PaperPortfolio", back_populates="positions")
    asset = relationship("Asset", back_populates="positions")
    strategy = relationship("Strategy", back_populates="positions")
    signal = relationship("Signal", back_populates="positions")


class PortfolioSnapshot(Base):
    """Daily portfolio snapshot for equity curve."""
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint('portfolio_id', 'time', name='uq_portfolio_time'),
    )

    id = Column(Integer, primary_key=True)
    time = Column(TIMESTAMPTZ, nullable=False, index=True)
    portfolio_id = Column(Integer, ForeignKey("paper_portfolio.id", ondelete="CASCADE"), nullable=False, index=True)
    cash = Column(Numeric(18, 2))
    equity = Column(Numeric(18, 2))
    unrealized_pnl = Column(Numeric(18, 2))
    realized_pnl = Column(Numeric(18, 2))
    exposure = Column(Numeric(8, 4))

    # Relationship
    portfolio = relationship("PaperPortfolio", back_populates="snapshots")


class Model(Base):
    """ML model registry."""
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    model_type = Column(String(50))
    version = Column(String(20), nullable=False)
    training_start_date = Column(DateTime(timezone=True))
    training_end_date = Column(DateTime(timezone=True))
    test_start_date = Column(DateTime(timezone=True))
    test_end_date = Column(DateTime(timezone=True))
    metrics_json = Column(JSONB)
    feature_list = Column(Text)  # Use Text instead of ARRAY for SQLite compatibility
    model_path = Column(String(255))
    is_active = Column(Boolean, default=False)
    created_at = Column(TIMESTAMPTZ, server_default=func.now())


class Experiment(Base):
    """Research experiment tracking."""
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    hypothesis = Column(Text)
    parameters = Column(JSONB)
    results_json = Column(JSONB)
    status = Column(String(20), default="running")
    created_at = Column(TIMESTAMPTZ, server_default=func.now())
    completed_at = Column(TIMESTAMPTZ)
