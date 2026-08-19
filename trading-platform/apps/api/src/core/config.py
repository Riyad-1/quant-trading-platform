from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Quant Trading Platform"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql://quantuser:quantpassword@localhost:5432/quantdb"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Data providers (abstracted, can be changed)
    ALPHA_VANTAGE_API_KEY: str | None = None
    POLYGON_API_KEY: str | None = None
    ALPACA_API_KEY: str | None = None
    FRED_API_KEY: str | None = None

    # OpenBB market data service
    SCANNER_DATA_PROVIDER: str = "openbb"
    OPENBB_BASE_URL: str = "http://localhost:6900"
    OPENBB_PRICE_PROVIDER: str = "yfinance"
    SCANNER_DEFAULT_TICKERS: str = (
        "AAPL,MSFT,NVDA,AMZN,META,GOOGL,AVGO,TSLA,JPM,LLY,XOM,COST,UNH,HD,PG"
    )
    SCANNER_LOOKBACK_DAYS: int = 400
    SCANNER_BENCHMARK_TICKER: str = "SPY"

    # LLM for news analysis
    OPENAI_API_KEY: str | None = None

    # Backtesting
    DEFAULT_INITIAL_CAPITAL: float = 100000.0
    TRANSACTION_COST_BPS: float = 5.0  # 0.05% per trade
    SLIPPAGE_BPS: float = 5.0

    # Risk management
    MAX_POSITION_SIZE_PCT: float = 0.10  # 10% max per position
    MAX_SECTOR_EXPOSURE_PCT: float = 0.30  # 30% max per sector
    MAX_PORTFOLIO_DRAWDOWN: float = 0.15  # 15% max drawdown

    # Liquidity filters (small account compatible)
    MIN_STOCK_PRICE: float = 5.0
    MIN_AVG_DOLLAR_VOLUME: float = 20_000_000  # $20M daily

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
