"""Bias-conscious SPY backtesting endpoints."""

from datetime import date, timedelta
from math import sqrt
from typing import Any

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool


router = APIRouter(prefix="/backtest", tags=["backtesting"])


def _metrics(equity: pd.Series, initial_capital: float) -> dict[str, float]:
    daily_returns = equity.pct_change().dropna()
    years = max((equity.index[-1] - equity.index[0]).days / 365.2425, 1 / 252)
    roi = float(equity.iloc[-1] / initial_capital - 1)
    volatility = float(daily_returns.std(ddof=0) * sqrt(252)) if len(daily_returns) else 0.0
    daily_std = float(daily_returns.std(ddof=0)) if len(daily_returns) else 0.0
    drawdown = equity / equity.cummax() - 1

    return {
        "final_equity": float(equity.iloc[-1]),
        "roi": roi,
        "cagr": float((equity.iloc[-1] / initial_capital) ** (1 / years) - 1),
        "max_drawdown": float(drawdown.min()),
        "volatility": volatility,
        "sharpe_zero_rf": (
            float(daily_returns.mean() / daily_std * sqrt(252))
            if daily_std > 0
            else 0.0
        ),
    }


def _run_spy_trend(
    start_date: date,
    end_date: date,
    initial_capital: float,
    sma_period: int,
    commission_bps: float,
    slippage_bps: float,
) -> dict[str, Any]:
    warmup_start = start_date - timedelta(days=max(500, sma_period * 3))
    download_end = end_date + timedelta(days=1)
    data = yf.download(
        "SPY",
        start=warmup_start.isoformat(),
        end=download_end.isoformat(),
        interval="1d",
        auto_adjust=True,
        repair=True,
        progress=False,
        threads=False,
        multi_level_index=False,
    )

    if data.empty:
        raise ValueError("Yahoo Finance returned no SPY price history")

    frame = data[["Open", "Close"]].dropna().copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame["sma"] = frame["Close"].rolling(sma_period, min_periods=sma_period).mean()
    frame["signal"] = (frame["Close"] > frame["sma"]).astype(int)
    frame["desired_at_open"] = frame["signal"].shift(1).fillna(0).astype(int)
    frame = frame.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)].copy()

    if len(frame) < 2:
        raise ValueError("The selected period does not contain enough completed sessions")

    one_way_cost = (commission_bps + slippage_bps) / 10_000
    cash = initial_capital
    shares = 0.0
    holding = False
    entries = 0
    exits = 0
    exposure_days = 0
    equity_values: list[float] = []

    for _, row in frame.iterrows():
        desired = bool(row["desired_at_open"])
        open_price = float(row["Open"])
        close_price = float(row["Close"])

        if desired and not holding:
            shares = cash / (open_price * (1 + one_way_cost))
            cash = 0.0
            holding = True
            entries += 1
        elif not desired and holding:
            cash = shares * open_price * (1 - one_way_cost)
            shares = 0.0
            holding = False
            exits += 1

        if holding:
            exposure_days += 1
        equity_values.append(cash + shares * close_price)

    if holding:
        cash = shares * float(frame.iloc[-1]["Close"]) * (1 - one_way_cost)
        equity_values[-1] = cash
        exits += 1

    strategy_equity = pd.Series(equity_values, index=frame.index, dtype=float)
    benchmark_units = initial_capital / (float(frame.iloc[0]["Open"]) * (1 + one_way_cost))
    benchmark_equity = benchmark_units * frame["Close"].astype(float)
    benchmark_equity.iloc[-1] = (
        benchmark_units * float(frame.iloc[-1]["Close"]) * (1 - one_way_cost)
    )

    max_points = 320
    step = max(1, len(frame) // max_points)
    sampled_indices = list(range(0, len(frame), step))
    if sampled_indices[-1] != len(frame) - 1:
        sampled_indices.append(len(frame) - 1)

    curve = [
        {
            "date": frame.index[index].date().isoformat(),
            "strategy": round(float(strategy_equity.iloc[index]), 2),
            "benchmark": round(float(benchmark_equity.iloc[index]), 2),
        }
        for index in sampled_indices
    ]

    strategy_metrics = _metrics(strategy_equity, initial_capital)
    benchmark_metrics = _metrics(benchmark_equity, initial_capital)

    return {
        "ticker": "SPY",
        "strategy_name": f"SPY {sma_period}-day trend filter",
        "data_source": "Yahoo Finance adjusted daily OHLC",
        "start_date": frame.index[0].date().isoformat(),
        "end_date": frame.index[-1].date().isoformat(),
        "initial_capital": initial_capital,
        "commission_bps": commission_bps,
        "slippage_bps": slippage_bps,
        "execution": "Signal after close; execute at next session open",
        "strategy": strategy_metrics,
        "benchmark": benchmark_metrics,
        "excess_roi": strategy_metrics["roi"] - benchmark_metrics["roi"],
        "entries": entries,
        "exits": exits,
        "market_exposure": exposure_days / len(frame),
        "equity_curve": curve,
        "limitations": [
            "Fractional shares are used",
            "Cash earns no interest",
            "Taxes and market impact are excluded",
            "Historical results are not investment advice",
        ],
    }


@router.get("/strategies")
async def list_strategies() -> dict[str, Any]:
    return {
        "strategies": [
            {
                "id": "spy_sma_trend",
                "name": "SPY moving-average trend filter",
                "description": "Long SPY above its moving average; otherwise hold cash.",
                "default_sma_period": 200,
            }
        ]
    }


@router.post("/run")
async def run_backtest(
    start_date: date = Query(default=date(2015, 1, 1)),
    end_date: date = Query(default_factory=lambda: date.today() - timedelta(days=1)),
    initial_capital: float = Query(default=100_000, ge=1_000, le=100_000_000),
    sma_period: int = Query(default=200, ge=50, le=300),
    commission_bps: float = Query(default=5, ge=0, le=100),
    slippage_bps: float = Query(default=5, ge=0, le=100),
) -> dict[str, Any]:
    if end_date <= start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")
    if (end_date - start_date).days < 365:
        raise HTTPException(status_code=400, detail="Select at least one year of history")

    try:
        return await run_in_threadpool(
            _run_spy_trend,
            start_date,
            end_date,
            initial_capital,
            sma_period,
            commission_bps,
            slippage_bps,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Market data request failed: {exc}") from exc
