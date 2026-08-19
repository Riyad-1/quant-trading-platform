"""Point-in-time daily-bar backtesting with explicit execution assumptions."""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple

import polars as pl

from .metrics import PerformanceMetrics
from .strategy import ExecutionModel, IntrabarPolicy, Strategy, StrategyConfig


@dataclass
class Trade:
    """A completed trade with signal, execution, and cost attribution."""

    ticker: str
    entry_date: date
    entry_price: float
    exit_date: Optional[date]
    exit_price: Optional[float]
    quantity: int
    side: str
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_period: int = 0
    exit_reason: str = "open"
    feature_timestamp: Optional[Any] = None
    signal_timestamp: Optional[Any] = None
    decision_timestamp: Optional[Any] = None
    execution_timestamp: Optional[Any] = None
    exit_decision_timestamp: Optional[Any] = None
    exit_execution_timestamp: Optional[Any] = None
    entry_reference_price: float = 0.0
    exit_reference_price: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    entry_commission_cost: float = 0.0
    exit_commission_cost: float = 0.0
    entry_spread_cost: float = 0.0
    exit_spread_cost: float = 0.0
    entry_slippage_cost: float = 0.0
    exit_slippage_cost: float = 0.0
    intrabar_ambiguous: bool = False
    intrabar_policy: Optional[str] = None

    @property
    def commission_cost(self) -> float:
        return self.entry_commission_cost + self.exit_commission_cost

    @property
    def spread_cost(self) -> float:
        return self.entry_spread_cost + self.exit_spread_cost

    @property
    def slippage_cost(self) -> float:
        return self.entry_slippage_cost + self.exit_slippage_cost

    @property
    def total_cost(self) -> float:
        return self.commission_cost + self.spread_cost + self.slippage_cost


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    equity_curve: pl.DataFrame
    benchmark_curve: Optional[pl.DataFrame]
    trades: List[Trade]
    metrics: PerformanceMetrics
    total_signals: int = 0
    avg_score: float = 0.0

    @property
    def gross_final_equity(self) -> float:
        return self.initial_capital + sum(trade.gross_pnl for trade in self.trades)

    @property
    def gross_total_return(self) -> float:
        return (self.gross_final_equity / self.initial_capital) - 1

    @property
    def net_total_return(self) -> float:
        return (self.final_equity / self.initial_capital) - 1

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "start_date": str(self.start_date),
            "end_date": str(self.end_date),
            "initial_capital": round(self.initial_capital, 2),
            "final_equity": round(self.final_equity, 2),
            "gross_final_equity": round(self.gross_final_equity, 2),
            "gross_total_return": round(self.gross_total_return, 4),
            "net_total_return": round(self.net_total_return, 4),
            "total_return": round(self.net_total_return, 4),
            "performance_basis": "net_of_commission_spread_and_slippage",
            "equity_curve": self.equity_curve.to_dicts()[-100:],
            "trades": [
                {
                    "ticker": trade.ticker,
                    "feature_timestamp": str(trade.feature_timestamp),
                    "signal_timestamp": str(trade.signal_timestamp),
                    "decision_timestamp": str(trade.decision_timestamp),
                    "execution_timestamp": str(trade.execution_timestamp),
                    "exit_decision_timestamp": str(trade.exit_decision_timestamp),
                    "exit_execution_timestamp": str(trade.exit_execution_timestamp),
                    "entry_date": str(trade.entry_date),
                    "exit_date": str(trade.exit_date) if trade.exit_date else None,
                    "entry_reference_price": round(trade.entry_reference_price, 6),
                    "entry_price": round(trade.entry_price, 6),
                    "exit_reference_price": round(trade.exit_reference_price, 6),
                    "exit_price": round(trade.exit_price, 6) if trade.exit_price is not None else None,
                    "quantity": trade.quantity,
                    "side": trade.side,
                    "gross_pnl": round(trade.gross_pnl, 2),
                    "net_pnl": round(trade.net_pnl, 2),
                    "pnl": round(trade.pnl, 2),
                    "pnl_pct": round(trade.pnl_pct, 4),
                    "entry_commission_cost": round(trade.entry_commission_cost, 4),
                    "exit_commission_cost": round(trade.exit_commission_cost, 4),
                    "entry_spread_cost": round(trade.entry_spread_cost, 4),
                    "exit_spread_cost": round(trade.exit_spread_cost, 4),
                    "entry_slippage_cost": round(trade.entry_slippage_cost, 4),
                    "exit_slippage_cost": round(trade.exit_slippage_cost, 4),
                    "total_cost": round(trade.total_cost, 4),
                    "holding_period": trade.holding_period,
                    "exit_reason": trade.exit_reason,
                    "intrabar_ambiguous": trade.intrabar_ambiguous,
                    "intrabar_policy": trade.intrabar_policy,
                }
                for trade in self.trades[-50:]
            ],
            "metrics": self.metrics.to_dict(),
            "total_signals": self.total_signals,
            "avg_score": round(self.avg_score, 2),
        }


class BacktestEngine:
    """Event-driven long-only simulator over observed daily trading sessions."""

    def __init__(self, initial_capital: float = 100_000):
        self.initial_capital = float(initial_capital)

    def run(
        self,
        data: pl.DataFrame,
        strategy: Strategy,
        benchmark_data: Optional[pl.DataFrame] = None,
        config: Optional[StrategyConfig] = None,
    ) -> BacktestResult:
        """Run a point-in-time backtest using the configured execution model."""
        config = config or strategy.config
        self._validate_input(data)
        data = data.sort(["ticker", "timestamp"])

        signals_df = strategy.generate_signals(data)
        buy_signals = signals_df.filter(pl.col("signal") == 1)

        all_dates = sorted(data["timestamp"].unique().to_list())
        rows_by_key = {
            (row["timestamp"], row["ticker"]): row
            for row in data.iter_rows(named=True)
        }
        ticker_sessions: Dict[str, List[Any]] = {}
        for ticker in data["ticker"].unique().to_list():
            ticker_sessions[ticker] = sorted(
                data.filter(pl.col("ticker") == ticker)["timestamp"].unique().to_list()
            )
        ticker_session_index = {
            ticker: {session: index for index, session in enumerate(sessions)}
            for ticker, sessions in ticker_sessions.items()
        }

        scheduled_entries = self._schedule_entries(buy_signals, ticker_sessions, config)
        positions: Dict[str, Dict[str, Any]] = {}
        trades: List[Trade] = []
        equity_history: List[Dict[str, Any]] = []
        latest_close: Dict[str, float] = {}
        cash = self.initial_capital

        for current_date in all_dates:
            for ticker in ticker_sessions:
                row = rows_by_key.get((current_date, ticker))
                if row is not None:
                    latest_close[ticker] = float(row["close"])

            cash += self._process_exits(
                positions=positions,
                current_date=current_date,
                rows_by_key=rows_by_key,
                ticker_session_index=ticker_session_index,
                config=config,
                trades=trades,
            )

            new_tickers: List[str] = []
            for signal_row in scheduled_entries.get(current_date, []):
                ticker = signal_row["ticker"]
                if ticker in positions:
                    continue
                market_row = rows_by_key.get((current_date, ticker))
                if market_row is None:
                    continue

                reference_price = self._entry_reference_price(signal_row, market_row, config)
                if reference_price is None:
                    continue
                if reference_price < config.min_price or market_row.get("volume", 0) < config.min_volume:
                    continue

                holdings_value = sum(
                    position["quantity"] * latest_close.get(symbol, position["entry_reference_price"])
                    for symbol, position in positions.items()
                )
                current_equity = cash + holdings_value
                position_value = min(
                    current_equity * config.max_position_pct,
                    current_equity / config.max_portfolio_positions,
                )
                quantity = int(position_value / self._entry_unit_cash_cost(reference_price, config))
                quantity = min(quantity, int(cash / self._entry_unit_cash_cost(reference_price, config)))
                if quantity < 1:
                    continue

                costs = self._costs(reference_price, quantity, config)
                entry_price = reference_price + costs["spread"] / quantity + costs["slippage"] / quantity
                cash -= reference_price * quantity + costs["spread"] + costs["slippage"] + costs["commission"]
                positions[ticker] = {
                    "entry_date": current_date,
                    "entry_session_index": ticker_session_index[ticker][current_date],
                    "entry_reference_price": reference_price,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "feature_timestamp": signal_row.get("feature_timestamp", signal_row.get("timestamp")),
                    "signal_timestamp": signal_row.get("signal_timestamp", signal_row.get("timestamp")),
                    "decision_timestamp": signal_row.get("decision_timestamp", signal_row.get("timestamp")),
                    "execution_timestamp": current_date,
                    "entry_commission_cost": costs["commission"],
                    "entry_spread_cost": costs["spread"],
                    "entry_slippage_cost": costs["slippage"],
                }
                new_tickers.append(ticker)

            execution_model = ExecutionModel(config.execution_model)
            if execution_model in {ExecutionModel.NEXT_OPEN, ExecutionModel.LIMIT}:
                # An open/limit entry can hit a stop or target later in its entry bar.
                cash += self._process_exits(
                    positions=positions,
                    current_date=current_date,
                    rows_by_key=rows_by_key,
                    ticker_session_index=ticker_session_index,
                    config=config,
                    trades=trades,
                    only_tickers=new_tickers,
                    allow_gap=False,
                )

            holdings_value = sum(
                position["quantity"] * latest_close.get(ticker, position["entry_reference_price"])
                for ticker, position in positions.items()
            )
            equity_history.append(
                {
                    "date": current_date,
                    "equity": cash + holdings_value,
                    "cash": cash,
                    "holdings_value": holdings_value,
                }
            )

        final_date = all_dates[-1]
        for ticker in list(positions):
            ticker_final_date = ticker_sessions[ticker][-1]
            market_row = rows_by_key.get((ticker_final_date, ticker))
            if market_row is None:
                continue
            position = positions.pop(ticker)
            cash += self._close_position(
                ticker=ticker,
                position=position,
                exit_reference_price=float(market_row["close"]),
                exit_date=ticker_final_date,
                exit_reason="end_of_backtest",
                holding_period=(
                    ticker_session_index[ticker][ticker_final_date]
                    - position["entry_session_index"]
                ),
                config=config,
                trades=trades,
            )

        if positions:
            holdings_value = sum(
                position["quantity"] * latest_close.get(ticker, position["entry_reference_price"])
                for ticker, position in positions.items()
            )
            final_equity = cash + holdings_value
        else:
            holdings_value = 0.0
            final_equity = cash

        equity_history[-1] = {
            "date": final_date,
            "equity": final_equity,
            "cash": cash,
            "holdings_value": holdings_value,
        }
        equity_df = pl.DataFrame(equity_history)
        benchmark_curve = self._build_benchmark_curve(benchmark_data, equity_df, config)
        metrics = self._calculate_metrics(equity_df, benchmark_curve, trades)
        avg_score = float(buy_signals["score"].mean() or 0.0) if len(buy_signals) else 0.0

        return BacktestResult(
            strategy_name=strategy.name,
            start_date=all_dates[0],
            end_date=all_dates[-1],
            initial_capital=self.initial_capital,
            final_equity=final_equity,
            equity_curve=equity_df,
            benchmark_curve=benchmark_curve,
            trades=trades,
            metrics=metrics,
            total_signals=len(buy_signals),
            avg_score=avg_score,
        )

    @staticmethod
    def _validate_input(data: pl.DataFrame) -> None:
        required = {"timestamp", "ticker", "open", "high", "low", "close", "volume"}
        missing = sorted(required - set(data.columns))
        if missing:
            raise ValueError(f"Missing required backtest columns: {missing}")
        if data.is_empty():
            raise ValueError("Backtest data must not be empty")

    def _schedule_entries(
        self,
        buy_signals: pl.DataFrame,
        ticker_sessions: Dict[str, List[Any]],
        config: StrategyConfig,
    ) -> Dict[Any, List[Dict[str, Any]]]:
        execution_model = ExecutionModel(config.execution_model)
        scheduled: Dict[Any, List[Dict[str, Any]]] = {}

        for signal in buy_signals.sort(["timestamp", "score"], descending=[False, True]).iter_rows(named=True):
            ticker = signal["ticker"]
            sessions = ticker_sessions.get(ticker, [])
            try:
                signal_index = sessions.index(signal["timestamp"])
            except ValueError:
                continue

            if execution_model == ExecutionModel.MARKET_ON_CLOSE:
                execution_date = sessions[signal_index]
                execution_time = self._execution_datetime(execution_date, execution_model)
                available_at = self._as_datetime(signal.get("available_at"))
                if available_at is None or available_at >= execution_time:
                    continue
            else:
                if signal_index + 1 >= len(sessions):
                    continue
                execution_date = sessions[signal_index + 1]
                available_at = self._as_datetime(signal.get("available_at"))
                if available_at is not None:
                    execution_time = self._execution_datetime(execution_date, execution_model)
                    if available_at > execution_time:
                        continue

            scheduled.setdefault(execution_date, []).append(signal)

        return scheduled

    @staticmethod
    def _as_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        return None

    @classmethod
    def _execution_datetime(cls, session: Any, execution_model: ExecutionModel) -> datetime:
        value = cls._as_datetime(session)
        if value is None:
            raise ValueError(f"Unsupported session timestamp: {session!r}")
        if execution_model in {ExecutionModel.NEXT_OPEN, ExecutionModel.LIMIT}:
            # 13:30 UTC is the earliest US regular-session open across DST states.
            return datetime.combine(value.date(), time(hour=13, minute=30))
        # 20:00 UTC is the earliest US regular-session close across DST states.
        return datetime.combine(value.date(), time(hour=20))

    @staticmethod
    def _entry_reference_price(
        signal: Dict[str, Any],
        market_row: Dict[str, Any],
        config: StrategyConfig,
    ) -> Optional[float]:
        execution_model = ExecutionModel(config.execution_model)
        if execution_model == ExecutionModel.NEXT_OPEN:
            return float(market_row["open"])
        if execution_model in {ExecutionModel.NEXT_CLOSE, ExecutionModel.MARKET_ON_CLOSE}:
            return float(market_row["close"])
        if execution_model == ExecutionModel.LIMIT:
            limit_price = signal.get(config.limit_price_column)
            if limit_price is None:
                return None
            limit_price = float(limit_price)
            if float(market_row["low"]) > limit_price:
                return None
            return min(float(market_row["open"]), limit_price)
        raise ValueError(f"Unsupported execution model: {execution_model}")

    @staticmethod
    def _costs(reference_price: float, quantity: int, config: StrategyConfig) -> Dict[str, float]:
        notional = reference_price * quantity
        return {
            "commission": notional * config.transaction_cost_pct,
            "spread": notional * (config.spread_pct / 2),
            "slippage": notional * config.slippage_pct,
        }

    def _entry_unit_cash_cost(self, reference_price: float, config: StrategyConfig) -> float:
        costs = self._costs(reference_price, 1, config)
        return reference_price + costs["commission"] + costs["spread"] + costs["slippage"]

    def _process_exits(
        self,
        positions: Dict[str, Dict[str, Any]],
        current_date: Any,
        rows_by_key: Dict[Tuple[Any, str], Dict[str, Any]],
        ticker_session_index: Dict[str, Dict[Any, int]],
        config: StrategyConfig,
        trades: List[Trade],
        only_tickers: Optional[List[str]] = None,
        allow_gap: bool = True,
    ) -> float:
        proceeds = 0.0
        tickers = list(only_tickers) if only_tickers is not None else list(positions)
        for ticker in tickers:
            position = positions.get(ticker)
            market_row = rows_by_key.get((current_date, ticker))
            if position is None or market_row is None:
                continue

            current_index = ticker_session_index[ticker][current_date]
            holding_period = current_index - position["entry_session_index"]
            exit_details = self._determine_exit(position, market_row, holding_period, config, allow_gap)
            if exit_details is None:
                continue

            exit_reference_price, exit_reason, ambiguous = exit_details
            proceeds += self._close_position(
                ticker=ticker,
                position=position,
                exit_reference_price=exit_reference_price,
                exit_date=current_date,
                exit_reason=exit_reason,
                holding_period=holding_period,
                config=config,
                trades=trades,
                intrabar_ambiguous=ambiguous,
            )
            del positions[ticker]
        return proceeds

    @staticmethod
    def _determine_exit(
        position: Dict[str, Any],
        market_row: Dict[str, Any],
        holding_period: int,
        config: StrategyConfig,
        allow_gap: bool,
    ) -> Optional[Tuple[float, str, bool]]:
        stop_price = position["entry_reference_price"] * (1 - config.stop_loss_pct)
        target_price = position["entry_reference_price"] * (1 + config.take_profit_pct)
        open_price = float(market_row["open"])
        low_price = float(market_row["low"])
        high_price = float(market_row["high"])

        if allow_gap and open_price <= stop_price:
            return open_price, "stop_gap", False
        if allow_gap and open_price >= target_price:
            return open_price, "target_gap", False

        stop_touched = low_price <= stop_price
        target_touched = high_price >= target_price
        if stop_touched and target_touched:
            policy = IntrabarPolicy(config.intrabar_policy)
            if policy == IntrabarPolicy.TARGET_FIRST:
                return target_price, "target", True
            return stop_price, "stop_loss", True
        if stop_touched:
            return stop_price, "stop_loss", False
        if target_touched:
            return target_price, "target", False
        if holding_period >= config.holding_period:
            return float(market_row["close"]), "time_exit", False
        return None

    def _close_position(
        self,
        ticker: str,
        position: Dict[str, Any],
        exit_reference_price: float,
        exit_date: Any,
        exit_reason: str,
        holding_period: int,
        config: StrategyConfig,
        trades: List[Trade],
        intrabar_ambiguous: bool = False,
    ) -> float:
        quantity = position["quantity"]
        exit_costs = self._costs(exit_reference_price, quantity, config)
        exit_price = exit_reference_price - exit_costs["spread"] / quantity - exit_costs["slippage"] / quantity
        gross_pnl = (exit_reference_price - position["entry_reference_price"]) * quantity
        total_cost = (
            position["entry_commission_cost"]
            + position["entry_spread_cost"]
            + position["entry_slippage_cost"]
            + exit_costs["commission"]
            + exit_costs["spread"]
            + exit_costs["slippage"]
        )
        net_pnl = gross_pnl - total_cost
        invested_notional = position["entry_reference_price"] * quantity

        trades.append(
            Trade(
                ticker=ticker,
                entry_date=position["entry_date"],
                entry_price=position["entry_price"],
                exit_date=exit_date,
                exit_price=exit_price,
                quantity=quantity,
                side="long",
                pnl=net_pnl,
                pnl_pct=net_pnl / invested_notional if invested_notional else 0.0,
                holding_period=holding_period,
                exit_reason=exit_reason,
                feature_timestamp=position["feature_timestamp"],
                signal_timestamp=position["signal_timestamp"],
                decision_timestamp=position["decision_timestamp"],
                execution_timestamp=position["execution_timestamp"],
                exit_decision_timestamp=exit_date,
                exit_execution_timestamp=exit_date,
                entry_reference_price=position["entry_reference_price"],
                exit_reference_price=exit_reference_price,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                entry_commission_cost=position["entry_commission_cost"],
                exit_commission_cost=exit_costs["commission"],
                entry_spread_cost=position["entry_spread_cost"],
                exit_spread_cost=exit_costs["spread"],
                entry_slippage_cost=position["entry_slippage_cost"],
                exit_slippage_cost=exit_costs["slippage"],
                intrabar_ambiguous=intrabar_ambiguous,
                intrabar_policy=IntrabarPolicy(config.intrabar_policy).value if intrabar_ambiguous else None,
            )
        )
        return (
            exit_reference_price * quantity
            - exit_costs["commission"]
            - exit_costs["spread"]
            - exit_costs["slippage"]
        )

    def _build_benchmark_curve(
        self,
        benchmark_data: Optional[pl.DataFrame],
        equity_curve: pl.DataFrame,
        config: StrategyConfig,
    ) -> Optional[pl.DataFrame]:
        if benchmark_data is None or benchmark_data.is_empty():
            return None
        required = {"timestamp", "open", "close"}
        if not required.issubset(benchmark_data.columns):
            raise ValueError(f"Benchmark data missing columns: {sorted(required - set(benchmark_data.columns))}")

        strategy_dates = equity_curve["date"].to_list()
        start_date, end_date = strategy_dates[0], strategy_dates[-1]
        benchmark = (
            benchmark_data
            .filter(
                (pl.col("timestamp") >= start_date)
                & (pl.col("timestamp") <= end_date)
                & pl.col("timestamp").is_in(strategy_dates)
            )
            .sort("timestamp")
            .unique(subset=["timestamp"], keep="first", maintain_order=True)
        )
        if benchmark.is_empty():
            return None

        benchmark_dates = benchmark["timestamp"].to_list()
        if benchmark_dates != strategy_dates:
            missing_dates = [session for session in strategy_dates if session not in benchmark_dates]
            raise ValueError(
                "Benchmark does not cover every strategy session; "
                f"missing sessions: {missing_dates[:5]}"
            )

        benchmark_rows = benchmark.to_dicts()
        entry_reference = float(benchmark_rows[0]["open"])
        quantity = int(self.initial_capital / self._entry_unit_cash_cost(entry_reference, config))
        entry_costs = self._costs(entry_reference, quantity, config)
        cash = (
            self.initial_capital
            - entry_reference * quantity
            - entry_costs["commission"]
            - entry_costs["spread"]
            - entry_costs["slippage"]
        )
        curve = [
            {"date": row["timestamp"], "equity": cash + quantity * float(row["close"])}
            for row in benchmark_rows
        ]

        final_reference = float(benchmark_rows[-1]["close"])
        exit_costs = self._costs(final_reference, quantity, config)
        curve[-1]["equity"] = (
            cash
            + final_reference * quantity
            - exit_costs["commission"]
            - exit_costs["spread"]
            - exit_costs["slippage"]
        )
        return pl.DataFrame(curve)

    @staticmethod
    def _calculate_metrics(
        equity_df: pl.DataFrame,
        benchmark_curve: Optional[pl.DataFrame],
        trades: List[Trade],
    ) -> PerformanceMetrics:
        trades_df = None
        if trades:
            trades_df = pl.DataFrame(
                {
                    "ticker": [trade.ticker for trade in trades],
                    "entry_date": [trade.entry_date for trade in trades],
                    "exit_date": [trade.exit_date for trade in trades],
                    "pnl": [trade.net_pnl for trade in trades],
                    "pnl_pct": [trade.pnl_pct for trade in trades],
                    "holding_period": [trade.holding_period for trade in trades],
                }
            )
        return PerformanceMetrics.calculate(
            equity_curve=equity_df.select(["date", "equity"]),
            benchmark_curve=benchmark_curve,
            trades=trades_df,
        )
