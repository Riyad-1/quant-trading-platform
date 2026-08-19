"""Stage B research-integrity invariants for features and execution."""

from datetime import date, datetime, time, timedelta

import numpy as np
import polars as pl
import pytest

from services.backtesting.engine import BacktestEngine
from services.backtesting.strategy import (
    ExecutionModel,
    IntrabarPolicy,
    MomentumBreakoutStrategy,
    Strategy,
    StrategyConfig,
)
from services.features.engine import FeatureEngine
from services.paper_trading.engine import OrderSide, OrderStatus, PaperTradingEngine


class OneShotStrategy(Strategy):
    """Emit one controlled signal without deriving it from future bars."""

    def __init__(
        self,
        signal_session: date,
        config: StrategyConfig,
        available_hour: int = 21,
        limit_price: float | None = None,
    ):
        super().__init__(config)
        self.signal_session = signal_session
        self.available_hour = available_hour
        self.limit_price = limit_price

    def get_required_features(self):
        return []

    def generate_signals(self, data: pl.DataFrame) -> pl.DataFrame:
        frame = data.filter(pl.col("timestamp") == self.signal_session).with_columns(
            pl.lit(1).alias("signal"),
            pl.lit(100.0).alias("score"),
            pl.col("timestamp").alias("feature_timestamp"),
            pl.col("timestamp").alias("signal_timestamp"),
            pl.col("timestamp").alias("decision_timestamp"),
            pl.lit(datetime.combine(self.signal_session, time(self.available_hour))).alias("available_at"),
        )
        if self.limit_price is not None:
            frame = frame.with_columns(pl.lit(self.limit_price).alias("limit_price"))
        columns = [
            "timestamp",
            "ticker",
            "signal",
            "score",
            "feature_timestamp",
            "signal_timestamp",
            "decision_timestamp",
            "available_at",
        ]
        if self.limit_price is not None:
            columns.append("limit_price")
        return frame.select(columns)


def strategy_config(**overrides) -> StrategyConfig:
    values = {
        "name": "Integrity test",
        "description": "Controlled execution fixture",
        "holding_period": 1,
        "stop_loss_pct": 0.50,
        "take_profit_pct": 1.00,
        "min_price": 0.0,
        "min_volume": 0,
        "transaction_cost_pct": 0.0,
        "spread_pct": 0.0,
        "slippage_pct": 0.0,
        "max_position_pct": 1.0,
        "max_portfolio_positions": 1,
    }
    values.update(overrides)
    return StrategyConfig(**values)


def bars(
    sessions,
    opens,
    highs=None,
    lows=None,
    closes=None,
    ticker="TEST",
) -> pl.DataFrame:
    highs = highs or [value + 1 for value in opens]
    lows = lows or [value - 1 for value in opens]
    closes = closes or list(opens)
    return pl.DataFrame(
        {
            "timestamp": sessions,
            "ticker": [ticker] * len(sessions),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1_000_000] * len(sessions),
        }
    )


def feature_prices(ticker: str, start: date, count: int, base: float, step: float) -> pl.DataFrame:
    rows = []
    for index in range(count):
        session = start + timedelta(days=index)
        close = base + index * step
        rows.append(
            {
                "time": session,
                "ticker": ticker,
                "open": close - 0.25,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000 + index * 10,
            }
        )
    return pl.DataFrame(rows)


def assert_numeric_columns_equal(left: pl.DataFrame, right: pl.DataFrame, columns) -> None:
    for column in columns:
        left_values = np.asarray(left[column].to_numpy(), dtype=float)
        right_values = np.asarray(right[column].to_numpy(), dtype=float)
        np.testing.assert_allclose(left_values, right_values, equal_nan=True)


def test_features_are_isolated_per_ticker():
    engine = FeatureEngine()
    asset_a = feature_prices("AAA", date(2024, 1, 1), 280, 10.0, 0.2)
    asset_b = feature_prices("BBB", date(2024, 1, 1), 280, 10_000.0, -7.0)

    isolated = engine.calculate_all_features(asset_a)
    combined = engine.calculate_all_features(pl.concat([asset_b, asset_a])).filter(pl.col("ticker") == "AAA")

    assert_numeric_columns_equal(isolated, combined, engine.get_feature_columns())
    assert combined["roc_5"].null_count() == isolated["roc_5"].null_count() == 5
    assert combined["sma_200"].null_count() == isolated["sma_200"].null_count() == 199


def test_mutating_future_rows_cannot_change_features_at_or_before_t():
    engine = FeatureEngine()
    original = feature_prices("AAA", date(2024, 1, 1), 280, 100.0, 0.5)
    cutoff = original["time"][240]
    mutated = original.with_columns(
        pl.when(pl.col("time") > cutoff).then(pl.col("close") * 50).otherwise(pl.col("close")).alias("close"),
        pl.when(pl.col("time") > cutoff).then(pl.col("high") * 50).otherwise(pl.col("high")).alias("high"),
        pl.when(pl.col("time") > cutoff).then(pl.col("volume") * 100).otherwise(pl.col("volume")).alias("volume"),
    )

    before = engine.calculate_all_features(original).filter(pl.col("time") <= cutoff)
    after = engine.calculate_all_features(mutated).filter(pl.col("time") <= cutoff)
    assert_numeric_columns_equal(before, after, engine.get_feature_columns())

    strategy = MomentumBreakoutStrategy()
    before_signals = strategy.generate_signals(
        before.rename({"time": "timestamp"}).with_columns(
            pl.lit(1.5).alias("relative_strength_spy")
        )
    )
    after_signals = strategy.generate_signals(
        after.rename({"time": "timestamp"}).with_columns(
            pl.lit(1.5).alias("relative_strength_spy")
        )
    )
    assert before_signals["signal"].to_list() == after_signals["signal"].to_list()
    np.testing.assert_allclose(
        np.asarray(before_signals["score"].to_numpy(), dtype=float),
        np.asarray(after_signals["score"].to_numpy(), dtype=float),
        equal_nan=True,
    )


def test_breakout_uses_prior_window_and_exposes_current_window():
    rows = []
    for index in range(21):
        is_breakout = index == 20
        rows.append(
            {
                "time": date(2024, 1, 1) + timedelta(days=index),
                "ticker": "AAA",
                "open": 99.0,
                "high": 105.0 if is_breakout else 100.0,
                "low": 98.0,
                "close": 105.0 if is_breakout else 99.0,
                "volume": 1_000_000,
            }
        )

    last = FeatureEngine().calculate_breakout_features(pl.DataFrame(rows)).row(-1, named=True)
    assert last["prior_20d_high"] == 100.0
    assert last["current_20d_high"] == 105.0
    assert last["high_20d"] == last["current_20d_high"]
    assert last["distance_from_20d_high"] == pytest.approx(0.05)
    assert last["is_20d_breakout"] is True


def test_feature_output_has_explicit_point_in_time_metadata():
    result = FeatureEngine().calculate_all_features(
        feature_prices("AAA", date(2024, 1, 1), 25, 100.0, 0.1)
    )
    row = result.row(0, named=True)
    assert row["event_time"] == datetime(2024, 1, 1)
    assert row["available_at"] == datetime(2024, 1, 1, 21)
    assert row["computed_at"] >= row["available_at"]
    assert row["availability_rule"] == "US_EQUITY_SESSION_CLOSE_CONSERVATIVE_21_UTC"


def test_close_signal_executes_at_next_session_open_with_ordered_timestamps():
    sessions = [date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9)]
    data = bars(sessions, [100.0, 120.0, 121.0], closes=[100.0, 120.0, 122.0])
    config = strategy_config()

    result = BacktestEngine().run(data, OneShotStrategy(sessions[0], config))
    trade = result.trades[0]

    assert trade.signal_timestamp == sessions[0]
    assert trade.decision_timestamp == sessions[0]
    assert trade.execution_timestamp == sessions[1]
    assert trade.entry_reference_price == 120.0
    assert trade.signal_timestamp < trade.execution_timestamp


def test_market_on_close_requires_explicit_pre_close_availability():
    sessions = [date(2024, 2, 1), date(2024, 2, 2)]
    data = bars(sessions, [100.0, 101.0], closes=[102.0, 103.0])
    config = strategy_config(execution_model=ExecutionModel.MARKET_ON_CLOSE)

    unsafe = BacktestEngine().run(data, OneShotStrategy(sessions[0], config, available_hour=21))
    safe = BacktestEngine().run(data, OneShotStrategy(sessions[0], config, available_hour=19))

    assert unsafe.trades == []
    assert safe.trades[0].execution_timestamp == sessions[0]
    assert safe.trades[0].entry_reference_price == 102.0


def test_value_unavailable_at_next_open_cannot_enter_the_backtest():
    sessions = [date(2024, 2, 1), date(2024, 2, 2), date(2024, 2, 5)]
    data = bars(sessions, [100.0, 101.0, 102.0])
    config = strategy_config()
    strategy = OneShotStrategy(sessions[0], config)
    original_generate = strategy.generate_signals

    def future_available(frame):
        return original_generate(frame).with_columns(
            pl.lit(datetime(2024, 2, 2, 21)).alias("available_at")
        )

    strategy.generate_signals = future_available
    result = BacktestEngine().run(data, strategy)
    assert result.trades == []


@pytest.mark.parametrize(
    ("execution_model", "limit_price", "expected_price"),
    [
        (ExecutionModel.NEXT_CLOSE, None, 103.0),
        (ExecutionModel.LIMIT, 99.0, 99.0),
    ],
)
def test_explicit_next_close_and_limit_execution(execution_model, limit_price, expected_price):
    sessions = [date(2024, 3, 1), date(2024, 3, 4), date(2024, 3, 5)]
    data = bars(
        sessions,
        [100.0, 101.0, 102.0],
        highs=[101.0, 104.0, 103.0],
        lows=[99.0, 98.0, 101.0],
        closes=[100.0, 103.0, 102.0],
    )
    config = strategy_config(execution_model=execution_model)
    result = BacktestEngine().run(
        data,
        OneShotStrategy(sessions[0], config, limit_price=limit_price),
    )
    assert result.trades[0].entry_reference_price == expected_price


def test_entry_and_exit_costs_reconcile_gross_to_net_and_final_equity():
    sessions = [date(2024, 4, 1), date(2024, 4, 2), date(2024, 4, 3)]
    data = bars(sessions, [100.0, 100.0, 110.0], closes=[100.0, 100.0, 110.0])
    config = strategy_config(
        transaction_cost_pct=0.001,
        spread_pct=0.002,
        slippage_pct=0.003,
    )
    result = BacktestEngine().run(data, OneShotStrategy(sessions[0], config))
    trade = result.trades[0]

    assert trade.entry_commission_cost > 0
    assert trade.exit_commission_cost > 0
    assert trade.entry_spread_cost > 0
    assert trade.exit_spread_cost > 0
    assert trade.entry_slippage_cost > 0
    assert trade.exit_slippage_cost > 0
    assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.total_cost)
    assert trade.pnl == pytest.approx(trade.net_pnl)
    assert result.final_equity == pytest.approx(result.initial_capital + trade.net_pnl)
    assert result.gross_final_equity == pytest.approx(result.initial_capital + trade.gross_pnl)
    assert result.gross_total_return > result.net_total_return


def test_gap_through_stop_fills_at_open_not_stop_level():
    sessions = [date(2024, 5, 1), date(2024, 5, 2), date(2024, 5, 3)]
    data = bars(
        sessions,
        [100.0, 100.0, 90.0],
        highs=[101.0, 101.0, 92.0],
        lows=[99.0, 99.0, 88.0],
        closes=[100.0, 100.0, 91.0],
    )
    config = strategy_config(stop_loss_pct=0.05, holding_period=10)
    trade = BacktestEngine().run(data, OneShotStrategy(sessions[0], config)).trades[0]

    assert trade.exit_reason == "stop_gap"
    assert trade.exit_reference_price == 90.0
    assert trade.exit_reference_price < 95.0


def test_ambiguous_intrabar_stop_and_target_uses_conservative_policy():
    sessions = [date(2024, 6, 3), date(2024, 6, 4), date(2024, 6, 5)]
    data = bars(
        sessions,
        [100.0, 100.0, 100.0],
        highs=[101.0, 101.0, 110.0],
        lows=[99.0, 99.0, 90.0],
        closes=[100.0, 100.0, 100.0],
    )
    config = strategy_config(
        stop_loss_pct=0.05,
        take_profit_pct=0.05,
        holding_period=10,
        intrabar_policy=IntrabarPolicy.CONSERVATIVE,
    )
    trade = BacktestEngine().run(data, OneShotStrategy(sessions[0], config)).trades[0]

    assert trade.intrabar_ambiguous is True
    assert trade.intrabar_policy == "conservative"
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_reference_price == 95.0


def test_holding_period_counts_observed_sessions_not_calendar_days():
    sessions = [date(2024, 7, 4), date(2024, 7, 5), date(2024, 7, 8), date(2024, 7, 9)]
    data = bars(sessions, [100.0, 100.0, 100.0, 100.0])
    config = strategy_config(holding_period=2)
    trade = BacktestEngine().run(data, OneShotStrategy(sessions[0], config)).trades[0]

    assert trade.entry_date == sessions[1]
    assert trade.exit_date == sessions[3]
    assert trade.holding_period == 2
    assert (trade.exit_date - trade.entry_date).days == 4


def test_benchmark_uses_exact_strategy_period_sessions_and_capital():
    strategy_sessions = [date(2024, 8, 5), date(2024, 8, 6), date(2024, 8, 7)]
    strategy_data = bars(strategy_sessions, [100.0, 100.0, 100.0])
    benchmark_sessions = [date(2024, 8, 1), date(2024, 8, 2), *strategy_sessions, date(2024, 8, 8)]
    benchmark_data = bars(benchmark_sessions, [100.0] * len(benchmark_sessions), ticker="SPY")
    config = strategy_config()

    result = BacktestEngine().run(
        strategy_data,
        OneShotStrategy(date(2023, 1, 1), config),
        benchmark_data=benchmark_data,
    )

    assert result.benchmark_curve is not None
    assert result.benchmark_curve["date"].to_list() == strategy_sessions
    assert result.benchmark_curve["equity"][0] == result.initial_capital
    assert result.benchmark_curve["date"].min() == result.start_date
    assert result.benchmark_curve["date"].max() == result.end_date


def test_paper_commission_is_per_share_with_minimum_and_cap():
    engine = PaperTradingEngine(
        commission_per_share=0.005,
        min_commission=1.0,
        max_commission=50.0,
    )
    assert engine.calculate_commission(100, 500.0) == 1.0
    assert engine.calculate_commission(1_000, 500.0) == 5.0
    assert engine.calculate_commission(20_000, 500.0) == 50.0


def test_paper_position_risk_uses_net_liquidation_not_remaining_cash():
    engine = PaperTradingEngine(
        initial_capital=100_000.0,
        slippage_bps=0.0,
        max_position_pct=0.20,
        max_sector_pct=1.0,
        max_portfolio_positions=1,
    )
    engine.set_sector_mapping("AAA", "Technology")
    engine.set_current_price("AAA", 100.0)
    first = engine.submit_order("AAA", OrderSide.BUY, 100)
    engine.set_current_price("AAA", 200.0)
    addition = engine.submit_order("AAA", OrderSide.BUY, 9)

    assert first.status == OrderStatus.FILLED
    assert addition.status == OrderStatus.FILLED
    assert engine.positions["AAA"].quantity == 109
    assert engine.get_net_liquidation_value() > engine.cash


def test_partial_sale_reconciles_sector_exposure_and_portfolio_value():
    engine = PaperTradingEngine(
        initial_capital=100_000.0,
        slippage_bps=0.0,
        max_position_pct=1.0,
        max_sector_pct=1.0,
    )
    engine.set_sector_mapping("AAA", "Technology")
    engine.set_current_price("AAA", 100.0)
    engine.submit_order("AAA", OrderSide.BUY, 100)
    engine.set_current_price("AAA", 120.0)
    engine.submit_order("AAA", OrderSide.SELL, 40)
    summary = engine.get_portfolio_summary()

    assert engine.positions["AAA"].quantity == 60
    assert engine.sector_exposure["Technology"] == pytest.approx(7_200.0)
    assert summary["sector_exposure"]["Technology"] == pytest.approx(7_200.0)
    assert summary["positions_value"] == pytest.approx(7_200.0)
    assert summary["total_value"] == pytest.approx(summary["cash"] + summary["positions_value"])
    assert summary["total_value"] == pytest.approx(engine.get_net_liquidation_value())
