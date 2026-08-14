"""
Scanner Service - High-level service for stock scanning operations

This service orchestrates the scanner engine with data retrieval and caching.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from services.scanner.scanner_engine import QuantScanner, StockScore, SetupType
from services.features.engine import FeatureEngine
from services.data.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)


class ScannerService:
    """
    Service layer for stock scanning operations.

    Handles:
    - Data retrieval from providers
    - Feature calculation
    - Scanning and ranking
    - Caching of results
    """

    def __init__(
        self,
        data_provider: MarketDataProvider,
        feature_engine: Optional[FeatureEngine] = None,
        scanner_config: Optional[Dict[str, Any]] = None
    ):
        self.data_provider = data_provider
        self.feature_engine = feature_engine or FeatureEngine()
        self.scanner = QuantScanner(config=scanner_config)
        self._last_scan_results: Optional[List[StockScore]] = None
        self._last_scan_timestamp: Optional[datetime] = None

    def run_scan(
        self,
        tickers: Optional[List[str]] = None,
        top_n: int = 50,
        use_cached_features: bool = True,
        market_regime: Optional[Dict[str, Any]] = None
    ) -> List[StockScore]:
        """
        Execute a full scan of the stock universe.

        Args:
            tickers: Optional list of specific tickers to scan. If None, scans entire universe.
            top_n: Number of top opportunities to return
            use_cached_features: Whether to use cached features if available
            market_regime: Current market regime information

        Returns:
            List of ranked StockScore objects
        """
        logger.info(f"Starting scan for {len(tickers) if tickers else 'all'} stocks")

        # Get stock universe if not specified
        if tickers is None:
            tickers = self.data_provider.get_stock_universe_sync(
                min_price=self.scanner.min_price,
                min_volume=self.scanner.min_avg_volume,
                min_market_cap=self.scanner.min_market_cap
            )

        if not tickers:
            logger.warning("No stocks found matching criteria")
            return []

        logger.info(f"Scanning {len(tickers)} stocks")

        # Retrieve price data
        end_date = datetime.now().date()
        price_data = self.data_provider.get_historical_prices(
            tickers=tickers,
            start_date=None,  # Use default lookback
            end_date=end_date
        )

        if price_data.height == 0:
            logger.warning("No price data retrieved")
            return []

        # Calculate features
        logger.info("Calculating features...")
        features_df = self.feature_engine.calculate_all_features(price_data)

        if features_df.height == 0:
            logger.warning("No features calculated")
            return []

        # Run scanner
        logger.info("Running scanner engine...")
        results = self.scanner.scan(
            features_df=features_df,
            market_regime=market_regime,
            top_n=top_n
        )

        # Cache results
        self._last_scan_results = results
        self._last_scan_timestamp = datetime.now()

        logger.info(f"Scan complete. Found {len(results)} opportunities")

        return results

    def get_top_opportunities(self, n: int = 10) -> List[StockScore]:
        """
        Get the top N opportunities from the last scan.

        Args:
            n: Number of opportunities to return

        Returns:
            List of top StockScore objects
        """
        if self._last_scan_results is None:
            logger.warning("No scan results available. Run scan first.")
            return []

        return self._last_scan_results[:n]

    def get_opportunity_by_ticker(self, ticker: str) -> Optional[StockScore]:
        """
        Get scan result for a specific ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            StockScore object or None if not found
        """
        if self._last_scan_results is None:
            return None

        for score in self._last_scan_results:
            if score.ticker == ticker:
                return score

        return None

    def get_scan_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics of the last scan.

        Returns:
            Dictionary with scan summary
        """
        if self._last_scan_results is None:
            return {"status": "no_scan_run"}

        return self.scanner.get_scan_summary(self._last_scan_results)

    def filter_by_setup_type(
        self,
        setup_type: SetupType,
        min_score: float = 0.0
    ) -> List[StockScore]:
        """
        Filter scan results by setup type and minimum score.

        Args:
            setup_type: Type of setup to filter for
            min_score: Minimum composite score threshold

        Returns:
            Filtered list of StockScore objects
        """
        if self._last_scan_results is None:
            return []

        return [
            score for score in self._last_scan_results
            if score.setup_type == setup_type and score.composite_score >= min_score
        ]

    def filter_by_sector(
        self,
        sector: str,
        min_score: float = 0.0
    ) -> List[StockScore]:
        """
        Filter scan results by sector and minimum score.

        Args:
            sector: Sector name to filter for
            min_score: Minimum composite score threshold

        Returns:
            Filtered list of StockScore objects
        """
        if self._last_scan_results is None:
            return []

        return [
            score for score in self._last_scan_results
            if score.sector.lower() == sector.lower() and score.composite_score >= min_score
        ]

    def get_last_scan_timestamp(self) -> Optional[datetime]:
        """Get the timestamp of the last scan."""
        return self._last_scan_timestamp

    def clear_cache(self):
        """Clear cached scan results."""
        self._last_scan_results = None
        self._last_scan_timestamp = None