"""Tests for the quantitative stock scanner."""

import pytest
import polars as pl
from datetime import datetime, timedelta
import random
import math

from services.scanner.scanner_engine import QuantScanner, StockScore, SetupType
from services.scanner.scanner_service import ScannerService
from services.data.providers.mock_provider import MockMarketDataProvider
from services.features.engine import FeatureEngine


def create_mock_features_data(n_stocks=20, n_days=250) -> pl.DataFrame:
    """Create mock features data for testing."""
    tickers = [f"TEST{i}" for i in range(1, n_stocks + 1)]

    # Generate base price data
    dates = [datetime.now().date() - timedelta(days=i) for i in range(n_days)]
    dates.reverse()

    records = []
    for ticker in tickers:
        base_price = random.uniform(20, 200)
        for i, date in enumerate(dates):
            # Random walk with drift
            daily_return = random.gauss(0.0005, 0.02)
            base_price *= (1 + daily_return)

            high = base_price * (1 + random.uniform(0, 0.03))
            low = base_price * (1 - random.uniform(0, 0.03))
            open_price = base_price * (1 + random.uniform(-0.01, 0.01))
            volume = random.randint(100000, 5000000)

            records.append({
                "ticker": ticker,
                "time": date,
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(base_price, 2),
                "volume": volume,
                "adjusted_close": round(base_price, 2),
            })

    df = pl.DataFrame(records)

    # Calculate features
    feature_engine = FeatureEngine()
    features_df = feature_engine.calculate_all_features(df)

    # Add static columns needed for filtering
    features_df = features_df.with_columns([
        pl.lit("Technology").alias("sector"),
        pl.lit("Software").alias("industry"),
        pl.lit(f"{random.choice(tickers)} Inc").alias("company_name"),
        pl.lit(random.uniform(1e9, 100e9)).alias("market_cap"),
        pl.lit(True).alias("is_active"),
    ])

    return features_df


class TestQuantScanner:
    """Test the QuantScanner engine."""

    def test_scanner_initialization(self):
        """Test scanner initializes with default config."""
        scanner = QuantScanner()

        assert scanner.weights['momentum'] == 0.30
        assert scanner.weights['breakout'] == 0.20
        assert scanner.weights['relative_strength'] == 0.25
        assert scanner.weights['volume'] == 0.15
        assert scanner.weights['fundamentals'] == 0.00
        assert scanner.weights['market_compatibility'] == 0.10

        assert scanner.min_price == 5.0
        assert scanner.min_avg_volume == 200000
        assert scanner.min_market_cap == 300000000

    def test_scanner_custom_config(self):
        """Test scanner with custom configuration."""
        config = {
            'momentum_weight': 0.40,
            'breakout_weight': 0.30,
            'min_price': 10.0,
            'min_avg_volume': 500000,
        }
        scanner = QuantScanner(config=config)

        assert scanner.weights['momentum'] == 0.40
        assert scanner.weights['breakout'] == 0.30
        assert scanner.min_price == 10.0
        assert scanner.min_avg_volume == 500000

    def test_liquidity_filters(self):
        """Test that liquidity filters work correctly."""
        scanner = QuantScanner(config={'min_price': 50.0})

        df = pl.DataFrame({
            "ticker": ["A", "B", "C"],
            "close": [40.0, 60.0, 80.0],
            "volume": [300000, 300000, 300000],
            "market_cap": [500000000, 500000000, 500000000],
            "is_active": [True, True, True],
        })

        filtered = scanner.apply_liquidity_filters(df)

        assert filtered.height == 2  # Only B and C pass
        assert "A" not in filtered["ticker"].to_list()

    def test_momentum_score_calculation(self):
        """Test momentum score calculation."""
        scanner = QuantScanner()

        df = pl.DataFrame({
            "ticker": ["A", "B"],
            "roc_5": [0.05, -0.03],
            "roc_20": [0.15, -0.10],
            "roc_60": [0.25, -0.15],
        })

        result = scanner.calculate_momentum_score(df)

        assert "momentum_score" in result.columns
        assert result["momentum_score"][0] > result["momentum_score"][1]

    def test_breakout_score_calculation(self):
        """Test breakout score calculation."""
        scanner = QuantScanner()

        df = pl.DataFrame({
            "ticker": ["A", "B"],
            "distance_from_52w_high": [-0.02, -0.30],
            "price_vs_sma20": [0.05, -0.05],
            "price_vs_sma50": [0.08, -0.08],
        })

        result = scanner.calculate_breakout_score(df)

        assert "breakout_score" in result.columns
        # Stock A is closer to 52-week high and above MAs
        assert result["breakout_score"][0] > result["breakout_score"][1]

    def test_relative_strength_score_calculation(self):
        """Test relative strength score calculation."""
        scanner = QuantScanner()

        df = pl.DataFrame({
            "ticker": ["A", "B"],
            "relative_strength_spy": [0.15, -0.05],
            "relative_strength_sector": [0.10, -0.03],
        })

        result = scanner.calculate_relative_strength_score(df)

        assert "relative_strength_score" in result.columns
        assert result["relative_strength_score"][0] > result["relative_strength_score"][1]

    def test_volume_score_calculation(self):
        """Test volume score calculation."""
        scanner = QuantScanner()

        df = pl.DataFrame({
            "ticker": ["A", "B"],
            "relative_volume": [2.5, 0.8],
            "volume_sma_ratio": [1.8, 0.7],
        })

        result = scanner.calculate_volume_score(df)

        assert "volume_score" in result.columns
        assert result["volume_score"][0] > result["volume_score"][1]

    def test_setup_type_identification(self):
        """Test setup type identification logic."""
        scanner = QuantScanner()

        # Breakout setup
        row_breakout = {
            'breakout_score': 85,
            'volume_score': 80,
            'momentum_score': 60,
            'relative_strength_score': 60,
        }
        assert scanner.identify_setup_type(row_breakout) == SetupType.BREAKOUT

        # Momentum setup
        row_momentum = {
            'momentum_score': 80,
            'relative_strength_score': 80,
            'breakout_score': 50,
            'volume_score': 50,
        }
        assert scanner.identify_setup_type(row_momentum) == SetupType.MOMENTUM

        # Relative strength setup
        row_rs = {
            'relative_strength_score': 90,
            'momentum_score': 60,
            'breakout_score': 50,
            'volume_score': 50,
        }
        assert scanner.identify_setup_type(row_rs) == SetupType.RELATIVE_STRENGTH

    def test_confidence_determination(self):
        """Test confidence level determination."""
        scanner = QuantScanner()

        assert scanner.determine_confidence(90, SetupType.MOMENTUM) == "High"
        assert scanner.determine_confidence(85, SetupType.MOMENTUM) == "High"
        assert scanner.determine_confidence(75, SetupType.MOMENTUM) == "Medium"
        assert scanner.determine_confidence(70, SetupType.MOMENTUM) == "Medium"
        assert scanner.determine_confidence(60, SetupType.MOMENTUM) == "Low"

    def test_full_scan(self):
        """Test complete scanning workflow."""
        features_df = create_mock_features_data(n_stocks=15, n_days=250)

        scanner = QuantScanner()
        results = scanner.scan(features_df, top_n=10)

        assert len(results) <= 10
        assert all(isinstance(r, StockScore) for r in results)

        # Check ranking
        for i in range(len(results) - 1):
            assert results[i].composite_score >= results[i+1].composite_score

        # Check scores are in valid range
        for result in results:
            assert 0 <= result.composite_score <= 100
            assert result.confidence in ["High", "Medium", "Low"]

    def test_scan_summary(self):
        """Test scan summary generation."""
        features_df = create_mock_features_data(n_stocks=20, n_days=250)

        scanner = QuantScanner()
        results = scanner.scan(features_df, top_n=20)
        summary = scanner.get_scan_summary(results)

        assert summary["total_opportunities"] == len(results)
        assert "average_score" in summary
        assert "top_score" in summary
        assert "setup_breakdown" in summary
        assert "sector_breakdown" in summary
        assert "confidence_breakdown" in summary


class TestScannerService:
    """Test the ScannerService layer."""

    def test_service_initialization(self):
        """Test service initializes correctly."""
        data_provider = MockMarketDataProvider()
        service = ScannerService(data_provider=data_provider)

        assert service.data_provider == data_provider
        assert service._last_scan_results is None
        assert service._last_scan_timestamp is None

    def test_run_scan(self):
        """Test running a scan through the service."""
        data_provider = MockMarketDataProvider(num_stocks=10)
        service = ScannerService(data_provider=data_provider)

        results = service.run_scan(top_n=5)

        assert len(results) <= 5
        assert service._last_scan_results is not None
        assert service._last_scan_timestamp is not None

    def test_get_top_opportunities(self):
        """Test getting top opportunities from cache."""
        data_provider = MockMarketDataProvider(num_stocks=10)
        service = ScannerService(data_provider=data_provider)

        # Run scan first
        service.run_scan(top_n=10)

        # Get top opportunities
        top = service.get_top_opportunities(n=3)

        assert len(top) <= 3
        assert all(r.composite_score >= top[-1].composite_score for r in top)

    def test_get_opportunity_by_ticker(self):
        """Test getting specific ticker from scan results."""
        data_provider = MockMarketDataProvider(num_stocks=10)
        service = ScannerService(data_provider=data_provider)

        # Run scan
        service.run_scan()

        # Get first ticker from results
        if service._last_scan_results:
            first_ticker = service._last_scan_results[0].ticker
            result = service.get_opportunity_by_ticker(first_ticker)

            assert result is not None
            assert result.ticker == first_ticker

    def test_filter_by_setup_type(self):
        """Test filtering by setup type."""
        data_provider = MockMarketDataProvider(num_stocks=20)
        service = ScannerService(data_provider=data_provider)

        service.run_scan(top_n=20)

        # Filter for momentum setups
        momentum_setups = service.filter_by_setup_type(SetupType.MOMENTUM, min_score=50)

        # All results should be momentum type
        for setup in momentum_setups:
            assert setup.setup_type == SetupType.MOMENTUM
            assert setup.composite_score >= 50

    def test_clear_cache(self):
        """Test clearing cached results."""
        data_provider = MockMarketDataProvider(num_stocks=10)
        service = ScannerService(data_provider=data_provider)

        # Run scan
        service.run_scan()
        assert service._last_scan_results is not None

        # Clear cache
        service.clear_cache()
        assert service._last_scan_results is None
        assert service._last_scan_timestamp is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])