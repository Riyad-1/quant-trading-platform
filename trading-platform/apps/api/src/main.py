"""FastAPI application main entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .api.v1 import assets, backtest, health, ml, news, paper, portfolio, regime, scanner, strategies


settings = get_settings()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Quantitative Stock Trading Research Platform"
)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routers
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(assets.router, prefix="/api/v1/assets", tags=["Assets"])
app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
app.include_router(strategies.router, prefix="/api/v1/strategies", tags=["Strategies"])
app.include_router(scanner.router, prefix="/api/v1", tags=["Scanner"])
app.include_router(regime.router, prefix="/api/v1", tags=["Market Regime"])
app.include_router(news.router, prefix="/api/v1", tags=["News & Catalysts"])
app.include_router(backtest.router, prefix="/api/v1", tags=["Backtesting"])
app.include_router(ml.router, prefix="/api/v1", tags=["Machine Learning"])
app.include_router(paper.router, prefix="/api/v1", tags=["Paper Trading"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
