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

from .regime_detector import MarketRegime, MarketRegimeDetector, RegimeResult

__all__ = ["MarketRegime", "MarketRegimeDetector", "RegimeResult"]