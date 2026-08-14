"""
Strategy Definition Module
Defines trading strategies with entry/exit rules
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import polars as pl


@dataclass
class StrategyConfig:
    """Configuration for a trading strategy"""
    name: str
    description: str
    holding_period: int = 5  # Default 5 days
    stop_loss_pct: float = 0.08  # 8% stop loss
    take_profit_pct: float = 0.15  # 15% take profit
    min_price: float = 5.0
    min_volume: int = 100000
    transaction_cost_pct: float = 0.001  # 0.1% per trade
    slippage_pct: float = 0.0005  # 0.05% slippage

    # Universe filters
    min_market_cap: float = 300_000_000  # $300M
    max_market_cap: Optional[float] = None

    # Position sizing
    max_position_pct: float = 0.05  # 5% max per position
    max_portfolio_positions: int = 20


class Strategy(ABC):
    """Abstract base class for trading strategies"""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.name = config.name

    @abstractmethod
    def generate_signals(self, data: pl.DataFrame) -> pl.DataFrame:
        """
        Generate trading signals from price/feature data

        Args:
             DataFrame with OHLCV and features

        Returns:
            DataFrame with columns: timestamp, ticker, signal, score
            signal: -1 (short), 0 (none), 1 (long)
            score: confidence score 0-100
        """
        pass

    @abstractmethod
    def get_required_features(self) -> List[str]:
        """Return list of required feature columns"""
        pass

    def validate_data(self, data: pl.DataFrame) -> bool:
        """Validate that data has required features"""
        required = self.get_required_features()
        missing = [f for f in required if f not in data.columns]
        if missing:
            raise ValueError(f"Missing required features: {missing}")
        return True


class MomentumBreakoutStrategy(Strategy):
    """
    First official strategy: Momentum Breakout

    Entry criteria:
    - Price > SMA50 > SMA200 (uptrend)
    - 20-day momentum positive
    - Relative strength vs SPY strong
    - Price near 20-day high
    - Volume above average
    - Market regime favorable
    """

    def __init__(self, config: Optional[StrategyConfig] = None):
        if config is None:
            config = StrategyConfig(
                name="Momentum Breakout",
                description="Long-only momentum breakout strategy",
                holding_period=5,
                stop_loss_pct=0.08,
                take_profit_pct=0.15,
            )
        super().__init__(config)

        # Scoring weights (configurable)
        self.weights = {
            "relative_strength": 0.30,
            "momentum": 0.20,
            "volume": 0.20,
            "breakout_quality": 0.15,
            "trend_alignment": 0.15,
        }

    def get_required_features(self) -> List[str]:
        return [
            "close", "sma_20", "sma_50", "sma_200",
            "rsi_14", "roc_20", "relative_strength_spy",
            "volume_sma_20_ratio", "distance_from_20d_high"
        ]

    def generate_signals(self, data: pl.DataFrame) -> pl.DataFrame:
        """Generate momentum breakout signals"""
        self.validate_data(data)

        # Calculate component scores (0-100) using proper Polars expressions
        df = data.with_columns([
            # Relative strength score (higher RS = higher score)
            (pl.col("relative_strength_spy").clip(0, 2) * 50).clip(0, 100).alias("rs_score"),

            # Momentum score (ROC20 > 0 gets points)
            ((50 + pl.col("roc_20") * 5).clip(0, 100)).alias("momentum_score"),

            # Volume score (rel volume > 1 gets points)
            (pl.col("volume_sma_20_ratio").clip(0, 3) * 33).clip(0, 100).alias("volume_score"),

            # Breakout quality (closer to high = better)
            ((100 + pl.col("distance_from_20d_high") * 500).clip(0, 100)).alias("breakout_score"),

            # Trend alignment (price > sma50 > sma200)
            (((pl.col("close") > pl.col("sma_50")) &
             (pl.col("sma_50") > pl.col("sma_200"))).cast(pl.Int32) * 100).alias("trend_score"),
        ])

        # Calculate composite score
        df = df.with_columns([
            (
                pl.col("rs_score") * self.weights["relative_strength"] +
                pl.col("momentum_score") * self.weights["momentum"] +
                pl.col("volume_score") * self.weights["volume"] +
                pl.col("breakout_score") * self.weights["breakout_quality"] +
                pl.col("trend_score") * self.weights["trend_alignment"]
            ).alias("composite_score")
        ])

        # Generate signals (score > 70 = buy signal)
        df = df.with_columns([
            (pl.col("composite_score") >= 70).cast(pl.Int32).alias("signal"),
            pl.col("composite_score").clip(0, 100).alias("score")
        ])

        return df.select([
            "timestamp", "ticker", "signal", "score",
            "rs_score", "momentum_score", "volume_score",
            "breakout_score", "trend_score", "composite_score"
        ])
