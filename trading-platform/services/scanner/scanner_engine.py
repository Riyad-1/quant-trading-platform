"""
Quantitative Stock Scanner Engine

This module implements the core scanning logic for identifying trading opportunities
based on technical indicators, momentum, relative strength, and volume patterns.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import polars as pl
from datetime import datetime, date


class SetupType(str, Enum):
    """Types of trading setups identified by the scanner"""
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    RELATIVE_STRENGTH = "relative_strength"
    VOLUME_SURGE = "volume_surge"
    EARNINGS_MOMENTUM = "earnings_momentum"
    TREND_CONTINUATION = "trend_continuation"
    MEAN_REVERSION = "mean_reversion"


@dataclass
class StockScore:
    """Represents a scored stock opportunity"""
    ticker: str
    company_name: str
    sector: str
    industry: str
    price: float
    composite_score: float
    momentum_score: float
    breakout_score: float
    relative_strength_score: float
    volume_score: float
    fundamentals_score: float
    market_compatibility_score: float
    setup_type: SetupType
    confidence: str
    rank: int
    timestamp: datetime


class QuantScanner:
    """Main scanner engine that processes stock data and generates ranked opportunities."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # Default scoring weights (configurable)
        self.weights = {
            'momentum': self.config.get('momentum_weight', 0.30),
            'breakout': self.config.get('breakout_weight', 0.20),
            'relative_strength': self.config.get('relative_strength_weight', 0.25),
            'volume': self.config.get('volume_weight', 0.15),
            'fundamentals': self.config.get('fundamentals_weight', 0.00),
            'market_compatibility': self.config.get('market_compatibility_weight', 0.10)
        }

        # Liquidity filters
        self.min_price = self.config.get('min_price', 5.0)
        self.min_avg_volume = self.config.get('min_avg_volume', 200000)
        self.min_market_cap = self.config.get('min_market_cap', 300000000)

    def _normalize_to_score(self, col_name: str, min_val: float = -1.0, max_val: float = 1.0) -> pl.Expr:
        """Helper to normalize a column to 0-100 score range."""
        return (
            pl.col(col_name)
            .clip(min_val, max_val)
            .map_elements(
                lambda x: float(min(100, max(0, ((x - min_val) / (max_val - min_val)) * 100))) if x is not None else 50.0,
                return_dtype=pl.Float64
            )
        )

    def calculate_momentum_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """Calculate momentum score based on multiple timeframes."""
        return df.with_columns([
            self._normalize_to_score("roc_5", -0.5, 0.5).alias("momentum_5d"),
            self._normalize_to_score("roc_20", -0.5, 0.5).alias("momentum_20d"),
            self._normalize_to_score("roc_60", -0.5, 0.5).alias("momentum_60d"),
        ]).with_columns([
            (
                pl.col("momentum_5d") * 0.2 +
                pl.col("momentum_20d") * 0.5 +
                pl.col("momentum_60d") * 0.3
            ).clip(0, 100).alias("momentum_score")
        ])

    def calculate_breakout_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """Calculate breakout score based on price position and volatility."""
        # Check which columns exist
        available_cols = df.columns

        # Use dist_52w_high_pct if distance_from_52w_high doesn't exist
        high_col = "distance_from_52w_high" if "distance_from_52w_high" in available_cols else "dist_52w_high_pct"

        # Use dist_sma_20_pct if price_vs_sma20 doesn't exist
        sma20_col = "price_vs_sma20" if "price_vs_sma20" in available_cols else "dist_sma_20_pct"

        # Use dist_sma_50_pct if price_vs_sma50 doesn't exist
        sma50_col = "price_vs_sma50" if "price_vs_sma50" in available_cols else "dist_sma_50_pct"

        return df.with_columns([
            # Distance from 52-week high (closer = higher score)
            pl.col(high_col).map_elements(
                lambda x: float(max(0, 100 - abs(x * 100))) if x is not None else 50.0,
                return_dtype=pl.Float64
            ).alias("high_proximity_score"),

            # Price above SMA20 (trend alignment)
            pl.col(sma20_col).map_elements(
                lambda x: float(min(100, max(0, 50 + x * 100))) if x is not None else 50.0,
                return_dtype=pl.Float64
            ).alias("sma20_alignment"),

            # Price above SMA50 (medium trend)
            pl.col(sma50_col).map_elements(
                lambda x: float(min(100, max(0, 50 + x * 100))) if x is not None else 50.0,
                return_dtype=pl.Float64
            ).alias("sma50_alignment"),
        ]).with_columns([
            (
                pl.col("high_proximity_score") * 0.4 +
                pl.col("sma20_alignment") * 0.3 +
                pl.col("sma50_alignment") * 0.3
            ).clip(0, 100).alias("breakout_score")
        ])

    def calculate_relative_strength_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """Calculate relative strength vs SPY and sector."""
        available_cols = df.columns

        # Use rs column if relative_strength_spy doesn't exist
        spy_col = "relative_strength_spy" if "relative_strength_spy" in available_cols else "rs"

        # Default to 1.0 (neutral) if sector RS doesn't exist
        if "relative_strength_sector" in available_cols:
            sector_expr = self._normalize_to_score("relative_strength_sector", -0.3, 0.3).alias("rs_vs_sector_normalized")
        else:
            sector_expr = pl.lit(50.0).alias("rs_vs_sector_normalized")

        return df.with_columns([
            self._normalize_to_score(spy_col, -0.3, 0.3).alias("rs_vs_spy_normalized"),
            sector_expr,
        ]).with_columns([
            (
                pl.col("rs_vs_spy_normalized") * 0.6 +
                pl.col("rs_vs_sector_normalized") * 0.4
            ).clip(0, 100).alias("relative_strength_score")
        ])

    def calculate_volume_score(self, df: pl.DataFrame) -> pl.DataFrame:
        """Calculate volume score based on relative volume and trends."""
        available_cols = df.columns

        # Use relative_volume for both if volume_sma_ratio doesn't exist
        vol_ratio_col = "volume_sma_ratio" if "volume_sma_ratio" in available_cols else "relative_volume"

        return df.with_columns([
            pl.col("relative_volume").clip(0, 4).map_elements(
                lambda x: float(min(100, max(0, x * 25))) if x is not None else 50.0,
                return_dtype=pl.Float64
            ).alias("rel_volume_score"),

            pl.col(vol_ratio_col).clip(0, 3).map_elements(
                lambda x: float(min(100, max(0, x * 40))) if x is not None else 50.0,
                return_dtype=pl.Float64
            ).alias("volume_trend_score"),
        ]).with_columns([
            (
                pl.col("rel_volume_score") * 0.6 +
                pl.col("volume_trend_score") * 0.4
            ).clip(0, 100).alias("volume_score")
        ])

    def identify_setup_type(self, row: Dict[str, Any]) -> SetupType:
        """Identify the primary setup type for a stock."""
        momentum = row.get('momentum_score') or 50
        breakout = row.get('breakout_score') or 50
        rs = row.get('relative_strength_score') or 50
        volume = row.get('volume_score') or 50

        if breakout > 80 and volume > 70:
            return SetupType.BREAKOUT
        elif momentum > 75 and rs > 75:
            return SetupType.MOMENTUM
        elif rs > 85:
            return SetupType.RELATIVE_STRENGTH
        elif volume > 85 and momentum > 60:
            return SetupType.VOLUME_SURGE
        elif momentum > 70 and breakout > 60:
            return SetupType.TREND_CONTINUATION
        else:
            return SetupType.MOMENTUM

    def determine_confidence(self, composite_score: Optional[float], setup_type: SetupType) -> str:
        """Determine confidence level based on score."""
        if composite_score is None:
            return "Low"
        if composite_score >= 85:
            return "High"
        elif composite_score >= 70:
            return "Medium"
        else:
            return "Low"

    def apply_liquidity_filters(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply liquidity and quality filters."""
        # Check which columns exist
        available_cols = df.columns

        # Build filter conditions based on available columns
        conditions = [
            (pl.col("close") >= self.min_price),
            (pl.col("volume") >= self.min_avg_volume),
        ]

        # Only filter by is_active if column exists
        if "is_active" in available_cols:
            conditions.append((pl.col("is_active") == True))

        # Only filter by market_cap if column exists
        if "market_cap" in available_cols:
            conditions.append((pl.col("market_cap") >= self.min_market_cap))

        return df.filter(pl.all_horizontal(conditions))

    def scan(self,
             features_df: pl.DataFrame,
             market_regime: Optional[Dict[str, Any]] = None,
             top_n: int = 50) -> List[StockScore]:
        """Main scanning method that processes features and returns ranked opportunities."""
        df = self.apply_liquidity_filters(features_df)

        if df.height == 0:
            return []

        # Calculate all sub-scores
        df = self.calculate_momentum_score(df)
        df = self.calculate_breakout_score(df)
        df = self.calculate_relative_strength_score(df)
        df = self.calculate_volume_score(df)

        # Add placeholder fundamentals score
        df = df.with_columns(pl.lit(50.0).alias("fundamentals_score"))

        # Market compatibility score
        if market_regime and market_regime.get('regime') in ['bull', 'strong_bull', 'risk_on']:
            df = df.with_columns(
                ((pl.col("momentum_score") + pl.col("breakout_score")) / 2).alias("market_compatibility_score")
            )
        else:
            df = df.with_columns(
                ((pl.col("momentum_score") + pl.col("breakout_score")) / 2 * 0.8).alias("market_compatibility_score")
            )

        # Calculate composite score
        df = df.with_columns([
            (
                pl.col("momentum_score") * self.weights['momentum'] +
                pl.col("breakout_score") * self.weights['breakout'] +
                pl.col("relative_strength_score") * self.weights['relative_strength'] +
                pl.col("volume_score") * self.weights['volume'] +
                pl.col("fundamentals_score") * self.weights['fundamentals'] +
                pl.col("market_compatibility_score") * self.weights['market_compatibility']
            ).alias("composite_score")
        ])

        # Sort and limit
        df = df.sort("composite_score", descending=True).head(top_n)
        df = df.with_columns(pl.arange(1, df.height + 1, dtype=pl.Int32).alias("rank"))

        # Convert to list of StockScore objects
        results = []
        current_date = datetime.now()

        for row in df.to_dicts():
            setup_type = self.identify_setup_type(row)
            confidence = self.determine_confidence(row.get('composite_score'), setup_type)

            # Helper to safely round values
            def safe_round(val, default=0.0):
                return round(val, 2) if val is not None else default

            stock_score = StockScore(
                ticker=row['ticker'],
                company_name=row.get('company_name', ''),
                sector=row.get('sector', 'Unknown'),
                industry=row.get('industry', 'Unknown'),
                price=row['close'],
                composite_score=safe_round(row.get('composite_score'), 0.0),
                momentum_score=safe_round(row.get('momentum_score'), 0.0),
                breakout_score=safe_round(row.get('breakout_score'), 0.0),
                relative_strength_score=safe_round(row.get('relative_strength_score'), 0.0),
                volume_score=safe_round(row.get('volume_score'), 0.0),
                fundamentals_score=safe_round(row.get('fundamentals_score'), 0.0),
                market_compatibility_score=safe_round(row.get('market_compatibility_score'), 0.0),
                setup_type=setup_type,
                confidence=confidence,
                rank=row['rank'],
                timestamp=current_date
            )
            results.append(stock_score)

        return results

    def get_scan_summary(self, scores: List[StockScore]) -> Dict[str, Any]:
        """Generate a summary of the scan results."""
        if not scores:
            return {"total_opportunities": 0}

        setup_counts = {}
        sector_counts = {}
        confidence_counts = {"High": 0, "Medium": 0, "Low": 0}

        for score in scores:
            setup_key = score.setup_type.value
            setup_counts[setup_key] = setup_counts.get(setup_key, 0) + 1
            sector_counts[score.sector] = sector_counts.get(score.sector, 0) + 1
            confidence_counts[score.confidence] += 1

        avg_score = sum(s.composite_score for s in scores) / len(scores)

        return {
            "total_opportunities": len(scores),
            "average_score": round(avg_score, 2),
            "top_score": scores[0].composite_score if scores else 0,
            "setup_breakdown": setup_counts,
            "sector_breakdown": sector_counts,
            "confidence_breakdown": confidence_counts,
            "timestamp": datetime.now().isoformat()
        }