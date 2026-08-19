"""Mock market data provider for testing and development."""

from typing import List, Optional, Dict, Any
from datetime import date, timedelta
import random
import polars as pl

from .base import MarketDataProvider
from services.data.capabilities import ProviderCapabilities


class MockMarketDataProvider(MarketDataProvider):
    """Mock implementation of MarketDataProvider for testing."""

    def __init__(
        self,
        num_stocks: int = 50,
        seed: Optional[int] = None,
        capabilities: Optional[ProviderCapabilities] = None,
    ):
        if seed is not None:
            random.seed(seed)

        self.num_stocks = num_stocks
        self.capabilities = capabilities or ProviderCapabilities.requested_symbol_prices_only()
        self._stocks = self._generate_stock_universe()

    def _generate_stock_universe(self) -> List[Dict[str, Any]]:
        """Generate a mock stock universe."""
        sectors = ["Technology", "Healthcare", "Financial", "Consumer", "Industrial", "Energy"]
        industries = {
            "Technology": ["Software", "Hardware", "Semiconductors"],
            "Healthcare": ["Biotech", "Pharmaceuticals", "Medical Devices"],
            "Financial": ["Banks", "Insurance", "Asset Management"],
            "Consumer": ["Retail", "Food & Beverage", "Entertainment"],
            "Industrial": ["Manufacturing", "Transportation", "Construction"],
            "Energy": ["Oil & Gas", "Renewable Energy", "Utilities"],
        }

        stocks = []
        for i in range(1, self.num_stocks + 1):
            ticker = f"MOCK{i:03d}"
            sector = random.choice(sectors)
            industry = random.choice(industries[sector])

            stocks.append({
                "ticker": ticker,
                "name": f"Mock Company {i}",
                "sector": sector,
                "industry": industry,
                "market_cap": random.uniform(500e6, 500e9),
                "is_active": True,
            })

        return stocks

    async def get_stock_universe(self) -> List[Dict[str, Any]]:
        """Get list of stock tickers matching criteria."""
        return self._stocks

    def get_stock_universe_sync(
        self,
        min_price: float = 0.0,
        min_volume: int = 0,
        min_market_cap: float = 0.0,
    ) -> List[str]:
        """Synchronous version for scanner service."""
        return [stock["ticker"] for stock in self._stocks]

    async def get_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Get daily OHLCV data for a ticker."""
        # Generate dates (weekdays only)
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)

        # Generate price data
        base_price = 20 + (hash(ticker) % 180)
        records = []
        for d in dates:
            daily_return = random.gauss(0.0003, 0.025)
            base_price *= (1 + daily_return)
            base_price = max(base_price, 1.0)

            daily_volatility = abs(random.gauss(0.015, 0.01))
            high = base_price * (1 + daily_volatility)
            low = base_price * (1 - daily_volatility)
            open_price = base_price * (1 + random.gauss(0, 0.005))
            volume = random.randint(200000, 10000000)

            records.append({
                "ticker": ticker,
                "time": d,
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(base_price, 2),
                "volume": volume,
            })

        return records

    async def get_intraday_prices(
        self,
        ticker: str,
        date: date,
        interval: str = "5min",
    ) -> List[Dict[str, Any]]:
        """Get intraday prices (mock)."""
        return []

    async def get_current_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get latest price for a ticker."""
        stock_info = self.get_company_info(ticker)
        if not stock_info:
            return None

        base_price = 20 + (hash(ticker) % 180)
        return {
            "ticker": ticker,
            "price": round(base_price, 2),
            "timestamp": date.today(),
        }

    def get_historical_prices(
        self,
        tickers: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pl.DataFrame:
        """Get historical daily prices for multiple tickers (sync version)."""
        if start_date is None:
            start_date = date.today() - timedelta(days=365)
        if end_date is None:
            end_date = date.today()

        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)

        records = []
        for ticker in tickers:
            base_price = 20 + (hash(ticker) % 180)

            for d in dates:
                daily_return = random.gauss(0.0003, 0.025)
                base_price *= (1 + daily_return)
                base_price = max(base_price, 1.0)

                daily_volatility = abs(random.gauss(0.015, 0.01))
                high = base_price * (1 + daily_volatility)
                low = base_price * (1 - daily_volatility)
                open_price = base_price * (1 + random.gauss(0, 0.005))
                volume = random.randint(200000, 10000000)

                records.append({
                    "ticker": ticker,
                    "time": d,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(base_price, 2),
                    "volume": volume,
                    "adjusted_close": round(base_price, 2),
                })

        return pl.DataFrame(records)

    def get_company_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get company information."""
        for stock in self._stocks:
            if stock["ticker"] == ticker:
                return stock
        return None

    def get_sector_for_ticker(self, ticker: str) -> Optional[str]:
        """Get sector for a ticker."""
        info = self.get_company_info(ticker)
        return info["sector"] if info else None

    def refresh_data(self, tickers: Optional[List[str]] = None):
        """Refresh data cache (no-op for mock)."""
        pass
