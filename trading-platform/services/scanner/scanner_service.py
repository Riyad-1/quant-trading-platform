"""
Scanner Service - High-level service for stock scanning operations

This service orchestrates the scanner engine with data retrieval and caching.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import polars as pl

from services.scanner.scanner_engine import QuantScanner, StockScore, SetupType
from services.features.engine import FeatureEngine
from services.data.providers.base import MarketDataProvider
from services.universe.integrity import evaluate_research_integrity

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
        scanner_config: Optional[Dict[str, Any]] = None,
        benchmark_ticker: str = "SPY",
    ):
        self.data_provider = data_provider
        self.feature_engine = feature_engine or FeatureEngine()
        self.scanner = QuantScanner(config=scanner_config)
        self.benchmark_ticker = benchmark_ticker.upper()
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

        scan_tickers = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))
        if not scan_tickers:
            logger.warning("No stocks found matching criteria")
            return []

        logger.info(f"Scanning {len(scan_tickers)} stocks")

        fetch_tickers = list(scan_tickers)
        if self.benchmark_ticker not in fetch_tickers:
            fetch_tickers.append(self.benchmark_ticker)

        # Retrieve price data
        end_date = datetime.now().date()
        price_data = self.data_provider.get_historical_prices(
            tickers=fetch_tickers,
            start_date=None,  # Use default lookback
            end_date=end_date
        )

        if price_data.height == 0:
            logger.warning("No price data retrieved")
            return []

        # Calculate each symbol independently so rolling windows never cross ticker boundaries.
        logger.info("Calculating features...")
        latest_feature_rows = []
        for ticker in fetch_tickers:
            ticker_prices = price_data.filter(pl.col("ticker") == ticker).sort("time")
            if ticker_prices.is_empty():
                logger.warning("No price history returned for %s", ticker)
                continue
            ticker_features = self.feature_engine.calculate_all_features(ticker_prices)
            latest_feature_rows.append(ticker_features.tail(1))

        if not latest_feature_rows:
            logger.warning("No per-symbol features calculated")
            return []

        features_df = pl.concat(latest_feature_rows, how="diagonal_relaxed")

        benchmark_rows = features_df.filter(pl.col("ticker") == self.benchmark_ticker)
        benchmark_return = (
            benchmark_rows["roc_60"][0]
            if benchmark_rows.height and benchmark_rows["roc_60"][0] is not None
            else None
        )
        if benchmark_return is None:
            features_df = features_df.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("relative_strength_spy")
            )
        else:
            features_df = features_df.with_columns(
                (pl.col("roc_60") - float(benchmark_return)).alias("relative_strength_spy")
            )

        features_df = features_df.filter(pl.col("ticker").is_in(scan_tickers))

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

    def get_provider_status(self) -> Dict[str, Any]:
        """Describe the configured provider and the source used by the latest request."""
        status_method = getattr(self.data_provider, "status", None)
        if callable(status_method):
            status = status_method()
        else:
            source_name = getattr(self.data_provider, "source_name", self.data_provider.__class__.__name__)
            status = {
                "configured_provider": source_name,
                "active_source": source_name,
                "fallback_source": None,
                "last_error": None,
                "default_universe_size": len(
                    self.data_provider.get_stock_universe_sync(
                        min_price=self.scanner.min_price,
                        min_volume=self.scanner.min_avg_volume,
                        min_market_cap=self.scanner.min_market_cap,
                    )
                ),
                "live_market_data": not str(source_name).lower().startswith("mock"),
            }

        capabilities = self.data_provider.capabilities
        integrity = evaluate_research_integrity(
            capabilities,
            str(status["configured_provider"]),
            "CURRENT_SCANNER_UNIVERSE",
            uses_current_constituents=True,
        )
        status["capabilities"] = capabilities.to_dict()
        status["research_integrity"] = integrity.to_dict()
        return status

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
