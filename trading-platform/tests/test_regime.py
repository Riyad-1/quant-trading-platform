"""Tests for Market Regime Detection."""

import pytest
from datetime import date, timedelta
from services.regime.regime_detector import (
    MarketRegimeDetector,
    MarketRegime,
    RegimeResult
)


class TestMarketRegimeDetector:
    """Test market regime detection functionality."""

    def test_detector_initialization(self):
        """Test detector initializes with default values."""
        detector = MarketRegimeDetector()

        assert detector.vix_low == 15.0
        assert detector.vix_high == 25.0
        assert detector.breadth_strong == 70.0
        assert detector.breadth_weak == 30.0

    def test_analyze_trend_bullish(self):
        """Test bullish trend detection."""
        detector = MarketRegimeDetector()

        spy_data = {
            'time': date.today(),
            'close': 450.0,
            'sma_20': 445.0,
            'sma_50': 440.0,
            'sma_200': 420.0
        }

        trend = detector._analyze_trend(spy_data)
        assert trend == "bullish"

    def test_analyze_trend_bearish(self):
        """Test bearish trend detection."""
        detector = MarketRegimeDetector()

        spy_data = {
            'time': date.today(),
            'close': 400.0,
            'sma_20': 410.0,
            'sma_50': 420.0,
            'sma_200': 440.0
        }

        trend = detector._analyze_trend(spy_data)
        assert trend == "bearish"

    def test_analyze_trend_neutral(self):
        """Test neutral trend detection."""
        detector = MarketRegimeDetector()

        spy_data = {
            'time': date.today(),
            'close': 430.0,
            'sma_20': 440.0,
            'sma_50': 425.0,
            'sma_200': 420.0
        }

        trend = detector._analyze_trend(spy_data)
        assert trend == "neutral"

    def test_classify_vix(self):
        """Test VIX classification."""
        detector = MarketRegimeDetector()

        assert detector._classify_vix(12.0) == "low"
        assert detector._classify_vix(18.0) == "medium"
        assert detector._classify_vix(30.0) == "high"
        assert detector._classify_vix(None) == "medium"

    def test_calculate_breadth_score(self):
        """Test breadth score calculation."""
        detector = MarketRegimeDetector()

        # Perfect breadth
        breadth_data = {
            'pct_above_sma50': 80.0,
            'advance_decline_ratio': 2.0,
            'new_highs_lows_ratio': 3.0
        }
        score = detector._calculate_breadth_score(breadth_data)
        assert score > 70

        # Weak breadth
        weak_breadth = {
            'pct_above_sma50': 20.0,
            'advance_decline_ratio': 0.5,
            'new_highs_lows_ratio': 0.3
        }
        score = detector._calculate_breadth_score(weak_breadth)
        assert score < 40

        # No data - default to neutral
        score = detector._calculate_breadth_score(None)
        assert score == 50.0

    def test_full_analysis_strong_bull(self):
        """Test full analysis returning strong bull regime."""
        detector = MarketRegimeDetector()

        spy_data = {
            'time': date.today(),
            'close': 450.0,
            'sma_20': 445.0,
            'sma_50': 440.0,
            'sma_200': 420.0
        }

        qqq_data = {
            'time': date.today(),
            'close': 380.0,
            'sma_20': 375.0,
            'sma_50': 370.0,
            'sma_200': 350.0
        }

        breadth_data = {
            'pct_above_sma50': 75.0,
            'advance_decline_ratio': 1.8,
            'new_highs_lows_ratio': 2.5
        }

        result = detector.analyze(
            spy_data=spy_data,
            qqq_data=qqq_data,
            vix_value=13.0,
            breadth_data=breadth_data
        )

        assert isinstance(result, RegimeResult)
        assert result.regime == MarketRegime.STRONG_BULL
        assert result.confidence >= 0.8
        assert result.spy_trend == "bullish"
        assert result.vix_level == "low"
        assert result.breadth_score > 70
        assert result.risk_score < 30

    def test_full_analysis_bear(self):
        """Test full analysis returning bear regime."""
        detector = MarketRegimeDetector()

        spy_data = {
            'time': date.today(),
            'close': 380.0,
            'sma_20': 400.0,
            'sma_50': 420.0,
            'sma_200': 450.0
        }

        qqq_data = {
            'time': date.today(),
            'close': 320.0,
            'sma_20': 340.0,
            'sma_50': 360.0,
            'sma_200': 390.0
        }

        breadth_data = {
            'pct_above_sma50': 20.0,
            'advance_decline_ratio': 0.4,
            'new_highs_lows_ratio': 0.2
        }

        result = detector.analyze(
            spy_data=spy_data,
            qqq_data=qqq_data,
            vix_value=32.0,
            breadth_data=breadth_data
        )

        assert result.regime == MarketRegime.BEAR
        assert result.confidence >= 0.8
        assert result.spy_trend == "bearish"
        assert result.vix_level == "high"
        assert result.risk_score > 70

    def test_full_analysis_neutral(self):
        """Test full analysis returning neutral regime."""
        detector = MarketRegimeDetector()

        spy_data = {
            'time': date.today(),
            'close': 420.0,
            'sma_20': 425.0,
            'sma_50': 415.0,
            'sma_200': 410.0
        }

        result = detector.analyze(
            spy_data=spy_data,
            vix_value=18.0
        )

        assert result.regime == MarketRegime.NEUTRAL
        assert result.confidence == 0.6

    def test_risk_score_calculation(self):
        """Test risk score calculation components."""
        detector = MarketRegimeDetector()

        # Low risk scenario
        risk_low = detector._calculate_risk_score(
            spy_trend="bullish",
            vix_level="low",
            breadth_score=80.0,
            vol_regime="low"
        )
        assert risk_low < 30

        # High risk scenario
        risk_high = detector._calculate_risk_score(
            spy_trend="bearish",
            vix_level="high",
            breadth_score=20.0,
            vol_regime="high"
        )
        assert risk_high > 70

    def test_strategy_recommendations(self):
        """Test strategy recommendations for different regimes."""
        detector = MarketRegimeDetector()

        # Bull market recommendations
        bull_recs = detector.get_strategy_recommendations(MarketRegime.BULL)
        assert bull_recs["momentum"] == "favourable"
        assert bull_recs["breakouts"] == "favourable"
        assert bull_recs["shorting"] == "unfavourable"

        # Bear market recommendations
        bear_recs = detector.get_strategy_recommendations(MarketRegime.BEAR)
        assert bear_recs["momentum"] == "unfavourable"
        assert bear_recs["description"] != ""

        # Neutral market recommendations
        neutral_recs = detector.get_strategy_recommendations(MarketRegime.NEUTRAL)
        assert neutral_recs["mean_reversion"] == "favourable"

    def test_result_to_dict(self):
        """Test RegimeResult serialization."""
        result = RegimeResult(
            date=date.today(),
            regime=MarketRegime.BULL,
            confidence=0.85,
            spy_trend="bullish",
            vix_level="low",
            breadth_score=72.5,
            volatility_regime="low",
            risk_score=25.0
        )

        result_dict = result.to_dict()

        assert result_dict["regime"] == "bull"
        assert result_dict["confidence"] == 0.85
        assert result_dict["spy_trend"] == "bullish"
        assert "date" in result_dict

    def test_minimal_input_analysis(self):
        """Test analysis with minimal inputs."""
        detector = MarketRegimeDetector()

        spy_data = {
            'time': date.today(),
            'close': 430.0,
            'sma_20': 425.0,
            'sma_50': 420.0,
            'sma_200': 415.0
        }

        # Only provide SPY data, everything else optional
        result = detector.analyze(spy_data=spy_data)

        assert isinstance(result, RegimeResult)
        assert result.regime in MarketRegime
        assert 0 <= result.confidence <= 1
        assert 0 <= result.risk_score <= 100
        assert 0 <= result.breadth_score <= 100