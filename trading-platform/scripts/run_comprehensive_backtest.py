#!/usr/bin/env python3
"""
Comprehensive Backtest Suite
Compares Quant Strategies vs SPY Buy & Hold over 5 years
"""

import sys
import os
from datetime import datetime, timedelta
import numpy as np
import random

# Add project root and subdirectories to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'apps', 'api'))

# Import from services layer which has the correct models
from services.db.models import Asset, PriceDaily, FeatureDaily, MarketRegime, Signal, Strategy, Base
from services.backtesting.engine import BacktestEngine, BacktestResult
from services.backtesting.strategy import MomentumBreakoutStrategy
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Create a dedicated engine for scripts
SCRIPT_ENGINE = create_engine("sqlite:///./trading_platform_backtest.db", connect_args={"check_same_thread": False})
ScriptSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=SCRIPT_ENGINE)

def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=SCRIPT_ENGINE)
    print("✅ Database initialized.")

def get_db_session():
    """Get a database session for scripts."""
    db = ScriptSessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_robust_dataset(session: Session, start_date: datetime, end_date: datetime):
    """Generate 5 years of synthetic data for SPY + 20 stocks"""
    print(f"📅 Generating synthetic data from {start_date} to {end_date}...")

    # Clear existing data
    session.query(PriceDaily).delete()
    session.query(Asset).delete()
    session.commit()

    # Generate date range (trading days only - simplified)
    trading_days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # Mon-Fri
            trading_days.append(current)
        current += timedelta(days=1)

    print(f"   Generated {len(trading_days)} trading days")

    # Create assets: SPY + 20 stocks
    tickers = ["SPY"] + [f"STOCK{i:02d}" for i in range(1, 21)]
    assets = []

    for ticker in tickers:
        is_spy = (ticker == "SPY")
        # SPY grows steadily, stocks have more volatility
        base_price = 450.0 if is_spy else random.uniform(50, 200)
        drift = 0.0003 if is_spy else random.uniform(0.0001, 0.0006)
        volatility = 0.012 if is_spy else random.uniform(0.015, 0.035)

        asset = Asset(
            ticker=ticker,
            name=f"{'S&P 500 ETF' if is_spy else f'Stock {ticker}'}",
            sector="ETF" if is_spy else random.choice(["Technology", "Healthcare", "Finance", "Energy", "Consumer"]),
            industry="Broad Market" if is_spy else random.choice(["Software", "Biotech", "Banking", "Oil & Gas", "Retail"]),
            market_cap=400000000000 if is_spy else random.randint(5000000000, 500000000000),
            is_active=True
        )
        session.add(asset)
        session.flush()
        assets.append({
            'id': asset.id,
            'ticker': ticker,
            'price': base_price,
            'drift': drift,
            'volatility': volatility
        })

    session.commit()
    print(f"   Created {len(assets)} assets")

    # Generate prices
    price_data = []
    for day_idx, date in enumerate(trading_days):
        for asset in assets:
            # Random walk with drift
            daily_return = asset['drift'] + np.random.normal(0, asset['volatility'])
            asset['price'] *= (1 + daily_return)

            # Generate OHLCV
            close = asset['price']
            daily_range = close * random.uniform(0.005, 0.025)
            high = close + random.uniform(0, daily_range)
            low = close - random.uniform(0, daily_range)
            open_price = low + random.uniform(0.2, 0.8) * (high - low)
            volume = int(random.uniform(500000, 50000000) * (1 + abs(daily_return) * 10))

            price_data.append(PriceDaily(
                asset_id=asset['id'],
                time=date,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                adjusted_close=close
            ))

    session.bulk_save_objects(price_data)
    session.commit()
    print(f"   Generated {len(price_data)} price records")
    print("✅ Data generation complete.")

def run_backtest_comparison(session: Session):
    """Run backtests for multiple strategies and compare to SPY"""

    # 1. Get Asset IDs
    spy_asset = session.query(Asset).filter(Asset.ticker == "SPY").first()
    if not spy_asset:
        print("❌ SPY not found in database!")
        return

    all_assets = session.query(Asset).all()
    asset_ids = [a.id for a in all_assets]
    tickers = [a.ticker for a in all_assets]

    print(f"\n📊 Backtest Universe: {len(all_assets)} assets ({len(tickers)-1} stocks + SPY)")

    # 2. Define Date Range (5 Years)
    end_date = datetime(2024, 1, 1)
    start_date = datetime(2019, 1, 1)

    # 3. Initialize Backtester
    backtester = BacktestEngine(session)

    # 4. Strategy 1: Momentum Breakout
    print("\n🚀 Running Strategy: Momentum Breakout...")
    strategy = MomentumBreakoutStrategy()

    results_momentum = backtester.run_portfolio_backtest(
        asset_ids=asset_ids,
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        initial_capital=100000,
        commission_pct=0.001,  # 0.1%
        slippage_pct=0.0005   # 0.05%
    )

    # 5. Strategy 2: SPY Buy & Hold (Benchmark)
    print("📈 Running Benchmark: SPY Buy & Hold...")
    results_spy = backtester.run_buy_and_hold(
        asset_id=spy_asset.id,
        start_date=start_date,
        end_date=end_date,
        initial_capital=100000
    )

    # 6. Print Comparison Report
    print("\n" + "="*80)
    print("🏆 BACKTEST RESULTS COMPARISON (5 YEARS)")
    print("="*80)

    metrics_list = [
        ("Total Return (%)", "total_return_pct"),
        ("CAGR (%)", "cagr"),
        ("Sharpe Ratio", "sharpe_ratio"),
        ("Sortino Ratio", "sortino_ratio"),
        ("Max Drawdown (%)", "max_drawdown_pct"),
        ("Volatility (Ann.)", "volatility_annual"),
        ("Win Rate (%)", "win_rate"),
        ("Profit Factor", "profit_factor"),
        ("Total Trades", "total_trades")
    ]

    print(f"{'Metric':<25} | {'Momentum Strategy':<20} | {'SPY Buy/Hold':<20}")
    print("-" * 80)

    for label, key in metrics_list:
        val_strat = results_momentum.get(key, 0)
        val_spy = results_spy.get(key, 0)

        # Format trades as int, others as float
        if key == "total_trades":
            print(f"{label:<25} | {int(val_strat):<20} | {int(val_spy):<20}")
        else:
            # Highlight outperformance
            strat_str = f"{val_strat:.2f}"
            spy_str = f"{val_spy:.2f}"

            if key in ["total_return_pct", "cagr", "sharpe_ratio", "sortino_ratio", "win_rate", "profit_factor"]:
                if val_strat > val_spy:
                    strat_str = f"\033[92m{val_strat:.2f}\033[0m"  # Green
                else:
                    spy_str = f"\033[92m{val_spy:.2f}\033[0m"
            elif key in ["max_drawdown_pct", "volatility_annual"]:
                if val_strat < val_spy:
                    strat_str = f"\033[92m{val_strat:.2f}\033[0m"  # Green (lower is better)
                else:
                    spy_str = f"\033[92m{val_spy:.2f}\033[0m"

            print(f"{label:<25} | {strat_str:<20} | {spy_str:<20}")

    print("="*80)

    # 7. Alpha/Beta Analysis
    excess_return = results_momentum.get('total_return_pct', 0) - results_spy.get('total_return_pct', 0)
    print(f"\n📊 Alpha (Excess Return): {excess_return:.2f}%")

    if excess_return > 0:
        print(f"✅ Strategy OUTPERFORMED SPY by {excess_return:.2f}% over 5 years")
    else:
        print(f"⚠️ Strategy UNDERPERFORMED SPY by {abs(excess_return):.2f}%")

    # 8. Risk Adjusted Comparison
    strat_sharpe = results_momentum.get('sharpe_ratio', 0)
    spy_sharpe = results_spy.get('sharpe_ratio', 0)

    if strat_sharpe > spy_sharpe:
        print(f"✅ Better Risk-Adjusted Returns (Sharpe: {strat_sharpe:.2f} vs {spy_sharpe:.2f})")
    else:
        print(f"⚠️ Lower Risk-Adjusted Returns (Sharpe: {strat_sharpe:.2f} vs {spy_sharpe:.2f})")

    return results_momentum, results_spy

if __name__ == "__main__":
    try:
        # Initialize DB
        print("🔌 Connecting to database...")
        init_db()
        session = next(get_db_session())

        # Check if data exists, if not generate
        asset_count = session.query(Asset).count()
        if asset_count < 10:
            print("⚠️ Insufficient data. Generating 5 years of synthetic market data...")
            generate_robust_dataset(
                session,
                datetime(2019, 1, 1),
                datetime(2024, 1, 1)
            )
        else:
            print(f"✅ Found {asset_count} assets in database.")

        # Run Backtests
        run_backtest_comparison(session)

        session.close()
        print("\n✅ Backtest Suite Completed Successfully!")

    except Exception as e:
        print(f"\n❌ Error during backtest: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)