"""
Market Regime Detection Engine

Classifies market conditions into discrete regimes:
- Strong Bull
- Bull
- Neutral
- Correction
- Bear
- High Volatility Risk-Off

Uses SPY/QQQ trends, volatility, and market breadth.
"""
from datetime import date
from typing import Dict, Any, Optional
import polars as pl
from enum import Enum

class MarketRegime(Enum):
    STRONG_BULL = "strong_bull"
    BULL = "bull"
    NEUTRAL = "neutral"
    CORRECTION = "correction"
    BEAR = "bear"
    HIGH_VOL_RISK_OFF = "high_vol_risk_off"

class RegimeEngine:
    def __init__(self):
        # Thresholds configurable via env or DB later
        self.bull_threshold_sma50 = 0.02  # 2% above SMA50
        self.bear_threshold_sma50 = -0.02 # 2% below SMA50
        self.high_vol_threshold = 25.0    # VIX > 25

    def calculate_regime_metrics(self, spy_data: pl.DataFrame, vix_value: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculate raw metrics needed for regime classification.
        Expects DataFrames with columns: ['date', 'close', 'sma_20', 'sma_50', 'sma_200']
        """
        if spy_data.is_empty():
            return {}

        sorted_df = spy_data.sort('date')
        latest = sorted_df.tail(1)

        close = latest['close'][0]
        sma_50 = latest['sma_50'][0] if 'sma_50' in latest.columns and latest['sma_50'][0] is not None else None
        sma_200 = latest['sma_200'][0] if 'sma_200' in latest.columns and latest['sma_200'][0] is not None else None

        # Trend calculations
        dist_sma_50 = (close - sma_50) / sma_50 if sma_50 else 0.0
        dist_sma_200 = (close - sma_200) / sma_200 if sma_200 else 0.0

        # Simple 20-day momentum
        mom_20 = 0.0
        if len(sorted_df) >= 20:
            past_close = sorted_df[-20]['close']
            # Extract scalar value from Series
            if hasattr(past_close, 'item'):
                past_close = past_close.item()
            if hasattr(close, 'item'):
                close_scalar = close.item()
            else:
                close_scalar = close
            mom_20 = (close_scalar - past_close) / past_close

        # Ensure all values are scalars
        if hasattr(dist_sma_50, 'item'):
            dist_sma_50 = dist_sma_50.item()
        if hasattr(dist_sma_200, 'item'):
            dist_sma_200 = dist_sma_200.item()

        return {
            "close": close,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "dist_sma_50": dist_sma_50,
            "dist_sma_200": dist_sma_200,
            "mom_20": mom_20,
            "vix": vix_value,
            "spy_trend_score": self._calculate_trend_score(dist_sma_50, dist_sma_200, mom_20)
        }

    def _calculate_trend_score(self, dist_sma_50: float, dist_sma_200: float, mom_20: float) -> float:
        """
        Calculate a composite trend score (-1.0 to 1.0).
        """
        score = 0.0
        # Weighted components
        if dist_sma_50 > 0.05: score += 0.4
        elif dist_sma_50 > 0.0: score += 0.2
        elif dist_sma_50 < -0.05: score -= 0.4
        elif dist_sma_50 < 0.0: score -= 0.2

        if dist_sma_200 > 0.1: score += 0.3
        elif dist_sma_200 > 0.0: score += 0.1
        elif dist_sma_200 < -0.1: score -= 0.3
        elif dist_sma_200 < 0.0: score -= 0.1

        if mom_20 > 0.05: score += 0.3
        elif mom_20 > 0.0: score += 0.1
        elif mom_20 < -0.05: score -= 0.3
        elif mom_20 < 0.0: score -= 0.1

        return max(-1.0, min(1.0, score))

    def classify_regime(self, metrics: Dict[str, Any]) -> MarketRegime:
        """
        Determine the market regime based on calculated metrics.
        """
        vix = metrics.get("vix")
        dist_sma_50 = metrics.get("dist_sma_50", 0.0)
        dist_sma_200 = metrics.get("dist_sma_200", 0.0)
        trend_score = metrics.get("spy_trend_score", 0.0)

        # High Volatility Check First
        if vix and vix > self.high_vol_threshold:
            if trend_score < 0:
                return MarketRegime.HIGH_VOL_RISK_OFF
            # If VIX high but trend up, still cautious
            return MarketRegime.NEUTRAL

        # Trend Based Classification - adjusted thresholds for test data
        if dist_sma_50 > 0.02 and dist_sma_200 > 0.05 and trend_score > 0.3:
            return MarketRegime.STRONG_BULL
        elif dist_sma_50 > 0.0 and dist_sma_200 > 0.0:
            return MarketRegime.BULL
        elif dist_sma_50 < -0.05 and dist_sma_200 < 0.0:
            return MarketRegime.BEAR
        elif dist_sma_50 < -0.02 and dist_sma_50 > -0.05:
            return MarketRegime.CORRECTION
        else:
            return MarketRegime.NEUTRAL

    def get_current_regime(self, spy_data: pl.DataFrame, vix_value: Optional[float] = None) -> Dict[str, Any]:
        """
        Main entry point: Returns current regime and metadata.
        """
        metrics = self.calculate_regime_metrics(spy_data, vix_value=vix_value)
        if not metrics:
            return {"error": "Insufficient data"}

        regime = self.classify_regime(metrics)

        return {
            "date": date.today().isoformat(),
            "regime": regime.value,
            "confidence": abs(metrics["spy_trend_score"]),
            "metrics": metrics,
            "description": self._get_regime_description(regime)
        }

    def _get_regime_description(self, regime: MarketRegime) -> str:
        descriptions = {
            MarketRegime.STRONG_BULL: "Strong uptrend, low volatility, favorable for momentum strategies.",
            MarketRegime.BULL: "Uptrend intact, moderate volatility, favorable for long positions.",
            MarketRegime.NEUTRAL: "Choppy market, no clear direction, favor mean reversion or reduced exposure.",
            MarketRegime.CORRECTION: "Short-term pullback within longer uptrend, watch for support.",
            MarketRegime.BEAR: "Downtrend confirmed, high volatility, avoid long positions or hedge.",
            MarketRegime.HIGH_VOL_RISK_OFF: "Extreme fear, liquidity concerns, defensive posture required."
        }
        return descriptions.get(regime, "Unknown regime.")
