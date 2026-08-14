"""Stock scoring and ranking engine."""

from typing import List, Dict, Any, Optional, Tuple
from datetime import date
import polars as pl


class StockScorer:
    """
    Score and rank stocks based on multiple factors.

    Scoring components:
    - Momentum (30%): Price momentum over various periods
    - Breakout (20%): Proximity to highs, breakout patterns
    - Relative Strength (25%): Performance vs SPY and sector
    - Volume (15%): Relative volume, volume trends
    - Market Compatibility (10%): Alignment with current market regime
    """

    def __init__(
        self,
        momentum_weight: float = 0.30,
        breakout_weight: float = 0.20,
        relative_strength_weight: float = 0.25,
        volume_weight: float = 0.15,
        market_compat_weight: float = 0.10
    ):
        self.weights = {
            "momentum": momentum_weight,
            "breakout": breakout_weight,
            "relative_strength": relative_strength_weight,
            "volume": volume_weight,
            "market_compatibility": market_compat_weight
        }

    def calculate_momentum_score(self, features: Dict[str, float]) -> float:
        """
        Calculate momentum sub-score (0-100).

        Factors:
        - 20-day return
        - 60-day return
        - Distance from SMA50
        - Distance from SMA200
        """
        score = 0.0
        components = []

        # 20-day momentum (roc_20)
        roc_20 = features.get("roc_20", 0)
        if roc_20 is not None:
            # Normalize: >20% = 100, <-20% = 0
            roc_20_score = min(100, max(0, (roc_20 + 0.20) * 250))
            components.append(roc_20_score)

        # 60-day momentum (roc_60)
        roc_60 = features.get("roc_60", 0)
        if roc_60 is not None:
            roc_60_score = min(100, max(0, (roc_60 + 0.30) * 200))
            components.append(roc_60_score)

        # Distance from SMA50
        dist_sma_50 = features.get("dist_sma_50_pct", 0)
        if dist_sma_50 is not None:
            # Above SMA50 is good
            sma_50_score = min(100, max(0, (dist_sma_50 + 0.10) * 500))
            components.append(sma_50_score)

        # Distance from SMA200
        dist_sma_200 = features.get("dist_sma_200_pct", 0)
        if dist_sma_200 is not None:
            sma_200_score = min(100, max(0, (dist_sma_200 + 0.10) * 500))
            components.append(sma_200_score)

        if components:
            score = sum(components) / len(components)

        return round(score, 2)

    def calculate_breakout_score(self, features: Dict[str, float]) -> float:
        """
        Calculate breakout sub-score (0-100).

        Factors:
        - Distance from 52-week high
        - 20-day breakout flag
        - Bollinger Band position
        """
        score = 0.0
        components = []

        # Distance from 52-week high (closer to high = better)
        dist_52w = features.get("dist_52w_high_pct", 0)
        if dist_52w is not None:
            # At high (0%) = 100, -20% below = 0
            high_score = min(100, max(0, (dist_52w + 0.20) * 500))
            components.append(high_score)

        # 20-day breakout flag
        is_breakout = features.get("is_20d_breakout", False)
        if is_breakout is not None:
            breakout_score = 100 if is_breakout else 50
            components.append(breakout_score)

        # Bollinger Band position
        bb_pct = features.get("bb_pct", 0.5)
        if bb_pct is not None:
            # Upper half of BB is bullish
            bb_score = min(100, max(0, bb_pct * 100))
            components.append(bb_score)

        if components:
            score = sum(components) / len(components)

        return round(score, 2)

    def calculate_relative_strength_score(self, features: Dict[str, float]) -> float:
        """
        Calculate relative strength sub-score (0-100).

        Note: This requires relative strength vs SPY to be pre-calculated.
        For now, we use absolute momentum as proxy.
        """
        score = 0.0
        components = []

        # Use 20-day ROC as proxy for relative strength
        roc_20 = features.get("roc_20", 0)
        if roc_20 is not None:
            # Top decile (>15%) = 100
            rs_score = min(100, max(0, (roc_20 + 0.15) * 333))
            components.append(rs_score)

        # Use 60-day ROC as well
        roc_60 = features.get("roc_60", 0)
        if roc_60 is not None:
            rs_60_score = min(100, max(0, (roc_60 + 0.20) * 250))
            components.append(rs_60_score)

        if components:
            score = sum(components) / len(components)

        return round(score, 2)

    def calculate_volume_score(self, features: Dict[str, float]) -> float:
        """
        Calculate volume sub-score (0-100).

        Factors:
        - Relative volume
        - Volume trend
        """
        score = 0.0
        components = []

        # Relative volume (>1.5 is good)
        rel_vol = features.get("relative_volume", 1.0)
        if rel_vol is not None:
            # 2.0+ = 100, 1.0 = 50, <0.5 = 0
            vol_score = min(100, max(0, (rel_vol - 0.5) * 66.67))
            components.append(vol_score)

        if components:
            score = sum(components) / len(components)

        return round(score, 2)

    def calculate_market_compatibility_score(
        self,
        features: Dict[str, float],
        market_regime: str = "neutral"
    ) -> float:
        """
        Calculate how well the stock fits the current market regime.

        Regimes: strong_bull, bull, neutral, correction, bear, high_vol
        """
        # Default score if no regime specified
        if not market_regime or market_regime == "neutral":
            return 50.0

        # Bull regimes favor momentum/breakout stocks
        if market_regime in ["strong_bull", "bull"]:
            # High momentum stocks get bonus
            momentum = features.get("roc_20", 0)
            if momentum and momentum > 0.10:
                return 90.0
            elif momentum and momentum > 0:
                return 70.0
            else:
                return 40.0

        # Correction/bear regimes favor defensive stocks
        elif market_regime in ["correction", "bear"]:
            # Low volatility, positive momentum preferred
            atr_pct = features.get("atr_pct", 5)
            momentum = features.get("roc_20", 0)

            if atr_pct and atr_pct < 3 and momentum and momentum > 0:
                return 75.0
            else:
                return 35.0

        # High volatility regime
        elif market_regime == "high_vol":
            # Avoid high beta stocks
            atr_pct = features.get("atr_pct", 5)
            if atr_pct and atr_pct < 4:
                return 60.0
            else:
                return 30.0

        return 50.0

    def calculate_composite_score(
        self,
        features: Dict[str, float],
        market_regime: str = "neutral"
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate composite score and all sub-scores.

        Returns:
            Tuple of (composite_score, sub_scores_dict)
        """
        sub_scores = {
            "momentum": self.calculate_momentum_score(features),
            "breakout": self.calculate_breakout_score(features),
            "relative_strength": self.calculate_relative_strength_score(features),
            "volume": self.calculate_volume_score(features),
            "market_compatibility": self.calculate_market_compatibility_score(
                features, market_regime
            )
        }

        # Calculate weighted composite
        composite = sum(
            sub_scores[key] * self.weights[key]
            for key in sub_scores.keys()
        )

        return round(composite, 2), sub_scores

    def rank_stocks(
        self,
        feature_matrix: pl.DataFrame,
        market_regime: str = "neutral",
        min_price: float = 5.0,
        min_dollar_volume: float = 20_000_000
    ) -> List[Dict[str, Any]]:
        """
        Rank all stocks in the universe.

        Args:
            feature_matrix: DataFrame with columns [asset_id, ticker, ...features...]
            market_regime: Current market regime
            min_price: Minimum price filter
            min_dollar_volume: Minimum dollar volume filter

        Returns:
            List of ranked stocks with scores
        """
        ranked_stocks = []

        # Convert to rows for iteration
        rows = feature_matrix.to_dicts()

        for row in rows:
            ticker = row.get("ticker", "UNKNOWN")
            asset_id = row.get("asset_id")

            # Extract features (exclude non-feature columns)
            features = {
                k: v for k, v in row.items()
                if k not in ["ticker", "asset_id"] and v is not None
            }

            # Calculate scores
            composite_score, sub_scores = self.calculate_composite_score(
                features, market_regime
            )

            # Determine primary setup type
            setup_type = self._identify_setup_type(sub_scores)

            # Determine confidence level
            confidence = self._determine_confidence(composite_score, sub_scores)

            ranked_stocks.append({
                "rank": 0,  # Will be set after sorting
                "asset_id": asset_id,
                "ticker": ticker,
                "composite_score": composite_score,
                "sub_scores": sub_scores,
                "setup_type": setup_type,
                "confidence": confidence,
                "features": features
            })

        # Sort by composite score descending
        ranked_stocks.sort(key=lambda x: x["composite_score"], reverse=True)

        # Assign ranks
        for i, stock in enumerate(ranked_stocks):
            stock["rank"] = i + 1

        return ranked_stocks

    def _identify_setup_type(self, sub_scores: Dict[str, float]) -> str:
        """Identify the primary setup type based on highest sub-scores."""
        max_score = max(sub_scores.values())

        if sub_scores["momentum"] == max_score and max_score > 70:
            return "Momentum"
        elif sub_scores["breakout"] == max_score and max_score > 70:
            return "Breakout"
        elif sub_scores["relative_strength"] == max_score and max_score > 70:
            return "Relative Strength"
        elif sub_scores["volume"] == max_score and max_score > 80:
            return "Volume Surge"
        else:
            return "Mixed Setup"

    def _determine_confidence(self, composite: float, sub_scores: Dict[str, float]) -> str:
        """Determine confidence level based on score consistency."""
        if composite >= 85:
            # Check if scores are consistent (not driven by one factor)
            score_values = list(sub_scores.values())
            avg_score = sum(score_values) / len(score_values)
            min_score = min(score_values)

            if min_score > 60:  # All factors supportive
                return "High"
            else:
                return "Medium"
        elif composite >= 70:
            return "Medium"
        else:
            return "Low"