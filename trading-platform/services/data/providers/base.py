"""Data provider abstraction layer."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime, date

from services.data.capabilities import ProviderCapabilities


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    capabilities = ProviderCapabilities()

    @abstractmethod
    async def get_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get daily OHLCV data for a ticker."""
        pass

    @abstractmethod
    async def get_intraday_prices(
        self,
        ticker: str,
        date: date,
        interval: str = "5min"
    ) -> List[Dict[str, Any]]:
        """Get intraday price data."""
        pass

    @abstractmethod
    async def get_stock_universe(self) -> List[Dict[str, Any]]:
        """Get list of available stocks with metadata."""
        pass

    @abstractmethod
    async def get_current_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get latest price for a ticker."""
        pass


class NewsProvider(ABC):
    """Abstract base class for news data providers."""

    @abstractmethod
    async def get_news(
        self,
        ticker: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get news articles."""
        pass


class FundamentalsProvider(ABC):
    """Abstract base class for fundamental data providers."""

    @abstractmethod
    async def get_financials(
        self,
        ticker: str,
        period: str = "annual"
    ) -> Dict[str, Any]:
        """Get financial statements."""
        pass

    @abstractmethod
    async def get_ratios(self, ticker: str) -> Dict[str, Any]:
        """Get financial ratios."""
        pass

    @abstractmethod
    async def get_earnings_calendar(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get upcoming earnings dates."""
        pass


class MacroDataProvider(ABC):
    """Abstract base class for macroeconomic data providers."""

    @abstractmethod
    async def get_indicator(self, indicator_id: str) -> Dict[str, Any]:
        """Get macroeconomic indicator (e.g., VIX, Treasury yields)."""
        pass

    @abstractmethod
    async def get_market_breadth(self, date: date) -> Dict[str, Any]:
        """Get market breadth indicators."""
        pass


class BrokerProvider(ABC):
    """Abstract base class for broker integration."""

    @abstractmethod
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        pass

    @abstractmethod
    async def place_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Place a trade order."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        pass
