"""Tests for OpenBB response normalization and resilient fallback behavior."""

import asyncio
from datetime import date

import httpx
import pandas as pd
import polars as pl

from services.data.providers.openbb_provider import OpenBBMarketDataProvider
from services.data.providers.yfinance_provider import _yfinance_frame_to_polars
from services.scanner.scanner_service import ScannerService


class FakeResponse:
    def __init__(self, results):
        self._results = results

    def raise_for_status(self):
        return None

    def json(self):
        return {"results": self._results}


class FakeOpenBBClient:
    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params or {}))
        if path.endswith("/profile"):
            return FakeResponse(
                [
                    {
                        "symbol": "AAPL",
                        "name": "Apple Inc.",
                        "sector": "Technology",
                        "industry_category": "Consumer Electronics",
                    }
                ]
            )
        return FakeResponse(
            [
                {
                    "symbol": "AAPL",
                    "date": "2025-01-02",
                    "open": 100,
                    "high": 103,
                    "low": 99,
                    "close": 102,
                    "volume": 1_000_000,
                },
                {
                    "symbol": "AAPL",
                    "date": "2025-01-03",
                    "open": 102,
                    "high": 105,
                    "low": 101,
                    "close": 104,
                    "volume": 1_200_000,
                },
            ]
        )

    def close(self):
        return None


class OfflineOpenBBClient:
    def get(self, path, params=None):
        request = httpx.Request("GET", f"http://openbb:6900{path}")
        raise httpx.ConnectError("OpenBB is offline", request=request)

    def close(self):
        return None


class StubFallback:
    source_name = "yfinance-direct"
    universe = ["AAPL"]

    def get_historical_prices(self, tickers, start_date=None, end_date=None):
        return pl.DataFrame(
            {
                "ticker": ["AAPL"],
                "time": [date(2025, 1, 3)],
                "open": [102.0],
                "high": [105.0],
                "low": [101.0],
                "close": [104.0],
                "volume": [1_200_000],
                "adjusted_close": [104.0],
                "company_name": ["AAPL"],
                "sector": ["Unknown"],
                "industry": ["Unknown"],
                "is_active": [True],
            }
        )

    def get_company_info(self, ticker):
        return {
            "ticker": ticker,
            "name": ticker,
            "sector": "Unknown",
            "industry": "Unknown",
            "market_cap": None,
            "is_active": True,
        }


def test_openbb_provider_normalizes_prices_and_profiles():
    client = FakeOpenBBClient()
    provider = OpenBBMarketDataProvider(
        base_url="http://openbb:6900",
        universe=["AAPL"],
        fallback=StubFallback(),
        client=client,
    )

    frame = provider.get_historical_prices(
        ["AAPL"],
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 3),
    )

    assert frame.height == 2
    assert frame["ticker"].to_list() == ["AAPL", "AAPL"]
    assert frame["company_name"].to_list() == ["Apple Inc.", "Apple Inc."]
    assert provider.status()["active_source"] == "openbb:yfinance"
    assert provider.status()["last_error"] is None
    historical_call = next(call for call in client.calls if call[0].endswith("/historical"))
    assert historical_call[1]["adjustment"] == "splits_and_dividends"


def test_openbb_provider_is_unverified_before_its_first_request():
    provider = OpenBBMarketDataProvider(
        base_url="http://openbb:6900",
        universe=["AAPL"],
        fallback=StubFallback(),
        client=FakeOpenBBClient(),
    )

    assert provider.status()["active_source"] == "not-yet-queried"
    assert provider.status()["live_market_data"] is False


def test_openbb_provider_uses_direct_fallback_when_service_is_offline():
    provider = OpenBBMarketDataProvider(
        base_url="http://openbb:6900",
        universe=["AAPL"],
        fallback=StubFallback(),
        client=OfflineOpenBBClient(),
    )

    frame = provider.get_historical_prices(["AAPL"])

    assert frame.height == 1
    assert provider.status()["active_source"] == "yfinance-direct"
    assert "offline" in provider.status()["last_error"].lower()


def test_successful_intraday_request_recovers_status_after_fallback():
    provider = OpenBBMarketDataProvider(
        base_url="http://openbb:6900",
        universe=["AAPL"],
        fallback=StubFallback(),
        client=OfflineOpenBBClient(),
    )
    provider.get_historical_prices(["AAPL"])
    assert provider.status()["active_source"] == "yfinance-direct"

    provider._client = FakeOpenBBClient()
    prices = asyncio.run(provider.get_intraday_prices("AAPL", date(2025, 1, 3)))

    assert prices
    assert provider.status()["active_source"] == "openbb:yfinance"
    assert provider.status()["last_error"] is None


def test_yfinance_multi_index_data_is_normalized():
    columns = pd.MultiIndex.from_product(
        [["AAPL"], ["Open", "High", "Low", "Close", "Volume"]]
    )
    raw = pd.DataFrame(
        [[100.0, 103.0, 99.0, 102.0, 1_000_000]],
        index=pd.DatetimeIndex(["2025-01-02"], name="Date"),
        columns=columns,
    )

    frame = _yfinance_frame_to_polars(raw, ["AAPL"])

    assert frame.height == 1
    assert frame.to_dicts()[0]["close"] == 102.0
    assert frame.to_dicts()[0]["time"] == date(2025, 1, 2)


def test_scanner_returns_one_latest_result_per_requested_ticker():
    from services.data.providers.mock_provider import MockMarketDataProvider

    service = ScannerService(
        data_provider=MockMarketDataProvider(num_stocks=2, seed=7),
        benchmark_ticker="SPY",
    )

    results = service.run_scan(tickers=["AAPL", "MSFT"], top_n=10)

    assert len(results) == 2
    assert {result.ticker for result in results} == {"AAPL", "MSFT"}
