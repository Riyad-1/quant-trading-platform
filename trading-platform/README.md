# Quantitative Stock Trading Research Platform

## Overview

A full-stack quantitative stock trading research platform with AI assistance. This system continuously analyzes the market, identifies promising trading opportunities, explains why they are attractive, backtests strategies historically, and tracks whether strategies can outperform the S&P 500 on a risk-adjusted basis.

**Version:** 0.1.0 (Phase 1 - Foundation)

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Next.js UI    │────▶│   FastAPI       │────▶│   PostgreSQL    │
│   (Port 3000)   │     │   (Port 8000)   │     │   + TimescaleDB │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
             ┌─────────────┐     ┌─────────────────┐
             │ OpenBB REST │     │   Redis         │
             │ (Port 6900) │     │   (Port 6379)   │
             └─────────────┘     └─────────────────┘
                                      │
                                      ▼
                        ┌─────────────────┐
                        │   Celery Worker │
                        └─────────────────┘
```

## Technology Stack

- **Frontend:** Next.js 14, React, TypeScript, Tailwind CSS
- **Backend:** Python 3.11, FastAPI
- **Database:** PostgreSQL 16 with TimescaleDB extension
- **Cache/Queue:** Redis 7
- **Data Processing:** Polars, NumPy, Pandas
- **Market Data Gateway:** OpenBB with direct yfinance fallback
- **ML:** Scikit-Learn, LightGBM, XGBoost
- **Backtesting:** VectorBT
- **Task Queue:** Celery

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Git

### Installation

1. **Clone the repository**
   ```bash
   cd trading-platform
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys if needed
   ```

3. **Start all services**
   ```bash
   docker-compose up -d
   ```

4. **Verify services are running**
   ```bash
   docker-compose ps
   ```

5. **Access the services**
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Frontend: http://localhost:3000
   - OpenBB API: http://localhost:6900/docs
   - PostgreSQL: localhost:5432
   - Redis: localhost:6379

### Development

#### View logs
```bash
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f web
```

#### Run database migrations
```bash
docker-compose exec api alembic upgrade head
```

#### Run tests
```bash
docker-compose exec api pytest
```

#### Stop services
```bash
docker-compose down
```

#### Stop and remove all data
```bash
docker-compose down -v
```

## Project Structure

```
trading-platform/
├── apps/
│   ├── api/                 # FastAPI backend
│   │   ├── src/
│   │   │   ├── core/        # Config, database
│   │   │   ├── api/v1/      # API endpoints
│   │   │   ├── db/          # Models, schemas
│   │   │   └── main.py      # App entry point
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── web/                 # Next.js frontend
│       └── src/
├── services/                # Core quant logic
│   ├── data/                # Data providers
│   ├── features/            # Feature engineering
│   ├── strategies/          # Trading strategies
│   ├── models/              # ML models
│   ├── risk/                # Risk management
│   └── backtesting/         # Backtesting engine
├── workers/                 # Celery tasks
│   ├── celery_app.py
│   ├── tasks_data.py
│   ├── tasks_features.py
│   └── tasks_ml.py
├── database/
│   └── init.sql             # Database schema
├── research/
│   └── notebooks/           # Jupyter notebooks
├── tests/                   # Test suite
├── docker-compose.yml
└── .env.example
```

## API Endpoints (Phase 1)

### Health
- `GET /api/v1/health` - Check API and database health

### Assets
- `GET /api/v1/assets` - List all assets
- `GET /api/v1/assets/{ticker}` - Get asset by ticker
- `POST /api/v1/assets` - Create new asset
- `PUT /api/v1/assets/{ticker}` - Update asset
- `DELETE /api/v1/assets/{ticker}` - Delete asset
- `GET /api/v1/assets/{ticker}/prices` - Get historical prices

### Scanner
- `GET /api/v1/scanner/provider` - Show the configured and currently active data source
- `GET /api/v1/scanner/scan` - Download market history, calculate features, and rank opportunities
- OpenBB's Yahoo Finance connector is preferred; direct `yfinance` is used automatically if the OpenBB service is unavailable
- Both paths use split-and-dividend-adjusted OHLC so fallback does not change scanner price semantics
- The default 15-symbol starter universe is configurable with `SCANNER_DEFAULT_TICKERS`

### Portfolio
- `GET /api/v1/portfolio` - List portfolios
- `GET /api/v1/portfolio/{id}` - Get portfolio
- `POST /api/v1/portfolio` - Create portfolio
- `GET /api/v1/portfolio/{id}/positions` - Get positions
- `GET /api/v1/portfolio/{id}/snapshots` - Get equity curve

### Strategies
- `GET /api/v1/strategies` - List strategies
- `GET /api/v1/strategies/{id}` - Get strategy
- `POST /api/v1/strategies` - Create strategy
- `PUT /api/v1/strategies/{id}` - Update strategy
- `DELETE /api/v1/strategies/{id}` - Delete strategy
- `GET /api/v1/strategies/{id}/signals` - Get signals

## Database Schema

Key tables:
- `assets` - Stock/ETF metadata
- `prices_daily` - Daily OHLCV (TimescaleDB hypertable)
- `features_daily` - Calculated features (TimescaleDB hypertable)
- `market_regimes` - Market regime classifications
- `news_events` - News with LLM analysis
- `strategies` - Trading strategy definitions
- `signals` - Generated trading signals
- `paper_portfolio` - Paper trading portfolios
- `paper_positions` - Portfolio positions
- `portfolio_snapshots` - Daily equity snapshots
- `models` - ML model registry
- `experiments` - Research experiments

## Development Phases

### Phase 1: Foundation (Current)
- ✅ Project architecture
- ✅ Database schema with TimescaleDB
- ✅ FastAPI backend setup
- ✅ Basic CRUD endpoints
- ✅ Celery worker setup
- ⏳ Next.js frontend
- ⏳ Data ingestion pipeline

### Phase 2: Quant Scanner
- Technical indicators
- Relative strength calculations
- Stock ranking system
- Opportunity scanner UI

### Phase 3: Backtesting
- VectorBT integration
- Strategy backtesting
- SPY benchmarking
- Performance metrics

### Phase 4: Market Regime
- Regime detection
- Market dashboard
- Strategy compatibility

### Phase 5: News AI
- News ingestion
- LLM sentiment analysis
- Catalyst detection

### Phase 6: Machine Learning
- Feature dataset creation
- Model training pipeline
- Walk-forward validation
- Signal generation

### Phase 7: Paper Trading
- Execution simulation
- Portfolio tracking
- Performance analytics

## Important Notes

1. **No Look-Ahead Bias:** All feature calculations and ML predictions must only use data available at prediction time.

2. **Benchmark Against SPY:** Every strategy is compared against SPY buy-and-hold.

3. **Risk Management First:** The risk engine always overrides prediction models.

4. **Explainability:** Every signal must include an explanation of why it was generated.

5. **Version Tracking:** All models and strategies are versioned for audit trails.

## License

Private - All rights reserved

## Contributing

This is a private project. Contact the maintainer for access.
