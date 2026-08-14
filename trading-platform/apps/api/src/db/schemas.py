"""Pydantic schemas for API request/response validation."""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class AssetStatus(str, Enum):
    active = "active"
    delisted = "delisted"
    suspended = "suspended"


class SignalDirection(str, Enum):
    long = "long"
    short = "short"
    neutral = "neutral"


# ============ Asset Schemas ============

class AssetBase(BaseModel):
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[int] = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[int] = None
    status: Optional[AssetStatus] = None


class AssetResponse(AssetBase):
    id: int
    status: AssetStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Price Schemas ============

class PriceDailyBase(BaseModel):
    time: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    adjusted_close: Optional[float] = None


class PriceDailyCreate(PriceDailyBase):
    asset_id: int


class PriceDailyResponse(PriceDailyBase):
    id: int
    asset_id: int
    dollar_volume: Optional[float] = None

    class Config:
        from_attributes = True


# ============ Feature Schemas ============

class FeatureDailyBase(BaseModel):
    time: datetime
    feature_name: str
    feature_value: float


class FeatureDailyCreate(FeatureDailyBase):
    asset_id: int


class FeatureDailyResponse(FeatureDailyBase):
    id: int
    asset_id: int

    class Config:
        from_attributes = True


# ============ Market Regime Schemas ============

class MarketRegimeBase(BaseModel):
    date: date
    regime_label: str
    confidence: Optional[float] = None
    metrics_json: Optional[Dict[str, Any]] = None


class MarketRegimeResponse(MarketRegimeBase):
    created_at: datetime

    class Config:
        from_attributes = True


# ============ News Schemas ============

class NewsEventBase(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    published_at: datetime


class NewsEventCreate(NewsEventBase):
    asset_id: Optional[int] = None


class NewsEventResponse(NewsEventBase):
    id: int
    asset_id: Optional[int] = None
    llm_sentiment: Optional[float] = None
    llm_importance: Optional[float] = None
    llm_catalysts: Optional[Dict[str, Any]] = None
    llm_explanation: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Strategy Schemas ============

class StrategyBase(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class StrategyCreate(StrategyBase):
    pass


class StrategyUpdate(BaseModel):
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class StrategyResponse(StrategyBase):
    id: int
    version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Signal Schemas ============

class SignalBase(BaseModel):
    generated_at: datetime
    score: float
    direction: Optional[SignalDirection] = None
    suggested_entry: Optional[float] = None
    suggested_stop: Optional[float] = None
    suggested_target: Optional[float] = None
    expected_return: Optional[float] = None
    confidence: Optional[str] = None
    explanation: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SignalCreate(SignalBase):
    asset_id: int
    strategy_id: Optional[int] = None
    model_version: Optional[str] = None


class SignalResponse(SignalBase):
    id: int
    asset_id: int
    strategy_id: Optional[int] = None
    model_version: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SignalWithAsset(SignalResponse):
    asset: AssetResponse


# ============ Portfolio Schemas ============

class PaperPortfolioBase(BaseModel):
    name: str = "Default Portfolio"
    initial_cash: float


class PaperPortfolioCreate(PaperPortfolioBase):
    pass


class PaperPortfolioResponse(PaperPortfolioBase):
    id: int
    current_cash: Optional[float] = None
    total_equity: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaperPositionBase(BaseModel):
    quantity: float
    entry_price: float
    entry_date: datetime
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    notes: Optional[str] = None


class PaperPositionCreate(PaperPositionBase):
    portfolio_id: int
    asset_id: int
    strategy_id: Optional[int] = None
    signal_id: Optional[int] = None


class PaperPositionResponse(PaperPositionBase):
    id: int
    portfolio_id: int
    asset_id: int
    exit_price: Optional[float] = None
    exit_date: Optional[datetime] = None
    status: str
    pnl_realized: Optional[float] = None
    strategy_id: Optional[int] = None
    signal_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PortfolioSnapshotBase(BaseModel):
    time: datetime
    cash: Optional[float] = None
    equity: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    exposure: Optional[float] = None


class PortfolioSnapshotResponse(PortfolioSnapshotBase):
    portfolio_id: int

    class Config:
        from_attributes = True


# ============ Model Schemas ============

class ModelBase(BaseModel):
    name: str
    model_type: Optional[str] = None
    version: str


class ModelCreate(ModelBase):
    training_start_date: Optional[datetime] = None
    training_end_date: Optional[datetime] = None
    test_start_date: Optional[datetime] = None
    test_end_date: Optional[datetime] = None
    metrics_json: Optional[Dict[str, Any]] = None
    feature_list: Optional[List[str]] = None
    model_path: Optional[str] = None


class ModelResponse(ModelBase):
    id: int
    training_start_date: Optional[datetime] = None
    training_end_date: Optional[datetime] = None
    test_start_date: Optional[datetime] = None
    test_end_date: Optional[datetime] = None
    metrics_json: Optional[Dict[str, Any]] = None
    feature_list: Optional[List[str]] = None
    model_path: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Experiment Schemas ============

class ExperimentBase(BaseModel):
    name: str
    hypothesis: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class ExperimentCreate(ExperimentBase):
    pass


class ExperimentResponse(ExperimentBase):
    id: int
    results_json: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============ Dashboard/Summary Schemas ============

class MarketDashboardResponse(BaseModel):
    spy_trend: str
    qqq_trend: str
    vix_level: Optional[float] = None
    market_breadth: Optional[str] = None
    sector_strength: Optional[Dict[str, float]] = None
    market_regime: str
    market_score: float
    risk_score: float
    last_updated: datetime


class OpportunityRank(BaseModel):
    rank: int
    ticker: str
    asset_id: int
    score: float
    setup_type: str
    confidence: str
    explanation: Optional[str] = None
    sub_scores: Optional[Dict[str, float]] = None
    generated_at: Optional[datetime] = None


class StockOpportunity(BaseModel):
    """Schema for scanner opportunities response."""
    rank: int
    ticker: str
    asset_id: int
    score: float
    setup_type: str
    confidence: str
    explanation: Optional[str] = None
    sub_scores: Optional[Dict[str, float]] = None
    generated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OpportunityScannerResponse(BaseModel):
    opportunities: List[StockOpportunity]
    total_count: int
    last_updated: datetime


class StockDetailResponse(BaseModel):
    ticker: str
    name: str
    sector: str
    industry: str
    current_price: float
    quant_score: float
    strategy_scores: Dict[str, float]
    why_high_score: List[str]
    risks: List[str]
    trade_model: Optional[Dict[str, Any]] = None
    recent_news: List[NewsEventResponse]
    fundamentals: Optional[Dict[str, Any]] = None


class BacktestResultResponse(BaseModel):
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    num_trades: int
    avg_holding_period: int
    benchmark_return: float
    alpha: float
    beta: float
    equity_curve: List[Dict[str, Any]]
    trades: List[Dict[str, Any]]
