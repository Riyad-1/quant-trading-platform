"""Scanner API endpoints - Provides REST API access to the stock scanner functionality."""

import asyncio

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime

from services.scanner.scanner_service import ScannerService
from services.scanner.scanner_engine import StockScore, SetupType
from services.data.providers.mock_provider import MockMarketDataProvider
from services.data.providers.openbb_provider import OpenBBMarketDataProvider
from services.data.providers.yfinance_provider import YFinanceMarketDataProvider
from services.features.engine import FeatureEngine
from apps.api.src.core.config import get_settings

router = APIRouter(tags=["scanner"])


# Response Models
class StockScoreResponse(BaseModel):
    """API response model for a scored stock"""
    ticker: str
    company_name: str
    sector: str
    industry: str
    price: float
    composite_score: float
    momentum_score: float
    breakout_score: float
    relative_strength_score: float
    volume_score: float
    fundamentals_score: float
    market_compatibility_score: float
    setup_type: str
    confidence: str
    rank: int
    timestamp: datetime

    class Config:
        from_attributes = True


class ScanSummaryResponse(BaseModel):
    """API response model for scan summary"""
    total_opportunities: int
    average_score: float
    top_score: float
    setup_breakdown: Dict[str, int]
    sector_breakdown: Dict[str, int]
    confidence_breakdown: Dict[str, int]
    timestamp: str


class ScannerConfigRequest(BaseModel):
    """Request model for customizing scanner weights"""
    momentum_weight: float = Field(default=0.30, ge=0, le=1)
    breakout_weight: float = Field(default=0.20, ge=0, le=1)
    relative_strength_weight: float = Field(default=0.25, ge=0, le=1)
    volume_weight: float = Field(default=0.15, ge=0, le=1)
    fundamentals_weight: float = Field(default=0.00, ge=0, le=1)
    market_compatibility_weight: float = Field(default=0.10, ge=0, le=1)
    min_price: float = Field(default=5.0, gt=0)
    min_avg_volume: int = Field(default=200000, gt=0)
    min_market_cap: int = Field(default=300000000, gt=0)


class ScannerProviderResponse(BaseModel):
    """Current scanner market-data source and fallback state."""

    configured_provider: str
    active_source: str
    fallback_source: Optional[str] = None
    openbb_data_provider: Optional[str] = None
    openbb_url: Optional[str] = None
    last_error: Optional[str] = None
    default_universe_size: int
    live_market_data: bool


# Initialize scanner service (in production, this would come from dependency injection)
_scanner_service: Optional[ScannerService] = None


def _configured_tickers() -> List[str]:
    settings = get_settings()
    return list(
        dict.fromkeys(
            ticker.strip().upper()
            for ticker in settings.SCANNER_DEFAULT_TICKERS.split(",")
            if ticker.strip()
        )
    )


def _build_data_provider():
    settings = get_settings()
    universe = _configured_tickers()
    provider_name = settings.SCANNER_DATA_PROVIDER.strip().lower()

    if provider_name == "mock":
        return MockMarketDataProvider()

    direct_yfinance = YFinanceMarketDataProvider(
        universe=universe,
        lookback_days=settings.SCANNER_LOOKBACK_DAYS,
    )
    if provider_name == "yfinance":
        return direct_yfinance
    if provider_name == "openbb":
        return OpenBBMarketDataProvider(
            base_url=settings.OPENBB_BASE_URL,
            provider=settings.OPENBB_PRICE_PROVIDER,
            universe=universe,
            lookback_days=settings.SCANNER_LOOKBACK_DAYS,
            fallback=direct_yfinance,
        )
    raise ValueError(
        "SCANNER_DATA_PROVIDER must be one of: openbb, yfinance, mock"
    )


def _new_scanner_service(scanner_config: Optional[Dict[str, Any]] = None) -> ScannerService:
    settings = get_settings()
    return ScannerService(
        data_provider=_build_data_provider(),
        feature_engine=FeatureEngine(),
        scanner_config=scanner_config,
        benchmark_ticker=settings.SCANNER_BENCHMARK_TICKER,
    )


def get_scanner_service() -> ScannerService:
    """Get or create scanner service instance"""
    global _scanner_service
    if _scanner_service is None:
        _scanner_service = _new_scanner_service()
    return _scanner_service


@router.get("/scanner/provider", response_model=ScannerProviderResponse)
async def get_scanner_provider():
    """Report whether scans are using OpenBB or the direct fallback."""
    return get_scanner_service().get_provider_status()


@router.get("/scanner/scan", response_model=List[StockScoreResponse])
async def run_scan(
    top_n: int = Query(default=50, ge=1, le=500, description="Number of top opportunities to return"),
    tickers: Optional[str] = Query(default=None, description="Comma-separated list of specific tickers"),
    use_cached_features: bool = Query(default=True, description="Use cached features if available")
):
    """Run a full stock scan and return ranked opportunities."""
    try:
        scanner_service = get_scanner_service()

        # Parse tickers if provided
        ticker_list = None
        if tickers:
            ticker_list = [t.strip().upper() for t in tickers.split(",")]

        results = await asyncio.to_thread(
            scanner_service.run_scan,
            tickers=ticker_list,
            top_n=top_n,
            use_cached_features=use_cached_features,
        )

        if not results:
            raise HTTPException(status_code=404, detail="No opportunities found")

        return results

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")


@router.get("/scanner/opportunities/top", response_model=List[StockScoreResponse])
async def get_top_opportunities(
    n: int = Query(default=10, ge=1, le=50, description="Number of top opportunities")
):
    """Get the top N opportunities from the last scan."""
    scanner_service = get_scanner_service()
    results = scanner_service.get_top_opportunities(n=n)

    if not results:
        raise HTTPException(status_code=404, detail="No scan results available. Run /scanner/scan first.")

    return results


@router.get("/scanner/opportunities/{ticker}", response_model=StockScoreResponse)
async def get_opportunity_by_ticker(ticker: str):
    """Get scan result for a specific ticker."""
    scanner_service = get_scanner_service()
    result = scanner_service.get_opportunity_by_ticker(ticker.upper())

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No scan result found for {ticker}. Run /scanner/scan first."
        )

    return result


@router.get("/scanner/summary", response_model=ScanSummaryResponse)
async def get_scan_summary():
    """Get summary statistics of the last scan."""
    scanner_service = get_scanner_service()
    summary = scanner_service.get_scan_summary()

    if summary.get("status") == "no_scan_run":
        raise HTTPException(status_code=404, detail="No scan results available. Run /scanner/scan first.")

    return summary


@router.get("/scanner/filter/setup-type", response_model=List[StockScoreResponse])
async def filter_by_setup_type(
    setup_type: str = Query(..., description="Setup type to filter by"),
    min_score: float = Query(default=0.0, ge=0, le=100, description="Minimum composite score")
):
    """Filter scan results by setup type."""
    try:
        setup_enum = SetupType(setup_type.lower())
    except ValueError:
        valid_types = [t.value for t in SetupType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid setup type. Valid types: {valid_types}"
        )

    scanner_service = get_scanner_service()
    results = scanner_service.filter_by_setup_type(setup_enum, min_score=min_score)

    if not results:
        raise HTTPException(status_code=404, detail="No results match the filter criteria")

    return results


@router.get("/scanner/filter/sector", response_model=List[StockScoreResponse])
async def filter_by_sector(
    sector: str = Query(..., description="Sector name to filter by"),
    min_score: float = Query(default=0.0, ge=0, le=100, description="Minimum composite score")
):
    """Filter scan results by sector."""
    scanner_service = get_scanner_service()
    results = scanner_service.filter_by_sector(sector, min_score=min_score)

    if not results:
        raise HTTPException(status_code=404, detail="No results match the filter criteria")

    return results


@router.post("/scanner/config")
async def update_scanner_config(config: ScannerConfigRequest):
    """Update scanner configuration (weights and filters)."""
    global _scanner_service

    config_dict = config.model_dump()

    # Recreate the scanner while preserving the configured real-data provider.
    _scanner_service = _new_scanner_service(scanner_config=config_dict)

    return {"status": "success", "message": "Scanner configuration updated"}


@router.delete("/scanner/cache")
async def clear_cache():
    """Clear cached scan results."""
    scanner_service = get_scanner_service()
    scanner_service.clear_cache()

    return {"status": "success", "message": "Cache cleared"}
