"""
Backtesting API Routes
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session

from services.backtesting import BacktestEngine, MomentumBreakoutStrategy, WalkForwardAnalyzer
from apps.api.src.core.database import get_db
from apps.api.src.db.models import Asset

router = APIRouter(prefix="/backtest", tags=["backtesting"])


@router.get("/strategies")
async def list_strategies():
    """List available backtesting strategies"""
    return {
        "strategies": [
            {
                "id": "momentum_breakout",
                "name": "Momentum Breakout",
                "description": "Combines momentum, relative strength, and breakout signals",
                "parameters": {
                    "min_relative_strength": {"type": "float", "default": 0.8, "description": "Minimum RS vs SPY"},
                    "min_momentum_score": {"type": "float", "default": 70, "description": "Minimum momentum score"},
                    "min_volume_ratio": {"type": "float", "default": 1.2, "description": "Minimum relative volume"},
                    "holding_period": {"type": "int", "default": 10, "description": "Days to hold"},
                    "stop_loss_pct": {"type": "float", "default": 0.08, "description": "Stop loss percentage"},
                }
            }
        ]
    }


@router.post("/run")
async def run_backtest(
    strategy_id: str = "momentum_breakout",
    start_date: date = date(2020, 1, 1),
    end_date: date = date(2024, 12, 31),
    initial_capital: float = 100000.0,
    position_size_pct: float = 0.1,
    commission_pct: float = 0.001,
    slippage_pct: float = 0.001,
    universe_size: int = 500,
    db: Session = Depends(get_db)
):
    """
    Run a backtest for a specific strategy

    Parameters:
    - strategy_id: Strategy to test
    - start_date: Backtest start date
    - end_date: Backtest end date
    - initial_capital: Starting capital
    - position_size_pct: Max % per position
    - commission_pct: Commission per trade
    - slippage_pct: Expected slippage
    - universe_size: Number of stocks to consider
    """

    # Get universe of stocks
    assets = db.query(Asset).filter(
        Asset.is_active == True,
        Asset.market_cap >= 300000000  # $300M min
    ).limit(universe_size).all()

    if not assets:
        raise HTTPException(status_code=404, detail="No assets found for backtesting")

    tickers = [a.ticker for a in assets]

    # Initialize strategy
    if strategy_id == "momentum_breakout":
        strategy = MomentumBreakoutStrategy(
            min_relative_strength=0.8,
            min_momentum_score=70,
            min_volume_ratio=1.2,
            holding_period=10,
            stop_loss_pct=0.08
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy_id}")

    # Run backtest
    engine = BacktestEngine(
        initial_capital=initial_capital,
        max_position_pct=position_size_pct,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct
    )

    result = engine.run_backtest(
        strategy=strategy,
        tickers=tickers,
        start_date=start_date,
        end_date=end_date
    )

    return {
        "status": "success",
        "backtest_id": "bt_" + str(hash(str(start_date) + str(end_date)))[:8],
        "summary": result.to_dict(),
        "metrics": result.metrics,
        "trade_count": len(result.trades),
        "sample_trades": result.trades[:10]  # First 10 trades
    }


@router.post("/walk-forward")
async def run_walk_forward_analysis(
    strategy_id: str = "momentum_breakout",
    start_date: date = date(2018, 1, 1),
    end_date: date = date(2024, 12, 31),
    training_periods: int = 3,  # Years
    testing_periods: int = 1,   # Year
    step_periods: int = 1,      # Year step
    db: Session = Depends(get_db)
):
    """
    Run walk-forward analysis to test strategy robustness
    """

    assets = db.query(Asset).filter(
        Asset.is_active == True,
        Asset.market_cap >= 300000000
    ).limit(100).all()

    if not assets:
        raise HTTPException(status_code=404, detail="No assets found")

    tickers = [a.ticker for a in assets]

    if strategy_id == "momentum_breakout":
        strategy = MomentumBreakoutStrategy()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy_id}")

    analyzer = WalkForwardAnalyzer(
        strategy=strategy,
        training_periods=training_periods,
        testing_periods=testing_periods,
        step_periods=step_periods
    )

    results = analyzer.run(tickers=tickers, start_date=start_date, end_date=end_date)

    return {
        "status": "success",
        "analysis": results.to_dict(),
        "robustness_score": results.calculate_robustness_score(),
        "is_robust": results.is_robust()
    }


@router.get("/compare")
async def compare_strategies(
    strategies: List[str] = ["momentum_breakout"],
    start_date: date = date(2020, 1, 1),
    end_date: date = date(2024, 12, 31),
    db: Session = Depends(get_db)
):
    """Compare multiple strategies"""

    assets = db.query(Asset).filter(
        Asset.is_active == True,
        Asset.market_cap >= 300000000
    ).limit(200).all()

    tickers = [a.ticker for a in assets]

    comparisons = []

    for strategy_id in strategies:
        if strategy_id == "momentum_breakout":
            strategy = MomentumBreakoutStrategy()
        else:
            continue

        engine = BacktestEngine()
        result = engine.run_backtest(strategy, tickers, start_date, end_date)

        comparisons.append({
            "strategy_id": strategy_id,
            "cagr": result.metrics.get("cagr", 0),
            "sharpe_ratio": result.metrics.get("sharpe_ratio", 0),
            "max_drawdown": result.metrics.get("max_drawdown", 0),
            "total_return": result.metrics.get("total_return", 0),
            "win_rate": result.metrics.get("win_rate", 0)
        })

    # Add benchmark (SPY buy and hold)
    # This would need actual SPY data - simplified here
    benchmark_return = 0.12 * ((end_date - start_date).days / 365)  # Approximate

    return {
        "strategies": comparisons,
        "benchmark": {
            "name": "SPY Buy & Hold",
            "estimated_cagr": 0.12,
            "period_return": benchmark_return
        }
    }