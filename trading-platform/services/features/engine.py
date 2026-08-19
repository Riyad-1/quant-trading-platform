"""Feature engineering engine using Polars for high-performance calculations."""

from typing import List

import polars as pl

from services.research.timing import add_daily_point_in_time_columns


class FeatureEngine:
    """Calculate technical and quantitative features from price data."""

    def __init__(self):
        pass

    @staticmethod
    def _sort(df: pl.DataFrame) -> pl.DataFrame:
        """Sort one asset chronologically or a panel by asset then time."""
        columns = ["ticker", "time"] if "ticker" in df.columns else ["time"]
        return df.sort(columns)

    @staticmethod
    def _per_ticker(expr: pl.Expr, df: pl.DataFrame) -> pl.Expr:
        """Evaluate a stateful expression independently for each ticker."""
        return expr.over("ticker") if "ticker" in df.columns else expr

    def calculate_price_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate price-based features: SMA, EMA, etc.

        Args:
            df: DataFrame with columns [time, open, high, low, close, volume]

        Returns:
            DataFrame with additional feature columns
        """
        df = self._sort(df)

        # Simple Moving Averages
        df = df.with_columns([
            self._per_ticker(pl.col("close").rolling_mean(window_size=20), df).alias("sma_20"),
            self._per_ticker(pl.col("close").rolling_mean(window_size=50), df).alias("sma_50"),
            self._per_ticker(pl.col("close").rolling_mean(window_size=200), df).alias("sma_200"),
        ])

        # Exponential Moving Averages
        df = df.with_columns([
            self._per_ticker(pl.col("close").ewm_mean(span=12, adjust=False), df).alias("ema_12"),
            self._per_ticker(pl.col("close").ewm_mean(span=26, adjust=False), df).alias("ema_26"),
            self._per_ticker(pl.col("close").ewm_mean(span=20, adjust=False), df).alias("ema_20"),
        ])

        return df

    def calculate_momentum_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate momentum features: ROC, relative strength, etc.
        """
        df = self._sort(df)

        # Rate of Change (ROC) / Returns
        df = df.with_columns([
            (pl.col("close") / self._per_ticker(pl.col("close").shift(5), df) - 1).alias("roc_5"),
            (pl.col("close") / self._per_ticker(pl.col("close").shift(10), df) - 1).alias("roc_10"),
            (pl.col("close") / self._per_ticker(pl.col("close").shift(20), df) - 1).alias("roc_20"),
            (pl.col("close") / self._per_ticker(pl.col("close").shift(60), df) - 1).alias("roc_60"),
            (pl.col("close") / self._per_ticker(pl.col("close").shift(120), df) - 1).alias("roc_120"),
        ])

        # Distance from moving averages
        df = df.with_columns([
            ((pl.col("close") - pl.col("sma_20")) / pl.col("sma_20")).alias("dist_sma_20_pct"),
            ((pl.col("close") - pl.col("sma_50")) / pl.col("sma_50")).alias("dist_sma_50_pct"),
            ((pl.col("close") - pl.col("sma_200")) / pl.col("sma_200")).alias("dist_sma_200_pct"),
        ])

        return df

    def calculate_rsi(self, df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
        """
        Calculate Relative Strength Index (RSI).
        """
        df = self._sort(df)

        # Calculate price changes
        df = df.with_columns([
            self._per_ticker(pl.col("close").diff(), df).alias("price_change")
        ])

        # Separate gains and losses
        df = df.with_columns([
            pl.when(pl.col("price_change") > 0)
            .then(pl.col("price_change"))
            .otherwise(0.0).alias("gain"),
            pl.when(pl.col("price_change") < 0)
            .then(-pl.col("price_change"))
            .otherwise(0.0).alias("loss")
        ])

        # Calculate average gain and loss using EMA
        df = df.with_columns([
            self._per_ticker(pl.col("gain").ewm_mean(alpha=1/period, adjust=False), df).alias("avg_gain"),
            self._per_ticker(pl.col("loss").ewm_mean(alpha=1/period, adjust=False), df).alias("avg_loss")
        ])

        # Calculate RS first
        df = df.with_columns([
            (pl.col("avg_gain") / pl.col("avg_loss")).alias("rs")
        ])

        # Then calculate RSI using RS
        df = df.with_columns([
            (100.0 - (100.0 / (1.0 + pl.col("rs")))).alias("rsi_14")
        ])

        return df

    def calculate_macd(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate MACD indicator.
        """
        df = self._sort(df)

        # MACD Line (12 EMA - 26 EMA)
        df = df.with_columns([
            (pl.col("ema_12") - pl.col("ema_26")).alias("macd_line")
        ])

        # Signal Line (9 EMA of MACD)
        df = df.with_columns([
            self._per_ticker(pl.col("macd_line").ewm_mean(span=9, adjust=False), df).alias("macd_signal")
        ])

        # MACD Histogram
        df = df.with_columns([
            (pl.col("macd_line") - pl.col("macd_signal")).alias("macd_hist")
        ])

        return df

    def calculate_volatility_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate volatility features: ATR, Bollinger Bands, etc.
        """
        df = self._sort(df)

        previous_close = self._per_ticker(pl.col("close").shift(1), df)

        # True Range
        df = df.with_columns([
            pl.max_horizontal([
                pl.col("high") - pl.col("low"),
                (pl.col("high") - previous_close).abs(),
                (pl.col("low") - previous_close).abs()
            ]).alias("true_range")
        ])

        # Average True Range (ATR)
        df = df.with_columns([
            self._per_ticker(pl.col("true_range").rolling_mean(window_size=14), df).alias("atr_14")
        ])

        # ATR as percentage of price
        df = df.with_columns([
            (pl.col("atr_14") / pl.col("close") * 100).alias("atr_pct")
        ])

        # Bollinger Bands - first calculate middle and std
        df = df.with_columns([
            self._per_ticker(pl.col("close").rolling_mean(window_size=20), df).alias("bb_middle"),
            self._per_ticker(pl.col("close").rolling_std(window_size=20), df).alias("bb_std")
        ])

        # Then calculate upper, lower and pct in separate step
        df = df.with_columns([
            (pl.col("bb_middle") + 2 * pl.col("bb_std")).alias("bb_upper"),
            (pl.col("bb_middle") - 2 * pl.col("bb_std")).alias("bb_lower")
        ])

        df = df.with_columns([
            ((pl.col("close") - pl.col("bb_lower")) / (pl.col("bb_upper") - pl.col("bb_lower"))).alias("bb_pct")
        ])

        return df

    def calculate_volume_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate volume-based features.
        """
        df = self._sort(df)

        # Volume SMA
        df = df.with_columns([
            self._per_ticker(pl.col("volume").rolling_mean(window_size=20), df).alias("volume_sma_20")
        ])

        # Relative Volume
        df = df.with_columns([
            (pl.col("volume") / pl.col("volume_sma_20")).alias("relative_volume"),
            (pl.col("volume") / pl.col("volume_sma_20")).alias("volume_sma_20_ratio"),
        ])

        # Dollar Volume
        if "dollar_volume" not in df.columns:
            df = df.with_columns([
                (pl.col("close") * pl.col("volume")).alias("dollar_volume")
            ])

        previous_close = self._per_ticker(pl.col("close").shift(1), df)
        df = df.with_columns([
            pl.when(pl.col("close") > previous_close)
            .then(pl.col("volume"))
            .when(pl.col("close") < previous_close)
            .then(-pl.col("volume"))
            .otherwise(0)
            .alias("signed_volume")
        ])
        df = df.with_columns([
            self._per_ticker(pl.col("signed_volume").cum_sum(), df).alias("obv")
        ])

        return df

    def calculate_breakout_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate breakout-related features.
        """
        df = self._sort(df)

        df = df.with_columns([
            self._per_ticker(pl.col("high").shift(1).rolling_max(window_size=20), df).alias("prior_20d_high"),
            self._per_ticker(pl.col("low").shift(1).rolling_min(window_size=20), df).alias("prior_20d_low"),
            self._per_ticker(pl.col("high").rolling_max(window_size=20), df).alias("current_20d_high"),
            self._per_ticker(pl.col("low").rolling_min(window_size=20), df).alias("current_20d_low"),
            self._per_ticker(pl.col("high").rolling_max(window_size=252), df).alias("high_52w"),
            self._per_ticker(pl.col("low").rolling_min(window_size=252), df).alias("low_52w"),
        ])

        df = df.with_columns([
            pl.col("current_20d_high").alias("high_20d"),
            pl.col("current_20d_low").alias("low_20d"),
        ])

        # Distance from 52-week high
        df = df.with_columns([
            ((pl.col("close") - pl.col("high_52w")) / pl.col("high_52w")).alias("dist_52w_high_pct"),
            ((pl.col("close") - pl.col("prior_20d_high")) / pl.col("prior_20d_high")).alias("distance_from_20d_high"),
        ])

        # Breakout flag (price at 20-day high)
        df = df.with_columns([
            (pl.col("close") >= pl.col("prior_20d_high")).fill_null(False).alias("is_20d_breakout")
        ])

        return df

    def calculate_all_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Calculate all features in the correct order.

        Args:
            df: DataFrame with columns [time, open, high, low, close, volume]

        Returns:
            DataFrame with all calculated features
        """
        df = self._sort(df)

        # Price features first (SMA, EMA)
        df = self.calculate_price_features(df)

        # Momentum features
        df = self.calculate_momentum_features(df)

        # RSI
        df = self.calculate_rsi(df)

        # MACD
        df = self.calculate_macd(df)

        # Volatility features
        df = self.calculate_volatility_features(df)

        # Volume features
        df = self.calculate_volume_features(df)

        # Breakout features
        df = self.calculate_breakout_features(df)

        return add_daily_point_in_time_columns(df, time_col="time")

    def get_feature_columns(self) -> List[str]:
        """Return list of all feature column names."""
        return [
            "sma_20", "sma_50", "sma_200",
            "ema_12", "ema_26", "ema_20",
            "roc_5", "roc_10", "roc_20", "roc_60", "roc_120",
            "dist_sma_20_pct", "dist_sma_50_pct", "dist_sma_200_pct",
            "rsi_14",
            "macd_line", "macd_signal", "macd_hist",
            "atr_14", "atr_pct",
            "bb_upper", "bb_middle", "bb_lower", "bb_pct",
            "volume_sma_20", "relative_volume", "volume_sma_20_ratio", "obv",
            "prior_20d_high", "prior_20d_low", "current_20d_high", "current_20d_low",
            "high_20d", "low_20d", "high_52w", "low_52w",
            "distance_from_20d_high", "dist_52w_high_pct", "is_20d_breakout"
        ]
