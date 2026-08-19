"""Direct Yahoo Finance market-data provider used as an OpenBB fallback."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd
import polars as pl
import yfinance as yf

from .base import MarketDataProvider


DEFAULT_SCANNER_UNIVERSE = (
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
    "JPM",
    "LLY",
    "XOM",
    "COST",
    "UNH",
    "HD",
    "PG",
)


class YFinanceMarketDataProvider(MarketDataProvider):
    """Fetch adjusted market data directly from yfinance."""

    source_name = "yfinance-direct"

    def __init__(
        self,
        universe: Optional[Sequence[str]] = None,
        lookback_days: int = 400,
        download: Optional[Callable[..., pd.DataFrame]] = None,
    ) -> None:
        self.universe = _normalize_tickers(universe or DEFAULT_SCANNER_UNIVERSE)
        self.lookback_days = lookback_days
        self._download = download or yf.download

    def get_stock_universe_sync(
        self,
        min_price: float = 0.0,
        min_volume: int = 0,
        min_market_cap: float = 0.0,
    ) -> List[str]:
        """Return the configured liquid-stock starter universe."""
        return list(self.universe)

    def get_historical_prices(
        self,
        tickers: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pl.DataFrame:
        """Download adjusted daily OHLCV records for one or more symbols."""
        symbols = _normalize_tickers(tickers)
        if not symbols:
            return _empty_price_frame()

        end = end_date or date.today()
        start = start_date or end - timedelta(days=self.lookback_days)
        raw = self._download(
            tickers=symbols,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True,
        )
        return _yfinance_frame_to_polars(raw, symbols)

    async def get_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        frame = await asyncio.to_thread(
            self.get_historical_prices,
            [ticker],
            start_date,
            end_date,
        )
        return frame.to_dicts()

    async def get_intraday_prices(
        self,
        ticker: str,
        date: date,
        interval: str = "5min",
    ) -> List[Dict[str, Any]]:
        yfinance_interval = interval.replace("min", "m")
        raw = await asyncio.to_thread(
            self._download,
            tickers=[ticker.upper()],
            start=date.isoformat(),
            end=(date + timedelta(days=1)).isoformat(),
            interval=yfinance_interval,
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=False,
        )
        return _yfinance_frame_to_polars(raw, [ticker.upper()]).to_dicts()

    async def get_stock_universe(self) -> List[Dict[str, Any]]:
        return [self.get_company_info(ticker) for ticker in self.universe]

    async def get_current_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        end = date.today()
        frame = await asyncio.to_thread(
            self.get_historical_prices,
            [ticker],
            end - timedelta(days=10),
            end,
        )
        if frame.is_empty():
            return None
        latest = frame.sort("time").tail(1).to_dicts()[0]
        return {
            "ticker": ticker.upper(),
            "price": latest["close"],
            "timestamp": latest["time"],
            "source": self.source_name,
        }

    def get_company_info(self, ticker: str) -> Dict[str, Any]:
        symbol = ticker.upper()
        return {
            "ticker": symbol,
            "name": symbol,
            "sector": "Unknown",
            "industry": "Unknown",
            "market_cap": None,
            "is_active": True,
        }

    def get_sector_for_ticker(self, ticker: str) -> str:
        return "Unknown"

    def refresh_data(self, tickers: Optional[List[str]] = None) -> None:
        """The direct provider has no local cache to clear."""


def _normalize_tickers(tickers: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))


def _empty_price_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "ticker": pl.Utf8,
            "time": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Int64,
            "adjusted_close": pl.Float64,
            "company_name": pl.Utf8,
            "sector": pl.Utf8,
            "industry": pl.Utf8,
            "is_active": pl.Boolean,
        }
    )


def _extract_symbol_frame(raw: pd.DataFrame, ticker: str, symbol_count: int) -> pd.DataFrame:
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw if symbol_count == 1 else pd.DataFrame()

    level_zero = raw.columns.get_level_values(0)
    level_one = raw.columns.get_level_values(1)
    if ticker in level_zero:
        return raw[ticker]
    if ticker in level_one:
        return raw.xs(ticker, axis=1, level=1)
    return pd.DataFrame()


def _yfinance_frame_to_polars(raw: pd.DataFrame, tickers: Sequence[str]) -> pl.DataFrame:
    if raw is None or raw.empty:
        return _empty_price_frame()

    records: List[Dict[str, Any]] = []
    for ticker in tickers:
        frame = _extract_symbol_frame(raw, ticker, len(tickers))
        if frame.empty:
            continue

        frame = frame.reset_index()
        columns = {str(column).lower(): column for column in frame.columns}
        time_column = columns.get("date") or columns.get("datetime")
        required = {name: columns.get(name) for name in ("open", "high", "low", "close", "volume")}
        if time_column is None or any(column is None for column in required.values()):
            continue

        for row in frame.to_dict(orient="records"):
            close = _finite_float(row[required["close"]])
            if close is None:
                continue
            timestamp = pd.Timestamp(row[time_column]).date()
            records.append(
                {
                    "ticker": ticker,
                    "time": timestamp,
                    "open": _finite_float(row[required["open"]]),
                    "high": _finite_float(row[required["high"]]),
                    "low": _finite_float(row[required["low"]]),
                    "close": close,
                    "volume": int(_finite_float(row[required["volume"]]) or 0),
                    "adjusted_close": close,
                    "company_name": ticker,
                    "sector": "Unknown",
                    "industry": "Unknown",
                    "is_active": True,
                }
            )

    return pl.DataFrame(records) if records else _empty_price_frame()


def _finite_float(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)
