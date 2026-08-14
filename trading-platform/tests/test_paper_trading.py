"""Tests for Paper Trading Engine"""

import pytest
from datetime import datetime, date, timedelta
from services.paper_trading.engine import (
    PaperTradingEngine,
    OrderSide,
    OrderType,
    OrderStatus
)


class TestPaperTradingEngine:
    """Test suite for paper trading engine"""

    def test_engine_initialization(self):
        """Test engine initializes with correct defaults"""
        engine = PaperTradingEngine(initial_capital=50000.0)

        assert engine.initial_capital == 50000.0
        assert engine.cash == 50000.0
        assert len(engine.positions) == 0
        assert len(engine.closed_trades) == 0

    def test_submit_buy_order_market(self):
        """Test submitting and filling a market buy order"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.20  # Allow 20% position
        )
        engine.set_current_price("AAPL", 150.0)
        engine.set_sector_mapping("AAPL", "Technology")

        order = engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET
        )

        assert order.status == OrderStatus.FILLED
        assert order.fill_price is not None
        assert order.fill_price >= 150.0  # With slippage
        assert "AAPL" in engine.positions
        assert engine.positions["AAPL"].quantity == 100
        assert engine.cash < 100000.0  # Cash reduced

    def test_submit_sell_order_closes_position(self):
        """Test selling closes position and creates trade record"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.20
        )
        engine.set_current_price("AAPL", 150.0)
        engine.set_sector_mapping("AAPL", "Technology")

        # Buy
        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET
        )

        # Sell at higher price
        engine.set_current_price("AAPL", 160.0)
        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.MARKET
        )

        assert "AAPL" not in engine.positions
        assert len(engine.closed_trades) == 1

        trade = engine.closed_trades[0]
        assert trade.ticker == "AAPL"
        assert trade.pnl > 0  # Profitable trade

    def test_risk_constraint_max_position_size(self):
        """Test rejection of order exceeding max position size"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.10  # 10% max
        )
        engine.set_current_price("AAPL", 150.0)

        # Try to buy $20,000 worth (20% of portfolio)
        order = engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=134,  # ~$20,100
            order_type=OrderType.MARKET
        )

        assert order.status == OrderStatus.REJECTED
        assert "exceeds max" in order.rejection_reason

    def test_risk_constraint_minimum_price(self):
        """Test rejection of stocks below minimum price"""
        engine = PaperTradingEngine(initial_capital=100000.0)
        engine.set_current_price("PENNY", 3.50)

        order = engine.submit_order(
            ticker="PENNY",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET
        )

        assert order.status == OrderStatus.REJECTED
        assert "below minimum" in order.rejection_reason

    def test_limit_order_pending(self):
        """Test limit order stays pending until price reached"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.20
        )
        engine.set_current_price("AAPL", 150.0)

        # Submit buy limit below current price
        order = engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=145.0
        )

        assert order.status == OrderStatus.PENDING
        assert len(engine.pending_orders) == 1

        # Price drops to limit
        engine.set_current_price("AAPL", 144.0)
        engine.process_pending_orders()

        assert order.status == OrderStatus.FILLED
        assert len(engine.pending_orders) == 0

    def test_stop_order_triggers(self):
        """Test stop order triggers when price reaches stop level"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.20
        )
        engine.set_current_price("AAPL", 150.0)

        # Submit buy stop above current price
        order = engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.STOP,
            stop_price=155.0
        )

        assert order.status == OrderStatus.PENDING

        # Price rises to stop level
        engine.set_current_price("AAPL", 156.0)
        engine.process_pending_orders()

        assert order.status == OrderStatus.FILLED

    def test_portfolio_snapshot(self):
        """Test taking portfolio snapshots"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.20
        )
        engine.set_current_price("AAPL", 150.0)
        engine.set_sector_mapping("AAPL", "Technology")

        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET
        )

        snapshot = engine.take_snapshot(date.today())

        assert snapshot.cash < 100000.0
        assert snapshot.positions_value > 0
        assert snapshot.total_value == snapshot.cash + snapshot.positions_value
        assert snapshot.num_positions == 1

    def test_performance_metrics(self):
        """Test calculation of performance metrics"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.20
        )
        engine.set_current_price("AAPL", 150.0)
        engine.set_sector_mapping("AAPL", "Technology")

        # Buy
        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET
        )

        # Take snapshots
        engine.take_snapshot(date.today() - timedelta(days=1))

        # Sell at profit
        engine.set_current_price("AAPL", 165.0)
        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.MARKET
        )

        engine.take_snapshot(date.today())

        metrics = engine.get_performance_metrics()

        assert "total_return" in metrics
        assert "win_rate" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert metrics["num_trades"] == 1
        assert metrics["num_winning_trades"] == 1

    def test_sector_concentration_limit(self):
        """Test sector concentration limits"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.50,  # Allow larger positions to test sector limit
            max_sector_pct=0.30  # 30% max per sector
        )

        engine.set_current_price("AAPL", 150.0)
        engine.set_current_price("MSFT", 300.0)
        engine.set_sector_mapping("AAPL", "Technology")
        engine.set_sector_mapping("MSFT", "Technology")

        # Buy AAPL - 20% of portfolio ($20k)
        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=133,  # ~$19,950
            order_type=OrderType.MARKET
        )

        # Try to buy MSFT that would exceed 30% tech exposure
        # Current tech: ~$20k, Max tech: $30k, So MSFT order > $10k should fail
        order = engine.submit_order(
            ticker="MSFT",
            side=OrderSide.BUY,
            quantity=50,  # ~$15,000 - would exceed 30% sector
            order_type=OrderType.MARKET
        )

        assert order.status == OrderStatus.REJECTED
        assert "Sector" in order.rejection_reason

    def test_partial_position_close(self):
        """Test selling partial position"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.20
        )
        engine.set_current_price("AAPL", 150.0)
        engine.set_sector_mapping("AAPL", "Technology")

        # Buy 100 shares
        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET
        )

        # Sell 50 shares
        engine.set_current_price("AAPL", 160.0)
        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.SELL,
            quantity=50,
            order_type=OrderType.MARKET
        )

        assert "AAPL" in engine.positions
        assert engine.positions["AAPL"].quantity == 50
        assert len(engine.closed_trades) == 0  # Position not fully closed

    def test_insufficient_shares_rejection(self):
        """Test rejection when selling more than owned"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.20
        )
        engine.set_current_price("AAPL", 150.0)
        engine.set_sector_mapping("AAPL", "Technology")

        # Buy 50 shares
        engine.submit_order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=50,
            order_type=OrderType.MARKET
        )

        # Try to sell 100 shares
        order = engine.submit_order(
            ticker="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.MARKET
        )

        assert order.status == OrderStatus.REJECTED
        assert "Insufficient shares" in order.rejection_reason

    def test_portfolio_summary(self):
        """Test getting portfolio summary"""
        engine = PaperTradingEngine(
            initial_capital=100000.0,
            max_position_pct=0.50  # Allow larger positions
        )
        engine.set_current_price("AAPL", 150.0)
        engine.set_current_price("MSFT", 300.0)
        engine.set_sector_mapping("AAPL", "Technology")
        engine.set_sector_mapping("MSFT", "Healthcare")  # Different sector

        engine.submit_order(ticker="AAPL", side=OrderSide.BUY, quantity=100, order_type=OrderType.MARKET)
        engine.submit_order(ticker="MSFT", side=OrderSide.BUY, quantity=50, order_type=OrderType.MARKET)

        summary = engine.get_portfolio_summary()

        assert "initial_capital" in summary
        assert "cash" in summary
        assert "positions_value" in summary
        assert "total_value" in summary
        assert "sector_exposure" in summary
        assert "positions" in summary
        assert summary["num_positions"] == 2
        assert "Technology" in summary["sector_exposure"]