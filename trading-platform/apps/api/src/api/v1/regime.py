"""Market Regime API endpoints."""

from fastapi import APIRouter, HTTPException, Depends
from datetime import date
from typing import List, Optional, Dict, Any

from services.regime.regime_detector import MarketRegimeDetector, MarketRegime

router = APIRouter(prefix="/regime", tags=["market-regime"])

# In-memory cache for latest regime (in production, use Redis)
_regime_cache: Dict[str, Any] = {}


@router.get("/current")
async def get_current_regime() -> Dict[str, Any]:
    """
    Get the current market regime classification.

    Returns regime analysis including:
    - Current regime (strong_bull, bull, neutral, correction, bear, etc.)
    - Confidence level
    - SPY trend
    - VIX level
    - Breadth score
    - Risk score
    - Strategy recommendations
    """
    # In production, this would fetch latest data from database
    # For now, return cached or calculate from mock data

    if "latest" in _regime_cache:
        result = _regime_cache["latest"]

        detector = MarketRegimeDetector()
        regime_enum = MarketRegime(result["regime"])
        recommendations = detector.get_strategy_recommendations(regime_enum)

        return {
            **result,
            "strategy_recommendations": recommendations
        }

    # Return default if no data
    return {
        "date": date.today().isoformat(),
        "regime": "neutral",
        "confidence": 0.6,
        "spy_trend": "neutral",
        "vix_level": "medium",
        "breadth_score": 50.0,
        "volatility_regime": "normal",
        "risk_score": 50.0,
        "strategy_recommendations": {
            "momentum": "neutral",
            "breakouts": "neutral",
            "mean_reversion": "favourable",
            "shorting": "neutral",
            "description": "Mixed approach, focus on stock selection over beta"
        }
    }


@router.get("/history")
async def get_regime_history(
    days: int = 30,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Get historical market regime classifications.

    Args:
        days: Number of days of history (default: 30)
        start_date: Optional start date
        end_date: Optional end date

    Returns:
        List of regime results for each day
    """
    # In production, query database for historical regimes
    # For now, return mock data

    from datetime import timedelta

    if start_date is None:
        end_date = end_date or date.today()
        start_date = end_date - timedelta(days=days)

    # Generate mock history
    history = []
    current_date = start_date

    detector = MarketRegimeDetector()

    while current_date <= end_date:
        # Mock data generation - in production this would be real analysis
        mock_spy_data = {
            'time': current_date,
            'close': 430 + (current_date.day % 10),
            'sma_20': 425 + (current_date.day % 8),
            'sma_50': 420 + (current_date.day % 6),
            'sma_200': 410 + (current_date.day % 5)
        }

        result = detector.analyze(spy_data=mock_spy_data)
        history.append(result.to_dict())

        current_date += timedelta(days=1)

    return history


@router.get("/recommendations")
async def get_strategy_recommendations(regime: Optional[str] = None) -> Dict[str, Any]:
    """
    Get strategy recommendations based on current or specified regime.

    Args:
        regime: Optional regime to get recommendations for.
                If not provided, uses current regime.

    Returns:
        Strategy favorability ratings and description
    """
    detector = MarketRegimeDetector()

    if regime:
        try:
            regime_enum = MarketRegime(regime)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid regime. Valid values: {[r.value for r in MarketRegime]}"
            )
    else:
        # Get current regime
        current = await get_current_regime()
        regime_enum = MarketRegime(current["regime"])

    recommendations = detector.get_strategy_recommendations(regime_enum)

    return {
        "regime": regime_enum.value,
        **recommendations
    }


@router.post("/analyze")
async def analyze_market_conditions(
    spy_data: Dict[str, Any],
    qqq_data: Optional[Dict[str, Any]] = None,
    vix_value: Optional[float] = None,
    breadth_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Analyze custom market conditions.

    This endpoint allows submitting custom market data for regime analysis.

    Args:
        spy_data: SPY price data with close, sma_20, sma_50, sma_200
        qqq_data: Optional QQQ price data
        vix_value: Optional VIX value
        breadth_data: Optional market breadth indicators

    Returns:
        Complete regime analysis result
    """
    detector = MarketRegimeDetector()

    try:
        result = detector.analyze(
            spy_data=spy_data,
            qqq_data=qqq_data,
            vix_value=vix_value,
            breadth_data=breadth_data
        )

        # Cache the result
        _regime_cache["latest"] = result.to_dict()

        recommendations = detector.get_strategy_recommendations(result.regime)

        return {
            **result.to_dict(),
            "strategy_recommendations": recommendations
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/risk-score")
async def get_risk_score() -> Dict[str, Any]:
    """
    Get current market risk score.

    Returns a score from 0-100 where higher values indicate
    higher risk (risk-off environment).
    """
    current = await get_current_regime()

    risk_score = current["risk_score"]

    # Categorize risk level
    if risk_score < 30:
        risk_level = "low"
        description = "Favorable risk environment, can take calibrated risks"
    elif risk_score < 50:
        risk_level = "moderate"
        description = "Normal risk environment, maintain standard position sizing"
    elif risk_score < 70:
        risk_level = "elevated"
        description = "Elevated risk, consider reducing exposure"
    else:
        risk_level = "high"
        description = "High risk environment, preserve capital, reduce positions"

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "description": description,
        "date": current["date"],
        "regime": current["regime"]
    }
