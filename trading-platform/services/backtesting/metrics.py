"""
Performance Metrics Module
Calculates comprehensive trading performance statistics
"""
from dataclasses import dataclass
from typing import List, Optional
import polars as pl
import numpy as np


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a strategy"""

    # Returns
    total_return: float
    cagr: float
    annual_return: float

    # Risk-adjusted metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Drawdown
    max_drawdown: float
    avg_drawdown: float
    max_drawdown_duration_days: int

    # Volatility
    volatility_annual: float
    downside_deviation: float

    # Benchmark comparison
    beta: float
    alpha: float
    correlation_to_benchmark: float
    excess_return: float

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_winner: float
    avg_loser: float
    profit_factor: float
    expectancy: float

    # Other
    turnover: float
    avg_holding_period: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_return": round(self.total_return, 4),
            "cagr": round(self.cagr, 4),
            "annual_return": round(self.annual_return, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "sortino_ratio": round(self.sortino_ratio, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "max_drawdown": round(self.max_drawdown, 4),
            "avg_drawdown": round(self.avg_drawdown, 4),
            "max_drawdown_duration_days": self.max_drawdown_duration_days,
            "volatility_annual": round(self.volatility_annual, 4),
            "downside_deviation": round(self.downside_deviation, 4),
            "beta": round(self.beta, 3),
            "alpha": round(self.alpha, 4),
            "correlation_to_benchmark": round(self.correlation_to_benchmark, 3),
            "excess_return": round(self.excess_return, 4),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 3),
            "avg_winner": round(self.avg_winner, 4),
            "avg_loser": round(self.avg_loser, 4),
            "profit_factor": round(self.profit_factor, 2),
            "expectancy": round(self.expectancy, 4),
            "turnover": round(self.turnover, 3),
            "avg_holding_period": round(self.avg_holding_period, 1),
        }

    @classmethod
    def calculate(
        cls,
        equity_curve: pl.DataFrame,
        benchmark_curve: Optional[pl.DataFrame] = None,
        trades: Optional[pl.DataFrame] = None,
        risk_free_rate: float = 0.02
    ) -> "PerformanceMetrics":
        """
        Calculate all performance metrics from equity curve

        Args:
            equity_curve: DataFrame with columns [date, equity]
            benchmark_curve: Optional benchmark DataFrame [date, equity]
            trades: Optional DataFrame of individual trades
            risk_free_rate: Annual risk-free rate
        """
        # Ensure sorted by date
        equity_curve = equity_curve.sort("date")

        # Calculate daily returns
        df = equity_curve.with_columns([
            (pl.col("equity").pct_change()).fill_null(0).alias("daily_return")
        ])

        returns = np.asarray(df["daily_return"].to_numpy(), dtype=float)
        dates = df["date"].to_numpy()

        # Basic returns
        total_equity = equity_curve["equity"][-1]
        starting_equity = equity_curve["equity"][0]
        total_return = (total_equity / starting_equity) - 1

        n_years = len(dates) / 252.0
        cagr = (total_equity / starting_equity) ** (1 / n_years) - 1 if n_years > 0 else 0
        annual_return = cagr

        # Volatility and Sharpe
        volatility_daily = np.std(returns)
        volatility_annual = volatility_daily * np.sqrt(252)

        excess_returns = returns - (risk_free_rate / 252)
        sharpe_ratio = (np.mean(excess_returns) / volatility_daily) * np.sqrt(252) if volatility_daily > 0 else 0

        # Sortino (downside deviation)
        negative_returns = returns[returns < 0]
        downside_deviation = np.std(negative_returns) if len(negative_returns) > 0 else 0
        sortino_ratio = (np.mean(excess_returns) / downside_deviation) * np.sqrt(252) if downside_deviation > 0 else 0

        # Drawdown analysis
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max

        max_drawdown = np.min(drawdowns)
        avg_drawdown = np.mean(drawdowns[drawdowns < 0]) if np.any(drawdowns < 0) else 0

        # Max drawdown duration
        in_drawdown = drawdowns < 0
        drawdown_duration = 0
        max_duration = 0
        for dd in in_drawdown:
            if dd:
                drawdown_duration += 1
                max_duration = max(max_duration, drawdown_duration)
            else:
                drawdown_duration = 0

        calmar_ratio = cagr / abs(max_drawdown) if max_drawdown != 0 else 0

        # Benchmark comparison
        if benchmark_curve is not None:
            benchmark_curve = benchmark_curve.sort("date")
            bench_returns = np.asarray(benchmark_curve.with_columns([
                (pl.col("equity").pct_change()).fill_null(0).alias("daily_return")
            ])["daily_return"].to_numpy(), dtype=float)

            # Beta and Alpha
            if len(returns) == len(bench_returns) and len(returns) > 1:
                covariance = np.cov(returns, bench_returns)[0, 1]
                bench_variance = np.var(bench_returns)
                beta = covariance / bench_variance if bench_variance > 0 else 1

                benchmark_total_return = (benchmark_curve["equity"][-1] / benchmark_curve["equity"][0]) - 1
                excess_return = total_return - benchmark_total_return
                alpha = cagr - (risk_free_rate + beta * (benchmark_total_return / n_years - risk_free_rate)) if n_years > 0 else 0

                correlation = np.corrcoef(returns, bench_returns)[0, 1] if len(returns) > 1 else 0
            else:
                beta, alpha, excess_return, correlation = 1.0, 0.0, 0.0, 0.0
        else:
            beta, alpha, excess_return, correlation = 1.0, 0.0, 0.0, 0.0

        # Trade statistics
        if trades is not None and len(trades) > 0:
            total_trades = len(trades)
            winning_trades = len(trades.filter(pl.col("pnl") > 0))
            losing_trades = len(trades.filter(pl.col("pnl") <= 0))
            win_rate = winning_trades / total_trades if total_trades > 0 else 0

            winners = np.asarray(trades.filter(pl.col("pnl") > 0)["pnl"].to_numpy(), dtype=float)
            losers = np.asarray(trades.filter(pl.col("pnl") <= 0)["pnl"].to_numpy(), dtype=float)

            avg_winner = np.mean(winners) if len(winners) > 0 else 0
            avg_loser = np.mean(losers) if len(losers) > 0 else 0

            gross_profit = np.sum(winners) if len(winners) > 0 else 0
            gross_loss = abs(np.sum(losers)) if len(losers) > 0 else 1
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

            expectancy = (win_rate * avg_winner) - ((1 - win_rate) * abs(avg_loser))

            holding_periods = np.asarray(trades["holding_period"].to_numpy(), dtype=float)
            avg_holding_period = np.mean(holding_periods) if len(holding_periods) > 0 else 0

            turnover = total_trades / n_years if n_years > 0 else 0
        else:
            total_trades = 0
            winning_trades = 0
            losing_trades = 0
            win_rate = 0
            avg_winner = 0
            avg_loser = 0
            profit_factor = 0
            expectancy = 0
            avg_holding_period = 0
            turnover = 0

        return cls(
            total_return=total_return,
            cagr=cagr,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown=max_drawdown,
            avg_drawdown=avg_drawdown,
            max_drawdown_duration_days=max_duration,
            volatility_annual=volatility_annual,
            downside_deviation=downside_deviation,
            beta=beta,
            alpha=alpha,
            correlation_to_benchmark=correlation,
            excess_return=excess_return,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_winner=avg_winner,
            avg_loser=avg_loser,
            profit_factor=profit_factor,
            expectancy=expectancy,
            turnover=turnover,
            avg_holding_period=avg_holding_period,
        )
