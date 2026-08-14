"""
Backtesting Engine Module
Provides vectorized and event-driven backtesting capabilities
"""
from .engine import BacktestEngine, BacktestResult
from .strategy import Strategy, StrategyConfig, MomentumBreakoutStrategy
from .metrics import PerformanceMetrics
from .walk_forward import WalkForwardAnalyzer

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "Strategy",
    "StrategyConfig",
    "MomentumBreakoutStrategy",
    "PerformanceMetrics",
    "WalkForwardAnalyzer",
]