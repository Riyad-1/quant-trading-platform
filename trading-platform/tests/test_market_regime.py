"""Tests for Market Regime Engine."""
import pytest
import polars as pl
from datetime import date, timedelta
from services.market_regime.regime_engine import RegimeEngine, MarketRegime

@pytest.fixture
def regime_engine():
    return RegimeEngine()

@pytest.fixture
def bull_market_data():
    """Generate synthetic data for a strong bull market."""
    dates = [date.today() - timedelta(days=i) for i in range(250)]
    dates.reverse()

    # Uptrend: Price consistently above SMAs
    data = {
        "date": dates,
        "close": [100 + i * 0.5 for i in range(250)],  # Steady uptrend
        "sma_20": [95 + i * 0.5 for i in range(250)],
        "sma_50": [90 + i * 0.5 for i in range(250)],
        "sma_200": [80 + i * 0.5 for i in range(250)]
    }
    return pl.DataFrame(data)

@pytest.fixture
def bear_market_data():
    """Generate synthetic data for a bear market."""
    dates = [date.today() - timedelta(days=i) for i in range(250)]
    dates.reverse()

    # Downtrend: Price consistently below SMAs
    data = {
        "date": dates,
        "close": [150 - i * 0.5 for i in range(250)],  # Steady downtrend
        "sma_20": [155 - i * 0.5 for i in range(250)],
        "sma_50": [160 - i * 0.5 for i in range(250)],
        "sma_200": [170 - i * 0.5 for i in range(250)]
    }
    return pl.DataFrame(data)

def test_strong_bull_classification(regime_engine, bull_market_data):
    """Test that strong uptrend is classified as STRONG_BULL."""
    result = regime_engine.get_current_regime(bull_market_data, vix_value=15.0)

    assert result["regime"] == MarketRegime.STRONG_BULL.value
    # Distance should be positive (price above SMA50)
    assert result["metrics"]["dist_sma_50"] > 0.02
    assert result["metrics"]["dist_sma_200"] > 0.05

def test_bear_classification(regime_engine, bear_market_data):
    """Test that downtrend is classified as BEAR."""
    result = regime_engine.get_current_regime(bear_market_data, vix_value=20.0)

    assert result["regime"] == MarketRegime.BEAR.value
    assert result["metrics"]["dist_sma_50"] < -0.05

def test_high_vol_risk_off(regime_engine, bear_market_data):
    """Test high VIX + downtrend = HIGH_VOL_RISK_OFF."""
    result = regime_engine.get_current_regime(bear_market_data, vix_value=35.0)

    assert result["regime"] == MarketRegime.HIGH_VOL_RISK_OFF.value

def test_metrics_calculation(regime_engine, bull_market_data):
    """Test that metrics are calculated correctly."""
    metrics = regime_engine.calculate_regime_metrics(bull_market_data, vix_value=18.0)

    assert "close" in metrics
    assert "sma_50" in metrics
    assert "dist_sma_50" in metrics
    assert "spy_trend_score" in metrics
    assert metrics["vix"] == 18.0
    assert metrics["dist_sma_50"] > 0  # Should be positive in bull market

def test_empty_data(regime_engine):
    """Test handling of empty dataframe."""
    empty_df = pl.DataFrame(schema={"date": pl.Date, "close": pl.Float64})
    result = regime_engine.get_current_regime(empty_df)

    assert "error" in result

def test_neutral_market(regime_engine):
    """Test choppy/neutral market classification."""
    dates = [date.today() - timedelta(days=i) for i in range(250)]
    dates.reverse()

    # Flat market: Price oscillating around SMA with no clear trend
    base = 100.0
    # Ensure last few data points are below or at SMA to avoid bull classification
    close_values = [base + (i % 5) - 2.5 for i in range(250)]
    close_values[-1] = base - 1.0  # Last day below SMA
    close_values[-2] = base - 0.5  # Second last day below SMA

    data = {
        "date": dates,
        "close": close_values,  # Purely oscillating, no drift
        "sma_20": [base for i in range(250)],  # Flat SMA
        "sma_50": [base for i in range(250)],
        "sma_200": [base for i in range(250)]
    }
    df = pl.DataFrame(data)

    result = regime_engine.get_current_regime(df, vix_value=20.0)

    # Should be NEUTRAL or CORRECTION for truly flat/choppy market
    assert result["regime"] in [MarketRegime.NEUTRAL.value, MarketRegime.CORRECTION.value]

def test_regime_description(regime_engine):
    """Test that descriptions are returned for all regimes."""
    for regime in MarketRegime:
        desc = regime_engine._get_regime_description(regime)
        assert isinstance(desc, str)
        assert len(desc) > 10