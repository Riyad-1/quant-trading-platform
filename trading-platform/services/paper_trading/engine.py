"""
Paper Trading Engine - Simulated Portfolio Management

Handles:
- Simulated order execution
- Position sizing based on risk rules
- P&L tracking (realized/unrealized)
- Audit trail for all trades
- Portfolio constraints enforcement
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass
class Order:
    """Represents a simulated order"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: int = 0
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    commission: float = 0.0
    rejection_reason: Optional[str] = None
    strategy_id: Optional[str] = None
    model_version: Optional[str] = None
    signal_score: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "fill_price": self.fill_price,
            "commission": self.commission,
            "rejection_reason": self.rejection_reason
        }


@dataclass
class Position:
    """Represents an open position"""
    ticker: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    entry_commission: float = 0.0
    opened_at: datetime = field(default_factory=datetime.utcnow)

    def update_price(self, price: float):
        """Update current price and recalculate P&L"""
        self.current_price = price
        self.unrealized_pnl = (price - self.avg_cost) * self.quantity
        self.unrealized_pnl_pct = ((price / self.avg_cost) - 1) * 100 if self.avg_cost > 0 else 0

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "entry_commission": self.entry_commission,
            "opened_at": self.opened_at.isoformat()
        }


@dataclass
class Trade:
    """Completed trade record for audit trail"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: int = 0
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    entry_date: datetime = field(default_factory=datetime.utcnow)
    exit_date: Optional[datetime] = None
    commission: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_period_days: int = 0
    exit_reason: Optional[str] = None  # "target", "stop", "signal_reversal", "manual"
    strategy_id: Optional[str] = None
    model_version: Optional[str] = None
    signal_score: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "side": self.side.value,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "entry_date": self.entry_date.isoformat(),
            "exit_date": self.exit_date.isoformat() if self.exit_date else None,
            "commission": self.commission,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "holding_period_days": self.holding_period_days,
            "exit_reason": self.exit_reason,
            "strategy_id": self.strategy_id,
            "model_version": self.model_version,
            "signal_score": self.signal_score
        }


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state"""
    date: date
    cash: float
    equity: float
    positions_value: float
    total_value: float
    num_positions: int
    daily_pnl: float
    daily_pnl_pct: float

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "cash": self.cash,
            "equity": self.equity,
            "positions_value": self.positions_value,
            "total_value": self.total_value,
            "num_positions": self.num_positions,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": self.daily_pnl_pct
        }


class PaperTradingEngine:
    """
    Simulated trading engine for paper trading.

    Features:
    - Market/limit order simulation
    - Position sizing with risk constraints
    - Commission and slippage modeling
    - Real-time P&L calculation
    - Complete audit trail
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_per_share: float = 0.005,
        min_commission: float = 1.0,
        max_commission: float = 50.0,
        slippage_bps: float = 5.0,  # 5 basis points default slippage
        max_position_pct: float = 0.10,  # Max 10% per position
        max_sector_pct: float = 0.30,  # Max 30% per sector
        max_portfolio_positions: int = 20
    ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_per_share = commission_per_share
        self.min_commission = min_commission
        self.max_commission = max_commission
        self.slippage_bps = slippage_bps
        self.max_position_pct = max_position_pct
        self.max_sector_pct = max_sector_pct
        self.max_portfolio_positions = max_portfolio_positions

        self.positions: Dict[str, Position] = {}
        self.pending_orders: List[Order] = []
        self.closed_trades: List[Trade] = []
        self.snapshots: List[PortfolioSnapshot] = []

        # Track sector exposure
        self.sector_exposure: Dict[str, float] = {}

        # Current prices (updated externally)
        self.current_prices: Dict[str, float] = {}

        # Sector mapping (should be loaded from database)
        self.ticker_to_sector: Dict[str, str] = {}

    def set_current_price(self, ticker: str, price: float):
        """Update current price for a ticker"""
        self.current_prices[ticker] = price
        if ticker in self.positions:
            self.positions[ticker].update_price(price)
        self._refresh_sector_exposure()

    def set_sector_mapping(self, ticker: str, sector: str):
        """Map ticker to sector for concentration checks"""
        self.ticker_to_sector[ticker] = sector
        self._refresh_sector_exposure()

    def calculate_commission(self, quantity: int, price: float) -> float:
        """Calculate commission with min/max bounds"""
        base_commission = abs(quantity) * self.commission_per_share
        return max(self.min_commission, min(self.max_commission, base_commission))

    def get_net_liquidation_value(self) -> float:
        """Return cash plus positions marked at their latest available prices."""
        return self.cash + sum(
            position.quantity * position.current_price
            for position in self.positions.values()
        )

    def _current_sector_exposure(self) -> Dict[str, float]:
        exposure: Dict[str, float] = {}
        for ticker, position in self.positions.items():
            sector = self.ticker_to_sector.get(ticker, "Unknown")
            exposure[sector] = exposure.get(sector, 0.0) + position.quantity * position.current_price
        return exposure

    def _refresh_sector_exposure(self) -> None:
        """Keep the public sector exposure cache reconciled to open positions."""
        self.sector_exposure = self._current_sector_exposure()

    def apply_slippage(self, price: float, side: OrderSide) -> float:
        """Apply slippage to execution price"""
        slippage_amount = price * (self.slippage_bps / 10000)
        if side == OrderSide.BUY:
            return price + slippage_amount
        else:
            return max(0, price - slippage_amount)

    def check_risk_constraints(
        self,
        ticker: str,
        quantity: int,
        price: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if order violates risk constraints.
        Returns (allowed, rejection_reason)
        """
        order_value = quantity * price
        net_liquidation_value = self.get_net_liquidation_value()
        existing_position_value = 0.0
        if ticker in self.positions:
            existing_position_value = self.positions[ticker].quantity * price

        # Check max position size
        max_position_value = net_liquidation_value * self.max_position_pct
        projected_position_value = existing_position_value + order_value
        if projected_position_value > max_position_value:
            return False, f"Position size ${projected_position_value:.2f} exceeds max ${max_position_value:.2f}"

        # Check max portfolio positions
        if ticker not in self.positions and len(self.positions) >= self.max_portfolio_positions:
            return False, f"Maximum portfolio positions ({self.max_portfolio_positions}) reached"

        # Check sector concentration
        sector = self.ticker_to_sector.get(ticker, "Unknown")
        current_sector_value = self._current_sector_exposure().get(sector, 0)
        max_sector_value = net_liquidation_value * self.max_sector_pct

        if current_sector_value + order_value > max_sector_value:
            return False, f"Sector {sector} exposure would exceed max ${max_sector_value:.2f}"

        # Check liquidity (minimum price)
        if price < 5.0:
            return False, f"Price ${price:.2f} below minimum $5.00"

        return True, None

    def submit_order(
        self,
        ticker: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        strategy_id: Optional[str] = None,
        model_version: Optional[str] = None,
        signal_score: Optional[float] = None
    ) -> Order:
        """Submit a new order"""
        current_price = self.current_prices.get(ticker)

        if current_price is None:
            order = Order(
                ticker=ticker,
                side=side,
                order_type=order_type,
                quantity=quantity,
                limit_price=limit_price,
                stop_price=stop_price,
                status=OrderStatus.REJECTED,
                rejection_reason=f"No price available for {ticker}"
            )
            return order

        # Risk checks for buy orders
        if side == OrderSide.BUY:
            allowed, reason = self.check_risk_constraints(ticker, quantity, current_price)
            if not allowed:
                order = Order(
                    ticker=ticker,
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    limit_price=limit_price,
                    stop_price=stop_price,
                    status=OrderStatus.REJECTED,
                    rejection_reason=reason
                )
                return order

        order = Order(
            ticker=ticker,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            strategy_id=strategy_id,
            model_version=model_version,
            signal_score=signal_score
        )

        # Try to fill immediately for market orders
        if order_type == OrderType.MARKET:
            self._fill_order(order, current_price)
        else:
            self.pending_orders.append(order)

        return order

    def _fill_order(self, order: Order, current_price: float):
        """Execute an order"""
        # Apply slippage
        fill_price = self.apply_slippage(current_price, order.side)

        # Check limit orders
        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and fill_price > order.limit_price:
                order.status = OrderStatus.PENDING
                return
            elif order.side == OrderSide.SELL and fill_price < order.limit_price:
                order.status = OrderStatus.PENDING
                return

        # Calculate commission
        commission = self.calculate_commission(order.quantity, fill_price)

        # Execute buy
        if order.side == OrderSide.BUY:
            total_cost = (order.quantity * fill_price) + commission

            if total_cost > self.cash:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = "Insufficient cash"
                return

            self.cash -= total_cost

            # Update or create position
            if order.ticker in self.positions:
                pos = self.positions[order.ticker]
                total_shares = pos.quantity + order.quantity
                pos.avg_cost = ((pos.avg_cost * pos.quantity) + (order.quantity * fill_price)) / total_shares
                pos.quantity = total_shares
                pos.entry_commission += commission
                pos.update_price(current_price)
            else:
                self.positions[order.ticker] = Position(
                    ticker=order.ticker,
                    quantity=order.quantity,
                    avg_cost=fill_price,
                    current_price=current_price,
                    entry_commission=commission,
                )

            self._refresh_sector_exposure()

        # Execute sell
        elif order.side == OrderSide.SELL:
            if order.ticker not in self.positions:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = "No position to sell"
                return

            pos = self.positions[order.ticker]

            if order.quantity > pos.quantity:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = "Insufficient shares"
                return

            quantity_before_sale = pos.quantity
            allocated_entry_commission = pos.entry_commission * (order.quantity / quantity_before_sale)

            # Calculate proceeds
            proceeds = (order.quantity * fill_price) - commission
            self.cash += proceeds

            # Update position
            pos.quantity -= order.quantity
            pos.entry_commission -= allocated_entry_commission

            if pos.quantity == 0:
                # Close position completely
                del self.positions[order.ticker]

                # Create trade record
                net_pnl = (
                    (fill_price - pos.avg_cost) * order.quantity
                    - allocated_entry_commission
                    - commission
                )
                trade = Trade(
                    ticker=order.ticker,
                    side=OrderSide.BUY,  # Original side was buy
                    quantity=order.quantity,
                    entry_price=pos.avg_cost,
                    exit_price=fill_price,
                    entry_date=pos.opened_at,
                    exit_date=datetime.utcnow(),
                    commission=allocated_entry_commission + commission,
                    pnl=net_pnl,
                    pnl_pct=(net_pnl / (pos.avg_cost * order.quantity)) * 100,
                    holding_period_days=(datetime.utcnow() - pos.opened_at).days,
                    exit_reason="position_closed",
                    strategy_id=order.strategy_id,
                    model_version=order.model_version,
                    signal_score=order.signal_score
                )
                self.closed_trades.append(trade)

            else:
                pos.update_price(current_price)

            self._refresh_sector_exposure()

        # Update order status
        order.status = OrderStatus.FILLED
        order.fill_price = fill_price
        order.commission = commission
        order.filled_at = datetime.utcnow()

    def process_pending_orders(self):
        """Process pending limit/stop orders against current prices"""
        filled_orders = []

        for order in self.pending_orders:
            current_price = self.current_prices.get(order.ticker)
            if current_price is None:
                continue

            # Check if limit order should fill
            if order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY and current_price <= order.limit_price:
                    self._fill_order(order, current_price)
                    filled_orders.append(order)
                elif order.side == OrderSide.SELL and current_price >= order.limit_price:
                    self._fill_order(order, current_price)
                    filled_orders.append(order)

            # Check if stop order should trigger
            elif order.order_type == OrderType.STOP:
                if order.side == OrderSide.BUY and current_price >= order.stop_price:
                    order.order_type = OrderType.MARKET
                    self._fill_order(order, current_price)
                    filled_orders.append(order)
                elif order.side == OrderSide.SELL and current_price <= order.stop_price:
                    order.order_type = OrderType.MARKET
                    self._fill_order(order, current_price)
                    filled_orders.append(order)

        # Remove filled orders from pending
        for order in filled_orders:
            if order in self.pending_orders:
                self.pending_orders.remove(order)

    def take_snapshot(self, snapshot_date: date):
        """Create a portfolio snapshot for historical tracking"""
        self._refresh_sector_exposure()
        positions_value = sum(
            pos.quantity * pos.current_price
            for pos in self.positions.values()
        )

        total_value = self.cash + positions_value

        # Calculate daily P&L
        if self.snapshots:
            prev_snapshot = self.snapshots[-1]
            daily_pnl = total_value - prev_snapshot.total_value
            daily_pnl_pct = (daily_pnl / prev_snapshot.total_value) * 100 if prev_snapshot.total_value > 0 else 0
        else:
            daily_pnl = total_value - self.initial_capital
            daily_pnl_pct = (daily_pnl / self.initial_capital) * 100 if self.initial_capital > 0 else 0

        snapshot = PortfolioSnapshot(
            date=snapshot_date,
            cash=self.cash,
            equity=total_value,
            positions_value=positions_value,
            total_value=total_value,
            num_positions=len(self.positions),
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct
        )

        self.snapshots.append(snapshot)
        return snapshot

    def get_portfolio_summary(self) -> dict:
        """Get current portfolio summary"""
        self._refresh_sector_exposure()
        positions_value = sum(
            pos.quantity * pos.current_price
            for pos in self.positions.values()
        )

        total_value = self.cash + positions_value
        total_pnl = total_value - self.initial_capital
        total_pnl_pct = (total_pnl / self.initial_capital) * 100 if self.initial_capital > 0 else 0

        sector_breakdown = dict(self.sector_exposure)

        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "positions_value": positions_value,
            "total_value": total_value,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "num_positions": len(self.positions),
            "num_pending_orders": len(self.pending_orders),
            "num_closed_trades": len(self.closed_trades),
            "sector_exposure": sector_breakdown,
            "positions": [pos.to_dict() for pos in self.positions.values()],
            "pending_orders": [order.to_dict() for order in self.pending_orders],
            "recent_trades": [trade.to_dict() for trade in self.closed_trades[-10:]]
        }

    def get_performance_metrics(self) -> dict:
        """Calculate performance metrics from snapshots and trades"""
        if not self.snapshots:
            return {}

        equities = [s.equity for s in self.snapshots]
        daily_returns = []

        for i in range(1, len(equities)):
            daily_return = (equities[i] - equities[i-1]) / equities[i-1] if equities[i-1] > 0 else 0
            daily_returns.append(daily_return)

        # Calculate metrics
        total_return = (equities[-1] - self.initial_capital) / self.initial_capital

        # Win rate
        winning_trades = [t for t in self.closed_trades if t.pnl > 0]
        losing_trades = [t for t in self.closed_trades if t.pnl < 0]
        win_rate = len(winning_trades) / len(self.closed_trades) if self.closed_trades else 0

        # Average win/loss
        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0

        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Sharpe ratio (annualized, assuming 252 trading days)
        import statistics
        if len(daily_returns) > 1 and statistics.stdev(daily_returns) > 0:
            sharpe_ratio = (statistics.mean(daily_returns) / statistics.stdev(daily_returns)) * (252 ** 0.5)
        else:
            sharpe_ratio = 0

        # Max drawdown
        peak = equities[0]
        max_drawdown = 0
        for equity in equities:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return {
            "total_return": total_return,
            "total_return_pct": total_return * 100,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown * 100,
            "num_trades": len(self.closed_trades),
            "num_winning_trades": len(winning_trades),
            "num_losing_trades": len(losing_trades)
        }
