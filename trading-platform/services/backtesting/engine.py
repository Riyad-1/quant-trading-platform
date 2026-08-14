"""
Backtest Engine Module
Core backtesting engine with vectorized execution
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import polars as pl
from datetime import date
import numpy as np

from .strategy import Strategy, StrategyConfig, MomentumBreakoutStrategy
from .metrics import PerformanceMetrics


@dataclass
class Trade:
    """Represents a single trade"""
    ticker: str
    entry_date: date
    entry_price: float
    exit_date: Optional[date]
    exit_price: Optional[float]
    quantity: int
    side: str  # "long" or "short"
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_period: int = 0
    exit_reason: str = "open"  # open, target, stop, signal_reverse


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float

    # Equity curves
    equity_curve: pl.DataFrame  # [date, equity, cash, holdings_value]
    benchmark_curve: Optional[pl.DataFrame]

    # Trades
    trades: List[Trade]

    # Metrics
    metrics: PerformanceMetrics

    # Metadata
    total_signals: int = 0
    avg_score: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "strategy_name": self.strategy_name,
            "start_date": str(self.start_date),
            "end_date": str(self.end_date),
            "initial_capital": round(self.initial_capital, 2),
            "final_equity": round(self.final_equity, 2),
            "total_return": round((self.final_equity / self.initial_capital) - 1, 4),
            "equity_curve": self.equity_curve.to_dicts()[-100:],  # Last 100 points
            "trades": [
                {
                    "ticker": t.ticker,
                    "entry_date": str(t.entry_date),
                    "exit_date": str(t.exit_date) if t.exit_date else None,
                    "entry_price": round(t.entry_price, 2),
                    "exit_price": round(t.exit_price, 2) if t.exit_price else None,
                    "quantity": t.quantity,
                    "side": t.side,
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 4),
                    "holding_period": t.holding_period,
                    "exit_reason": t.exit_reason
                }
                for t in self.trades[-50:]  # Last 50 trades
            ],
            "metrics": self.metrics.to_dict(),
            "total_signals": self.total_signals,
            "avg_score": round(self.avg_score, 2)
        }


class BacktestEngine:
    """
    Vectorized backtesting engine

    Features:
    - Event-driven simulation
    - Realistic transaction costs and slippage
    - Position sizing constraints
    - Stop loss and take profit
    - Benchmark comparison
    """

    def __init__(self, initial_capital: float = 100_000):
        self.initial_capital = initial_capital

    def run(
        self,
        data: pl.DataFrame,
        strategy: Strategy,
        benchmark_data: Optional[pl.DataFrame] = None,
        config: Optional[StrategyConfig] = None
    ) -> BacktestResult:
        """
        Run backtest

        Args:
             DataFrame with OHLCV and features, columns: timestamp, ticker, open, high, low, close, volume, ...features
            strategy: Strategy instance
            benchmark_data: Optional benchmark price data (e.g., SPY)
            config: Strategy configuration

        Returns:
            BacktestResult with equity curve, trades, and metrics
        """
        if config is None:
            config = strategy.config

        # Generate signals
        signals_df = strategy.generate_signals(data)

        # Filter to only buy signals (long-only for now)
        buy_signals = signals_df.filter(pl.col("signal") == 1)

        if len(buy_signals) == 0:
            # No signals, return empty result
            return self._empty_result(strategy.name, data)

        # Simulate trades
        trades = []
        positions = {}  # ticker -> position info

        # Track daily equity
        dates = sorted(data["timestamp"].unique())
        equity_history = []
        cash = self.initial_capital

        current_date_idx = 0
        signals_by_date = {}

        # Index signals by date
        for row in buy_signals.iter_rows(named=True):
            d = row["timestamp"]
            if d not in signals_by_date:
                signals_by_date[d] = []
            signals_by_date[d].append(row)

        # Process each day
        for current_date in dates:
            # Check for exits first (stops/targets)
            exited_positions = []
            for ticker, pos in list(positions.items()):
                # Get today's price data
                day_data = data.filter(
                    (pl.col("timestamp") == current_date) &
                    (pl.col("ticker") == ticker)
                )

                if len(day_data) == 0:
                    continue

                row = day_data.to_dicts()[0]
                current_price = row["close"]
                current_high = row.get("high", current_price)
                current_low = row.get("low", current_price)

                # Check stop loss
                stop_price = pos["entry_price"] * (1 - config.stop_loss_pct)
                if current_low <= stop_price:
                    # Stopped out
                    exit_price = stop_price
                    pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                    pnl_pct = (exit_price / pos["entry_price"]) - 1

                    trades.append(Trade(
                        ticker=ticker,
                        entry_date=pos["entry_date"],
                        entry_price=pos["entry_price"],
                        exit_date=current_date,
                        exit_price=exit_price,
                        quantity=pos["quantity"],
                        side="long",
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        holding_period=(current_date - pos["entry_date"]).days,
                        exit_reason="stop_loss"
                    ))

                    cash += pos["quantity"] * exit_price
                    exited_positions.append(ticker)
                    continue

                # Check take profit
                target_price = pos["entry_price"] * (1 + config.take_profit_pct)
                if current_high >= target_price:
                    # Target hit
                    exit_price = target_price
                    pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                    pnl_pct = (exit_price / pos["entry_price"]) - 1

                    trades.append(Trade(
                        ticker=ticker,
                        entry_date=pos["entry_date"],
                        entry_price=pos["entry_price"],
                        exit_date=current_date,
                        exit_price=exit_price,
                        quantity=pos["quantity"],
                        side="long",
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        holding_period=(current_date - pos["entry_date"]).days,
                        exit_reason="target"
                    ))

                    cash += pos["quantity"] * exit_price
                    exited_positions.append(ticker)
                    continue

                # Check if signal reversed (exit on signal loss)
                # For simplicity, hold until stop/target or max holding period
                max_hold_days = config.holding_period * 7  # Approximate trading days
                if (current_date - pos["entry_date"]).days >= max_hold_days:
                    exit_price = current_price
                    pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                    pnl_pct = (exit_price / pos["entry_price"]) - 1

                    trades.append(Trade(
                        ticker=ticker,
                        entry_date=pos["entry_date"],
                        entry_price=pos["entry_price"],
                        exit_date=current_date,
                        exit_price=exit_price,
                        quantity=pos["quantity"],
                        side="long",
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        holding_period=(current_date - pos["entry_date"]).days,
                        exit_reason="time_exit"
                    ))

                    cash += pos["quantity"] * exit_price
                    exited_positions.append(ticker)

            # Remove exited positions
            for ticker in exited_positions:
                del positions[ticker]

            # Check for new entries
            if current_date in signals_by_date:
                for signal_row in signals_by_date[current_date]:
                    ticker = signal_row["ticker"]
                    score = signal_row.get("score", 70)

                    # Skip if already have position
                    if ticker in positions:
                        continue

                    # Get price data
                    day_data = data.filter(
                        (pl.col("timestamp") == current_date) &
                        (pl.col("ticker") == ticker)
                    )

                    if len(day_data) == 0:
                        continue

                    row = day_data.to_dicts()[0]
                    entry_price = row["close"]
                    volume = row.get("volume", 0)

                    # Apply filters
                    if entry_price < config.min_price:
                        continue
                    if volume < config.min_volume:
                        continue

                    # Calculate position size
                    position_value = min(
                        cash * config.max_position_pct,
                        cash / config.max_portfolio_positions
                    )

                    if position_value < entry_price:  # Can't afford even 1 share
                        continue

                    quantity = int(position_value / entry_price)
                    if quantity < 1:
                        continue

                    # Apply transaction costs and slippage
                    effective_price = entry_price * (1 + config.slippage_pct + config.transaction_cost_pct)

                    cost = quantity * effective_price
                    if cost > cash:
                        quantity = int(cash / effective_price)
                        cost = quantity * effective_price

                    if quantity < 1:
                        continue

                    # Open position
                    positions[ticker] = {
                        "entry_date": current_date,
                        "entry_price": effective_price,
                        "quantity": quantity,
                    }

                    cash -= cost

            # Calculate current equity
            holdings_value = 0
            for ticker, pos in positions.items():
                # Get current price
                day_data = data.filter(
                    (pl.col("timestamp") == current_date) &
                    (pl.col("ticker") == ticker)
                )
                if len(day_data) > 0:
                    current_price = day_data["close"][0]
                    holdings_value += pos["quantity"] * current_price

            total_equity = cash + holdings_value
            equity_history.append({
                "date": current_date,
                "equity": total_equity,
                "cash": cash,
                "holdings_value": holdings_value
            })

        # Close any remaining positions at the end
        final_date = dates[-1]
        for ticker, pos in list(positions.items()):
            day_data = data.filter(
                (pl.col("timestamp") == final_date) &
                (pl.col("ticker") == ticker)
            )
            if len(day_data) > 0:
                exit_price = day_data["close"][0]
                pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                pnl_pct = (exit_price / pos["entry_price"]) - 1

                trades.append(Trade(
                    ticker=ticker,
                    entry_date=pos["entry_date"],
                    entry_price=pos["entry_price"],
                    exit_date=final_date,
                    exit_price=exit_price,
                    quantity=pos["quantity"],
                    side="long",
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    holding_period=(final_date - pos["entry_date"]).days,
                    exit_reason="end_of_backtest"
                ))

                cash += pos["quantity"] * exit_price

        final_equity = cash

        # Create equity curve DataFrame
        equity_df = pl.DataFrame(equity_history)

        # Create benchmark curve if provided
        benchmark_curve = None
        if benchmark_data is not None:
            # Simple benchmark: buy and hold SPY
            benchmark_start = benchmark_data.filter(pl.col("timestamp") >= dates[0])
            if len(benchmark_start) > 0:
                spy_start_price = benchmark_start.sort("timestamp")[0]["close"]
                benchmark_curve = benchmark_data.with_columns([
                    ((pl.col("close") / spy_start_price) * self.initial_capital).alias("equity")
                ]).select(["timestamp", "equity"])
                benchmark_curve = benchmark_curve.rename({"timestamp": "date"})

        # Calculate metrics
        metrics = PerformanceMetrics.calculate(
            equity_curve=equity_df.select(["date", "equity"]),
            benchmark_curve=benchmark_curve,
            trades=pl.DataFrame([
                {
                    "ticker": t.ticker,
                    "entry_date": t.entry_date,
                    "exit_date": t.exit_date,
                    "pnl": t.pnl,
                    "pnl_pct": t.pnl_pct,
                    "holding_period": t.holding_period
                }
                for t in trades
            ]) if trades else None
        )

        # Calculate average score
        avg_score = buy_signals["score"].mean() if len(buy_signals) > 0 else 0

        return BacktestResult(
            strategy_name=strategy.name,
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=self.initial_capital,
            final_equity=final_equity,
            equity_curve=equity_df,
            benchmark_curve=benchmark_curve,
            trades=trades,
            metrics=metrics,
            total_signals=len(buy_signals),
            avg_score=avg_score
        )

    def _empty_result(self, strategy_name: str, data: pl.DataFrame) -> BacktestResult:
        """Return empty result when no signals generated"""
        dates = sorted(data["timestamp"].unique())
        equity_df = pl.DataFrame([
            {"date": d, "equity": self.initial_capital}
            for d in dates
        ])

        metrics = PerformanceMetrics(
            total_return=0.0,
            cagr=0.0,
            annual_return=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown=0.0,
            avg_drawdown=0.0,
            max_drawdown_duration_days=0,
            volatility_annual=0.0,
            downside_deviation=0.0,
            beta=0.0,
            alpha=0.0,
            correlation_to_benchmark=0.0,
            excess_return=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            avg_winner=0.0,
            avg_loser=0.0,
            profit_factor=0.0,
            expectancy=0.0,
            turnover=0.0,
            avg_holding_period=0.0
        )

        return BacktestResult(
            strategy_name=strategy_name,
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=self.initial_capital,
            final_equity=self.initial_capital,
            equity_curve=equity_df,
            benchmark_curve=None,
            trades=[],
            metrics=metrics,
            total_signals=0,
            avg_score=0.0
        )
