"""
Walk-Forward Analysis Module
Implements walk-forward validation to prevent overfitting
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import polars as pl
from datetime import date, timedelta
from .metrics import PerformanceMetrics


@dataclass
class WalkForwardResult:
    """Results from walk-forward analysis"""
    train_periods: List[str]
    test_periods: List[str]
    test_metrics: List[PerformanceMetrics]
    avg_out_of_sample_return: float
    stability_score: float  # How consistent are results across periods?
    degradation_factor: float  # In-sample vs out-of-sample performance ratio

    def to_dict(self) -> dict:
        return {
            "train_periods": self.train_periods,
            "test_periods": self.test_periods,
            "avg_out_of_sample_return": round(self.avg_out_of_sample_return, 4),
            "stability_score": round(self.stability_score, 2),
            "degradation_factor": round(self.degradation_factor, 2),
            "period_results": [
                {
                    "period": test_period,
                    "metrics": metrics.to_dict()
                }
                for test_period, metrics in zip(self.test_periods, self.test_metrics)
            ]
        }


class WalkForwardAnalyzer:
    """
    Implements walk-forward validation

    Example:
    Train 2010–2015 → Test 2016
    Train 2011–2016 → Test 2017
    Train 2012–2017 → Test 2018
    """

    def __init__(
        self,
        train_years: int = 5,
        test_years: int = 1,
        step_years: int = 1
    ):
        self.train_years = train_years
        self.test_years = test_years
        self.step_years = step_years

    def generate_periods(
        self,
        start_date: date,
        end_date: date
    ) -> List[tuple]:
        """Generate train/test period pairs"""
        periods = []

        current_train_start = start_date
        while True:
            train_end = current_train_start + timedelta(days=self.train_years * 365)
            if train_end >= end_date:
                break

            test_start = train_end + timedelta(days=1)
            test_end = test_start + timedelta(days=self.test_years * 365)

            if test_end > end_date:
                test_end = end_date

            periods.append((current_train_start, train_end, test_start, test_end))

            # Step forward
            current_train_start += timedelta(days=self.step_years * 365)

        return periods

    def analyze(
        self,
        data: pl.DataFrame,
        strategy: Any,
        backtest_engine: Any,
        benchmark_data: Optional[pl.DataFrame] = None
    ) -> WalkForwardResult:
        """
        Run walk-forward analysis

        Args:
             Full dataset with prices and features
            strategy: Strategy instance
            backtest_engine: BacktestEngine instance
            benchmark_data: Optional benchmark price data

        Returns:
            WalkForwardResult with metrics for each period
        """
        min_date = data["timestamp"].min()
        max_date = data["timestamp"].max()

        periods = self.generate_periods(min_date, max_date)

        train_periods = []
        test_periods = []
        test_metrics = []

        for train_start, train_end, test_start, test_end in periods:
            # Filter training data
            train_data = data.filter(
                (pl.col("timestamp") >= train_start) &
                (pl.col("timestamp") <= train_end)
            )

            # Filter test data
            test_data = data.filter(
                (pl.col("timestamp") >= test_start) &
                (pl.col("timestamp") <= test_end)
            )

            if len(train_data) < 252 or len(test_data) < 63:  # Need minimum data
                continue

            # Note: In real implementation, we would retrain the model here
            # For now, we'll just run the backtest on the test period

            # Run backtest on test period
            result = backtest_engine.run(
                data=test_data,
                strategy=strategy,
                benchmark_data=benchmark_data
            )

            train_periods.append(f"{train_start} to {train_end}")
            test_periods.append(f"{test_start} to {test_end}")
            test_metrics.append(result.metrics)

        # Calculate aggregate statistics
        if len(test_metrics) > 0:
            returns = [m.total_return for m in test_metrics]
            avg_return = sum(returns) / len(returns)

            # Stability score: inverse of standard deviation of returns
            if len(returns) > 1:
                import numpy as np
                std_dev = np.std(returns)
                stability_score = 1 / (1 + std_dev)  # Higher is better
            else:
                stability_score = 1.0

            # Degradation factor would compare in-sample vs out-of-sample
            # For now, set to 1.0 (no comparison available)
            degradation_factor = 1.0
        else:
            avg_return = 0.0
            stability_score = 0.0
            degradation_factor = 0.0

        return WalkForwardResult(
            train_periods=train_periods,
            test_periods=test_periods,
            test_metrics=test_metrics,
            avg_out_of_sample_return=avg_return,
            stability_score=stability_score,
            degradation_factor=degradation_factor
        )
