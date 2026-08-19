"""OpenBB REST adapter with a direct-yfinance fallback."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import httpx
import polars as pl

from .base import MarketDataProvider
from .yfinance_provider import YFinanceMarketDataProvider, _empty_price_frame, _normalize_tickers

logger = logging.getLogger(__name__)

PRICE_ADJUSTMENT = "splits_and_dividends"


class OpenBBMarketDataProvider(MarketDataProvider):
    """Consume OpenBB's FastAPI service and fall back to direct Yahoo Finance."""

    def __init__(
        self,
        base_url: str,
        provider: str = "yfinance",
        universe: Optional[Sequence[str]] = None,
        lookback_days: int = 400,
        timeout_seconds: float = 60.0,
        fallback: Optional[YFinanceMarketDataProvider] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        self.lookback_days = lookback_days
        self.fallback = fallback or YFinanceMarketDataProvider(universe, lookback_days)
        self.universe = _normalize_tickers(universe or self.fallback.universe)
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout_seconds)
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self.last_source = "not-yet-queried"
        self.last_error: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        return {
            "configured_provider": "openbb",
            "openbb_data_provider": self.provider,
            "openbb_url": self.base_url,
            "active_source": self.last_source,
            "fallback_source": self.fallback.source_name,
            "last_error": self.last_error,
            "default_universe_size": len(self.universe),
            "live_market_data": self.last_source != "not-yet-queried",
        }

    def get_stock_universe_sync(
        self,
        min_price: float = 0.0,
        min_volume: int = 0,
        min_market_cap: float = 0.0,
    ) -> List[str]:
        return list(self.universe)

    def get_historical_prices(
        self,
        tickers: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pl.DataFrame:
        symbols = _normalize_tickers(tickers)
        if not symbols:
            return _empty_price_frame()

        end = end_date or date.today()
        start = start_date or end - timedelta(days=self.lookback_days)
        try:
            results = self._request(
                "/api/v1/equity/price/historical",
                {
                    "symbol": ",".join(symbols),
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "interval": "1d",
                    "adjustment": PRICE_ADJUSTMENT,
                    "provider": self.provider,
                },
            )
            frame = self._price_results_to_frame(results, symbols)
            if frame.is_empty():
                raise ValueError("OpenBB returned no historical price records")
            self._load_profiles(symbols)
            frame = self._attach_profiles(frame)
            self.last_source = f"openbb:{self.provider}"
            self.last_error = None
            return frame
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            self.last_error = str(exc)
            self.last_source = self.fallback.source_name
            logger.warning("OpenBB request failed; using direct yfinance fallback: %s", exc)
            return self.fallback.get_historical_prices(symbols, start, end)

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
        try:
            results = await asyncio.to_thread(
                self._request,
                "/api/v1/equity/price/historical",
                {
                    "symbol": ticker.upper(),
                    "start_date": date.isoformat(),
                    "end_date": date.isoformat(),
                    "interval": interval.replace("min", "m"),
                    "adjustment": PRICE_ADJUSTMENT,
                    "provider": self.provider,
                },
            )
            frame = self._price_results_to_frame(results, [ticker.upper()])
            if frame.is_empty():
                raise ValueError(f"OpenBB returned no intraday price records for {ticker.upper()}")
            self.last_source = f"openbb:{self.provider}"
            self.last_error = None
            return frame.to_dicts()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            self.last_error = str(exc)
            self.last_source = self.fallback.source_name
            return await self.fallback.get_intraday_prices(ticker, date, interval)

    async def get_stock_universe(self) -> List[Dict[str, Any]]:
        await asyncio.to_thread(self._load_profiles, self.universe)
        return [self.get_company_info(ticker) for ticker in self.universe]

    async def get_current_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        symbol = ticker.upper()
        try:
            results = await asyncio.to_thread(
                self._request,
                "/api/v1/equity/price/quote",
                {"symbol": symbol, "provider": self.provider},
            )
            if not results:
                raise ValueError(f"OpenBB returned no quote for {symbol}")
            quote = results[0]
            price = quote.get("last_price") or quote.get("price") or quote.get("close")
            if price is None:
                raise ValueError(f"OpenBB quote for {symbol} has no price")
            self.last_source = f"openbb:{self.provider}"
            self.last_error = None
            return {
                "ticker": symbol,
                "price": float(price),
                "timestamp": quote.get("last_trade_time") or datetime.now().isoformat(),
                "source": self.last_source,
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            self.last_error = str(exc)
            self.last_source = self.fallback.source_name
            return await self.fallback.get_current_price(symbol)

    def get_company_info(self, ticker: str) -> Dict[str, Any]:
        symbol = ticker.upper()
        return self._profiles.get(symbol) or self.fallback.get_company_info(symbol)

    def get_sector_for_ticker(self, ticker: str) -> str:
        return str(self.get_company_info(ticker).get("sector") or "Unknown")

    def refresh_data(self, tickers: Optional[List[str]] = None) -> None:
        if tickers is None:
            self._profiles.clear()
            return
        for ticker in tickers:
            self._profiles.pop(ticker.upper(), None)

    def close(self) -> None:
        self._client.close()

    def _request(self, path: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list):
            raise ValueError(f"OpenBB response from {path} has no results list")
        return results

    def _load_profiles(self, symbols: Sequence[str]) -> None:
        missing = [symbol for symbol in symbols if symbol not in self._profiles]
        if not missing:
            return
        try:
            results = self._request(
                "/api/v1/equity/profile",
                {"symbol": ",".join(missing), "provider": self.provider},
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.info("OpenBB profiles unavailable; keeping symbol-only metadata: %s", exc)
            return

        for item in results:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol:
                continue
            self._profiles[symbol] = {
                "ticker": symbol,
                "name": item.get("name") or item.get("legal_name") or symbol,
                "sector": item.get("sector") or "Unknown",
                "industry": item.get("industry_category") or item.get("industry_group") or "Unknown",
                "market_cap": item.get("market_cap"),
                "is_active": item.get("is_actively_trading", True),
            }

    def _attach_profiles(self, frame: pl.DataFrame) -> pl.DataFrame:
        records = []
        for row in frame.to_dicts():
            profile = self.get_company_info(row["ticker"])
            row.update(
                {
                    "company_name": profile["name"],
                    "sector": profile["sector"],
                    "industry": profile["industry"],
                    "is_active": profile["is_active"],
                }
            )
            if profile.get("market_cap") is not None:
                row["market_cap"] = profile["market_cap"]
            records.append(row)
        return pl.DataFrame(records)

    @staticmethod
    def _price_results_to_frame(
        results: Sequence[Dict[str, Any]],
        symbols: Sequence[str],
    ) -> pl.DataFrame:
        records: List[Dict[str, Any]] = []
        for item in results:
            symbol = str(item.get("symbol") or (symbols[0] if len(symbols) == 1 else "")).upper()
            if not symbol:
                raise ValueError("OpenBB multi-symbol price record is missing its symbol")
            timestamp = item.get("date") or item.get("datetime")
            if timestamp is None or item.get("close") is None:
                continue
            parsed_time = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).date()
            close = float(item["close"])
            records.append(
                {
                    "ticker": symbol,
                    "time": parsed_time,
                    "open": float(item.get("open") or close),
                    "high": float(item.get("high") or close),
                    "low": float(item.get("low") or close),
                    "close": close,
                    "volume": int(item.get("volume") or 0),
                    "adjusted_close": close,
                    "company_name": symbol,
                    "sector": "Unknown",
                    "industry": "Unknown",
                    "is_active": True,
                }
            )
        return pl.DataFrame(records) if records else _empty_price_frame()
