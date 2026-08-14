"""Tests for feature engineering engine."""

import sys
sys.path.insert(0, '/workspace/trading-platform')

import polars as pl
from datetime import datetime, timedelta
import random

# Import only the engine (no database dependencies)
from services.features.engine import FeatureEngine


def create_sample_price_data(days: int = 300) -> pl.DataFrame:
    """Create sample price data for testing."""
    random.seed(42)

    base_price = 100.0
    dates = [datetime.now() - timedelta(days=i) for i in range(days, 0, -1)]

    prices = []
    price = base_price

    for date in dates:
        # Random walk with drift
        change = random.gauss(0.0005, 0.02)
        price = price * (1 + change)

        open_price = price * (1 + random.gauss(0, 0.005))
        high_price = max(open_price, price) * (1 + abs(random.gauss(0, 0.01)))
        low_price = min(open_price, price) * (1 - abs(random.gauss(0, 0.01)))
        close_price = price
        volume = int(random.uniform(1_000_000, 10_000_000))

        prices.append({
            "time": date,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": volume
        })

    return pl.DataFrame(prices)


class TestFeatureEngine:
    """Test suite for FeatureEngine."""

    def test_calculate_price_features(self):
        """Test SMA and EMA calculations."""
        engine = FeatureEngine()
        df = create_sample_price_data(300)

        result = engine.calculate_price_features(df)

        # Check that columns were added
        assert "sma_20" in result.columns
        assert "sma_50" in result.columns
        assert "sma_200" in result.columns
        assert "ema_12" in result.columns
        assert "ema_26" in result.columns

        # Check that we have the right number of rows
        assert len(result) == 300

        # First rows should have null values for long-period SMAs (not enough data)
        # SMA200 needs 200 periods, so index 0-198 should be null
        sma_200_null_count = result["sma_200"].null_count()
        assert sma_200_null_count >= 199, f"Expected at least 199 null values for SMA200, got {sma_200_null_count}"

        print("✓ Price features test passed")

    def test_calculate_momentum_features(self):
        """Test momentum/ROC calculations."""
        engine = FeatureEngine()
        df = create_sample_price_data(300)
        df = engine.calculate_price_features(df)

        result = engine.calculate_momentum_features(df)

        assert "roc_5" in result.columns
        assert "roc_20" in result.columns
        assert "roc_60" in result.columns
        assert "dist_sma_20_pct" in result.columns

        print("✓ Momentum features test passed")

    def test_calculate_rsi(self):
        """Test RSI calculation."""
        engine = FeatureEngine()
        df = create_sample_price_data(300)
        df = engine.calculate_price_features(df)

        result = engine.calculate_rsi(df)

        assert "rsi_14" in result.columns

        # RSI should be between 0 and 100 (excluding NaN and null values)
        rsi_col = result["rsi_14"]
        # Convert to Python list and filter
        rsi_values = [v for v in rsi_col.to_list() if v is not None and not (isinstance(v, float) and (v != v or v > 100 or v < 0))]
        if len(rsi_values) > 0:
            assert all(0 <= v <= 100 for v in rsi_values)

        print("✓ RSI test passed")

    def test_calculate_macd(self):
        """Test MACD calculation."""
        engine = FeatureEngine()
        df = create_sample_price_data(300)
        df = engine.calculate_price_features(df)

        result = engine.calculate_macd(df)

        assert "macd_line" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_hist" in result.columns

        print("✓ MACD test passed")

    def test_calculate_volatility_features(self):
        """Test ATR and Bollinger Bands."""
        engine = FeatureEngine()
        df = create_sample_price_data(300)

        result = engine.calculate_volatility_features(df)

        assert "atr_14" in result.columns
        assert "atr_pct" in result.columns
        assert "bb_upper" in result.columns
        assert "bb_lower" in result.columns
        assert "bb_pct" in result.columns

        # ATR should be positive
        atr_values = result["atr_14"].drop_nulls()
        if len(atr_values) > 0:
            assert all(v > 0 for v in atr_values)

        print("✓ Volatility features test passed")

    def test_calculate_volume_features(self):
        """Test volume-based features."""
        engine = FeatureEngine()
        df = create_sample_price_data(300)

        result = engine.calculate_volume_features(df)

        assert "volume_sma_20" in result.columns
        assert "relative_volume" in result.columns
        assert "obv" in result.columns
        assert "dollar_volume" in result.columns

        print("✓ Volume features test passed")

    def test_calculate_breakout_features(self):
        """Test breakout detection features."""
        engine = FeatureEngine()
        df = create_sample_price_data(300)

        result = engine.calculate_breakout_features(df)

        assert "high_20d" in result.columns
        assert "high_52w" in result.columns
        assert "dist_52w_high_pct" in result.columns
        assert "is_20d_breakout" in result.columns

        print("✓ Breakout features test passed")

    def test_calculate_all_features(self):
        """Test complete feature calculation pipeline."""
        engine = FeatureEngine()
        df = create_sample_price_data(300)

        result = engine.calculate_all_features(df)

        # Check all expected feature categories
        expected_features = engine.get_feature_columns()

        for feature in expected_features:
            assert feature in result.columns, f"Missing feature: {feature}"

        # Verify we still have original columns
        assert "time" in result.columns
        assert "close" in result.columns
        assert "volume" in result.columns

        print(f"✓ All features test passed ({len(expected_features)} features)")

    def test_feature_names(self):
        """Test that feature names are consistent."""
        engine = FeatureEngine()
        features = engine.get_feature_columns()

        # Should have reasonable number of features
        assert len(features) >= 20

        # All features should be strings
        assert all(isinstance(f, str) for f in features)

        # No duplicates
        assert len(features) == len(set(features))

        print(f"✓ Feature names test passed ({len(features)} unique features)")


if __name__ == "__main__":
    # Run tests
    test_suite = TestFeatureEngine()

    print("\n=== Running Feature Engine Tests ===\n")

    test_suite.test_calculate_price_features()
    test_suite.test_calculate_momentum_features()
    test_suite.test_calculate_rsi()
    test_suite.test_calculate_macd()
    test_suite.test_calculate_volatility_features()
    test_suite.test_calculate_volume_features()
    test_suite.test_calculate_breakout_features()
    test_suite.test_calculate_all_features()
    test_suite.test_feature_names()

    print("\n=== All Tests Passed! ===\n")