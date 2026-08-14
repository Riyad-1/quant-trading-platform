"""
Market Regime Detection Module

Classifies market conditions into regimes:
- Strong Bull
- Bull
- Neutral
- Correction
- Bear
- High-Volatility Risk-Off
- Low-Volatility Risk-On
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import date
import polars as pl


class MarketRegime(Enum):
    """Market regime classifications."""
    STRONG_BULL = "strong_bull"
    BULL = "bull"
    NEUTRAL = "neutral"
    CORRECTION = "correction"
    BEAR = "bear"
    HIGH_VOL_RISK_OFF = "high_vol_risk_off"
    LOW_VOL_RISK_ON = "low_vol_risk_on"


@dataclass
class RegimeResult:
    """Result of market regime analysis."""
    date: date
    regime: MarketRegime
    confidence: float  # 0.0 to 1.0
    spy_trend: str  # bullish, bearish, neutral
    vix_level: str  # low, medium, high
    breadth_score: float  # 0-100
    volatility_regime: str
    risk_score: float  # 0-100, higher = more risk

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "regime": self.regime.value,
            "confidence": round(self.confidence, 2),
            "spy_trend": self.spy_trend,
            "vix_level": self.vix_level,
            "breadth_score": round(self.breadth_score, 2),
            "volatility_regime": self.volatility_regime,
            "risk_score": round(self.risk_score, 2)
        }


class MarketRegimeDetector:
    """
    Detects market regimes using multiple indicators.

    Inputs:
    - SPY trend (position relative to SMA20/50/200)
    - QQQ trend
    - VIX level
    - Realized volatility
    - Market breadth (% of stocks above moving averages)
    - Sector breadth
    """

    def __init__(self):
        # VIX thresholds
        self.vix_low = 15.0
        self.vix_high = 25.0

        # Breadth thresholds
        self.breadth_strong = 70.0  # % above SMA50
        self.breadth_weak = 30.0

    def analyze(self,
                spy_data: Dict[str, Any],
                qqq_data: Optional[Dict[str, Any]] = None,
                vix_value: Optional[float] = None,
                breadth_data: Optional[Dict[str, Any]] = None,
                volatility_data: Optional[Dict[str, Any]] = None) -> RegimeResult:
        """
        Analyze market conditions and determine regime.

        Args:
            spy_data: SPY price data with SMAs
            qqq_data: QQQ price data (optional)
            vix_value: Current VIX value
            breadth_data: Market breadth indicators
            volatility_data: Volatility metrics

        Returns:
            RegimeResult with classification and metrics
        """
        current_date = spy_data.get('time', date.today())

        # Analyze SPY trend
        spy_trend = self._analyze_trend(spy_data)

        # Analyze QQQ trend if available
        qqq_trend = self._analyze_trend(qqq_data) if qqq_data else spy_trend

        # Determine VIX level
        vix_level = self._classify_vix(vix_value)

        # Calculate breadth score
        breadth_score = self._calculate_breadth_score(breadth_data)

        # Determine volatility regime
        vol_regime = self._determine_volatility_regime(vix_value, volatility_data)

        # Calculate risk score (0-100, higher = more risk)
        risk_score = self._calculate_risk_score(
            spy_trend, vix_level, breadth_score, vol_regime
        )

        # Determine primary regime
        regime, confidence = self._determine_regime(
            spy_trend, qqq_trend, vix_level, breadth_score, vol_regime, risk_score
        )

        return RegimeResult(
            date=current_date,
            regime=regime,
            confidence=confidence,
            spy_trend=spy_trend,
            vix_level=vix_level,
            breadth_score=breadth_score,
            volatility_regime=vol_regime,
            risk_score=risk_score
        )

    def _analyze_trend(self, price_data: Dict[str, Any]) -> str:
        """Analyze trend based on price vs moving averages."""
        close = price_data.get('close', 0)
        sma_20 = price_data.get('sma_20', 0)
        sma_50 = price_data.get('sma_50', 0)
        sma_200 = price_data.get('sma_200', 0)

        if close > sma_20 > sma_50 > sma_200:
            return "bullish"
        elif close < sma_20 < sma_50 < sma_200:
            return "bearish"
        else:
            return "neutral"

    def _classify_vix(self, vix_value: Optional[float]) -> str:
        """Classify VIX level."""
        if vix_value is None:
            return "medium"

        if vix_value < self.vix_low:
            return "low"
        elif vix_value > self.vix_high:
            return "high"
        else:
            return "medium"

    def _calculate_breadth_score(self, breadth_data: Optional[Dict[str, Any]]) -> float:
        """Calculate composite breadth score (0-100)."""
        if not breadth_data:
            return 50.0  # neutral default

        # % of stocks above SMA50
        pct_above_sma50 = breadth_data.get('pct_above_sma50', 50.0)

        # Advance/Decline ratio
        adv_dec = breadth_data.get('advance_decline_ratio', 1.0)
        adv_dec_score = min(100, max(0, 50 + (adv_dec - 1) * 25))

        # New highs vs new lows
        nh_nl = breadth_data.get('new_highs_lows_ratio', 1.0)
        nh_nl_score = min(100, max(0, 50 + (nh_nl - 1) * 25))

        # Composite score
        breadth_score = (pct_above_sma50 + adv_dec_score + nh_nl_score) / 3
        return min(100, max(0, breadth_score))

    def _determine_volatility_regime(self,
                                     vix_value: Optional[float],
                                     vol_data: Optional[Dict[str, Any]]) -> str:
        """Determine volatility regime."""
        if vix_value is not None:
            if vix_value < self.vix_low:
                return "low"
            elif vix_value > self.vix_high:
                return "high"
            else:
                return "normal"

        if vol_data:
            realized_vol = vol_data.get('realized_volatility', 0)
            historical_avg = vol_data.get('historical_avg_vol', 0)

            if realized_vol < historical_avg * 0.8:
                return "low"
            elif realized_vol > historical_avg * 1.3:
                return "high"
            else:
                return "normal"

        return "normal"

    def _calculate_risk_score(self,
                             spy_trend: str,
                             vix_level: str,
                             breadth_score: float,
                             vol_regime: str) -> float:
        """
        Calculate overall risk score (0-100).
        Higher score = more risk (risk-off environment)
        """
        risk_score = 50.0  # baseline

        # SPY trend component (-20 to +20)
        if spy_trend == "bullish":
            risk_score -= 20
        elif spy_trend == "bearish":
            risk_score += 20

        # VIX component (-15 to +15)
        if vix_level == "low":
            risk_score -= 15
        elif vix_level == "high":
            risk_score += 15

        # Breadth component (-15 to +15)
        risk_score += (50 - breadth_score) * 0.3

        # Volatility regime component (-10 to +10)
        if vol_regime == "low":
            risk_score -= 10
        elif vol_regime == "high":
            risk_score += 10

        return min(100, max(0, risk_score))

    def _determine_regime(self,
                         spy_trend: str,
                         qqq_trend: str,
                         vix_level: str,
                         breadth_score: float,
                         vol_regime: str,
                         risk_score: float) -> tuple[MarketRegime, float]:
        """
        Determine the primary market regime and confidence.

        Returns:
            Tuple of (MarketRegime, confidence 0-1)
        """
        # Strong Bull: bullish trend, low VIX, strong breadth
        if (spy_trend == "bullish" and qqq_trend == "bullish" and
            vix_level == "low" and breadth_score > self.breadth_strong):
            return MarketRegime.STRONG_BULL, 0.9

        # Bull: bullish trend, reasonable breadth
        if spy_trend == "bullish" and breadth_score > 50 and risk_score < 40:
            return MarketRegime.BULL, 0.8

        # Bear: bearish trend, high VIX, weak breadth
        if (spy_trend == "bearish" and qqq_trend == "bearish" and
            vix_level == "high" and breadth_score < self.breadth_weak):
            return MarketRegime.BEAR, 0.9

        # High-Vol Risk-Off: high VIX, weak breadth regardless of trend
        if vix_level == "high" and breadth_score < 40:
            return MarketRegime.HIGH_VOL_RISK_OFF, 0.85

        # Low-Vol Risk-On: low VIX, decent breadth
        if vix_level == "low" and breadth_score > 60:
            return MarketRegime.LOW_VOL_RISK_ON, 0.8

        # Correction: neutral/bearish trend but not full bear
        if spy_trend == "bearish" and breadth_score < 50 and vix_level != "high":
            return MarketRegime.CORRECTION, 0.75

        # Neutral: everything else
        return MarketRegime.NEUTRAL, 0.6

    def get_strategy_recommendations(self, regime: MarketRegime) -> Dict[str, str]:
        """
        Get strategy recommendations for a given regime.

        Returns dict with favorability ratings for different strategies.
        """
        recommendations = {
            MarketRegime.STRONG_BULL: {
                "momentum": "favourable",
                "breakouts": "favourable",
                "mean_reversion": "neutral",
                "shorting": "unfavourable",
                "description": "Aggressive momentum and breakout strategies work best"
            },
            MarketRegime.BULL: {
                "momentum": "favourable",
                "breakouts": "favourable",
                "mean_reversion": "neutral",
                "shorting": "unfavourable",
                "description": "Trend-following strategies with moderate risk"
            },
            MarketRegime.NEUTRAL: {
                "momentum": "neutral",
                "breakouts": "neutral",
                "mean_reversion": "favourable",
                "shorting": "neutral",
                "description": "Mixed approach, focus on stock selection over beta"
            },
            MarketRegime.CORRECTION: {
                "momentum": "unfavourable",
                "breakouts": "unfavourable",
                "mean_reversion": "favourable",
                "shorting": "neutral",
                "description": "Defensive positioning, reduce exposure"
            },
            MarketRegime.BEAR: {
                "momentum": "unfavourable",
                "breakouts": "unfavourable",
                "mean_reversion": "neutral",
                "shorting": "favourable",
                "description": "Capital preservation, consider hedging"
            },
            MarketRegime.HIGH_VOL_RISK_OFF: {
                "momentum": "unfavourable",
                "breakouts": "unfavourable",
                "mean_reversion": "unfavourable",
                "shorting": "neutral",
                "description": "Reduce position sizes, increase cash"
            },
            MarketRegime.LOW_VOL_RISK_ON: {
                "momentum": "favourable",
                "breakouts": "favourable",
                "mean_reversion": "neutral",
                "shorting": "unfavourable",
                "description": "Good environment for calibrated risk-taking"
            }
        }

        return recommendations.get(regime, {
            "momentum": "neutral",
            "breakouts": "neutral",
            "mean_reversion": "neutral",
            "shorting": "neutral",
            "description": "No clear regime signal"
        })

    def analyze_from_dataframe(self,
                               df: pl.DataFrame,
                               benchmark_ticker: str = "SPY") -> List[RegimeResult]:
        """
        Analyze regime from a DataFrame with price data.

        Assumes DataFrame has columns for ticker, time, close, sma_20, sma_50, sma_200
        """
        results = []

        # Group by date and get SPY data for each date
        spy_df = df.filter(pl.col("ticker") == benchmark_ticker)

        for row in spy_df.iter_rows(named=True):
            spy_data = {
                'time': row['time'],
                'close': row['close'],
                'sma_20': row.get('sma_20'),
                'sma_50': row.get('sma_50'),
                'sma_200': row.get('sma_200')
            }

            result = self.analyze(spy_data=spy_data)
            results.append(result)

        return results
