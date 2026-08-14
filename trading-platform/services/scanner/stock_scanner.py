"""Stock scanner for ranking and filtering opportunities."""
import polars as pl
from typing import Optional


class StockScanner:
    """Scans and ranks stocks based on quantitative criteria."""

    def __init__(self):
        self.min_price = 5.0  # Minimum price filter
        self.min_avg_volume = 100000  # Minimum average volume
        self.min_market_cap = 300_000_000  # $300M minimum market cap

    def rank_stocks(
        self,
        features_df: pl.DataFrame,
        strategy: str = "momentum_breakout"
    ) -> pl.DataFrame:
        """
        Rank stocks based on the specified strategy.

        Args:
            features_df: DataFrame with features for multiple stocks
            strategy: Strategy name ('momentum_breakout', 'relative_strength', etc.)

        Returns:
            Ranked DataFrame with scores
        """
        if strategy == "momentum_breakout":
            return self._rank_momentum_breakout(features_df)
        elif strategy == "relative_strength":
            return self._rank_relative_strength(features_df)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _rank_momentum_breakout(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Rank stocks using momentum breakout strategy.

        Scoring components:
        - 30% Relative strength vs SPY
        - 20% Price momentum (20-day ROC)
        - 20% Volume confirmation
        - 15% Breakout quality (distance from highs)
        - 15% Trend alignment (price above SMA50/200)
        """
        df = df.with_columns([
            # Normalize RSI (higher is better, but cap at 70)
            pl.col("rsi_14").clip(0, 70).alias("rsi_norm"),

            # Momentum score (20-day rate of change)
            pl.col("roc_20").fill_null(0).alias("momentum"),

            # Volume score (relative volume)
            pl.col("relative_volume").fill_null(1.0).alias("volume_score"),

            # Distance from 52-week high (lower is better for breakout)
            pl.col("dist_52w_high_pct").fill_null(100).alias("dist_high"),

            # Trend alignment
            ((pl.col("close") > pl.col("sma_50")) &
             (pl.col("close") > pl.col("sma_200"))).cast(pl.Float64).alias("trend_align")
        ])

        # Calculate composite score (0-100 scale)
        df = df.with_columns([
            (
                0.30 * (100 - pl.col("dist_high")).clip(0, 100) +  # Breakout score
                0.20 * pl.col("momentum").clip(-50, 50) * 2 +  # Momentum score
                0.20 * pl.col("volume_score").clip(0, 5) * 20 +  # Volume score
                0.15 * pl.col("trend_align") * 100 +  # Trend score
                0.15 * pl.col("rsi_norm")  # RSI score
            ).alias("composite_score")
        ])

        # Filter and sort
        result = df.filter(
            (pl.col("close") >= self.min_price) &
            (pl.col("volume") >= self.min_avg_volume)
        ).sort("composite_score", descending=True)

        return result

    def _rank_relative_strength(self, df: pl.DataFrame) -> pl.DataFrame:
        """Rank stocks by relative strength vs market."""
        # Placeholder for relative strength ranking
        df = df.with_columns([
            pl.col("relative_strength").fill_null(0).alias("rs_score")
        ])

        result = df.filter(
            (pl.col("close") >= self.min_price) &
            (pl.col("volume") >= self.min_avg_volume)
        ).sort("rs_score", descending=True)

        return result

    def apply_filters(
        self,
        df: pl.DataFrame,
        min_price: Optional[float] = None,
        min_volume: Optional[int] = None,
        sectors: Optional[list[str]] = None
    ) -> pl.DataFrame:
        """Apply custom filters to stock universe."""
        min_p = min_price or self.min_price
        min_v = min_volume or self.min_avg_volume

        df = df.filter(
            (pl.col("close") >= min_p) &
            (pl.col("volume") >= min_v)
        )

        if sectors:
            df = df.filter(pl.col("sector").is_in(sectors))

        return df