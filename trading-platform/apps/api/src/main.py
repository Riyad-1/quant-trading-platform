"""FastAPI application main entry point."""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import get_settings
from .core.database import engine, Base
from .api.v1 import assets, health, portfolio, strategies, scanner, regime, news

# Import all models to ensure they're registered with Base
from .db import models  # noqa: F401
from .db.models_news import NewsSource, NewsArticle, TickerNewsLink, NewsEvent, CatalystScore  # noqa: F401


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: Create tables if they don't exist
    print("Starting up Quant Trading Platform API...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created/verified")

    yield

    # Shutdown
    print("Shutting down Quant Trading Platform API...")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Quantitative Stock Trading Research Platform",
    lifespan=lifespan
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