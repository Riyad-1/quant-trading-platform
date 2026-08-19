-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Create enum for asset status
CREATE TYPE asset_status AS ENUM ('active', 'delisted', 'suspended');

-- Create enum for signal direction
CREATE TYPE signal_direction AS ENUM ('long', 'short', 'neutral');

-- Immutable security master. External identifiers remain NULL unless supplied by a provider.
CREATE TABLE securities (
    id SERIAL PRIMARY KEY,
    security_type VARCHAR(50) NOT NULL DEFAULT 'COMMON_STOCK',
    display_name VARCHAR(255),
    primary_exchange VARCHAR(50),
    currency VARCHAR(10),
    country VARCHAR(10),
    current_status VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN',
    figi VARCHAR(20) UNIQUE,
    composite_figi VARCHAR(20) UNIQUE,
    isin VARCHAR(20) UNIQUE,
    cusip VARCHAR(20) UNIQUE,
    provider_identifiers JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- All effective-dated ranges in Stage C are half-open: [valid_from, valid_to).
CREATE TABLE security_symbols (
    id SERIAL PRIMARY KEY,
    security_id INTEGER NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    exchange VARCHAR(50),
    valid_from DATE NOT NULL,
    valid_to DATE,
    source VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_security_symbol_start UNIQUE (security_id, ticker, exchange, valid_from),
    CONSTRAINT ck_security_symbol_valid_range CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX ix_security_symbols_lookup
    ON security_symbols (ticker, valid_from, valid_to);

CREATE TABLE security_status_history (
    id SERIAL PRIMARY KEY,
    security_id INTEGER NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    source VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_security_status_start UNIQUE (security_id, valid_from),
    CONSTRAINT ck_security_status_valid_range CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX ix_security_status_lookup
    ON security_status_history (security_id, valid_from, valid_to);

CREATE TABLE universe_definitions (
    id SERIAL PRIMARY KEY,
    code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    source VARCHAR(100) NOT NULL,
    methodology JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Explicit validation evidence for an actual historical universe dataset.
-- No rows are seeded: provider capability or membership row count is not proof.
CREATE TABLE historical_universe_coverage (
    id SERIAL PRIMARY KEY,
    universe_id INTEGER NOT NULL REFERENCES universe_definitions(id) ON DELETE CASCADE,
    provider_name VARCHAR(100) NOT NULL,
    coverage_start DATE,
    coverage_end DATE,
    historical_population_verified BOOLEAN NOT NULL DEFAULT false,
    historical_membership_established BOOLEAN NOT NULL DEFAULT false,
    membership_availability_established BOOLEAN NOT NULL DEFAULT false,
    symbol_history_established BOOLEAN NOT NULL DEFAULT false,
    listing_history_established BOOLEAN NOT NULL DEFAULT false,
    delisted_coverage_established BOOLEAN NOT NULL DEFAULT false,
    provenance_known BOOLEAN NOT NULL DEFAULT false,
    source VARCHAR(100) NOT NULL,
    evidence_metadata JSONB,
    warnings JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_historical_universe_coverage_evidence UNIQUE (
        universe_id,
        provider_name,
        source,
        coverage_start,
        coverage_end
    ),
    CONSTRAINT ck_historical_universe_coverage_range CHECK (
        coverage_end IS NULL OR coverage_start IS NULL OR coverage_end >= coverage_start
    )
);

CREATE INDEX ix_historical_universe_coverage_lookup
    ON historical_universe_coverage (universe_id, provider_name);
CREATE INDEX ix_historical_universe_coverage_universe_id
    ON historical_universe_coverage (universe_id);
CREATE INDEX ix_historical_universe_coverage_provider_name
    ON historical_universe_coverage (provider_name);

CREATE TABLE universe_memberships (
    id SERIAL PRIMARY KEY,
    universe_id INTEGER NOT NULL REFERENCES universe_definitions(id) ON DELETE CASCADE,
    security_id INTEGER NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    valid_from DATE NOT NULL,
    valid_to DATE,
    source VARCHAR(100) NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_universe_membership_start UNIQUE (universe_id, security_id, valid_from),
    CONSTRAINT ck_universe_membership_valid_range CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX ix_universe_membership_lookup
    ON universe_memberships (universe_id, valid_from, valid_to);

CREATE TABLE corporate_actions (
    id SERIAL PRIMARY KEY,
    security_id INTEGER NOT NULL REFERENCES securities(id) ON DELETE CASCADE,
    action_type VARCHAR(30) NOT NULL,
    event_date DATE,
    effective_date DATE NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE,
    source VARCHAR(100) NOT NULL,
    source_event_id VARCHAR(200),
    action_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_corporate_action_source_event UNIQUE (source, source_event_id)
);

CREATE INDEX ix_corporate_actions_security_date
    ON corporate_actions (security_id, effective_date);

-- Assets table (stocks, ETFs)
CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    security_id INTEGER REFERENCES securities(id) ON DELETE SET NULL,
    ticker VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255),
    exchange VARCHAR(50),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    status asset_status DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_assets_security_id ON assets (security_id);

-- Create hypertable for daily prices
CREATE TABLE prices_daily (
    time TIMESTAMPTZ NOT NULL,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    open NUMERIC(18, 6),
    high NUMERIC(18, 6),
    low NUMERIC(18, 6),
    close NUMERIC(18, 6),
    volume BIGINT,
    adjusted_close NUMERIC(18, 6),
    dollar_volume NUMERIC(24, 6),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (asset_id, time)
);

SELECT create_hypertable('prices_daily', 'time');

-- Create indexes for common queries
CREATE INDEX idx_prices_daily_asset_time ON prices_daily (asset_id, time DESC);
CREATE INDEX idx_prices_daily_time ON prices_daily (time DESC);

-- Features table (hypertable for time-series features)
CREATE TABLE features_daily (
    time TIMESTAMPTZ NOT NULL,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    feature_name VARCHAR(100) NOT NULL,
    feature_value NUMERIC(18, 8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (asset_id, time, feature_name)
);

SELECT create_hypertable('features_daily', 'time');

CREATE INDEX idx_features_daily_asset_time ON features_daily (asset_id, time DESC);
CREATE INDEX idx_features_daily_name ON features_daily (feature_name);

-- Market regimes table
CREATE TABLE market_regimes (
    date DATE PRIMARY KEY,
    regime_label VARCHAR(50) NOT NULL,
    confidence NUMERIC(5, 4),
    metrics_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- News events table
CREATE TABLE news_events (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
    published_at TIMESTAMPTZ NOT NULL,
    headline TEXT,
    summary TEXT,
    source VARCHAR(100),
    url TEXT,
    llm_sentiment NUMERIC(5, 4),
    llm_importance NUMERIC(5, 4),
    llm_catalysts JSONB,
    llm_explanation TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_news_events_asset_time ON news_events (asset_id, published_at DESC);
CREATE INDEX idx_news_events_time ON news_events (published_at DESC);

-- Strategies table
CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    version VARCHAR(20) DEFAULT '1.0.0',
    parameters JSONB,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Signals table (generated by strategies/models)
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    strategy_id INTEGER REFERENCES strategies(id),
    model_version VARCHAR(50),
    score NUMERIC(8, 4),
    direction signal_direction,
    suggested_entry NUMERIC(18, 6),
    suggested_stop NUMERIC(18, 6),
    suggested_target NUMERIC(18, 6),
    expected_return NUMERIC(8, 6),
    confidence VARCHAR(20),
    explanation TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_signals_asset_time ON signals (asset_id, generated_at DESC);
CREATE INDEX idx_signals_time ON signals (generated_at DESC);
CREATE INDEX idx_signals_score ON signals (score DESC);

-- Paper portfolio table
CREATE TABLE paper_portfolio (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) DEFAULT 'Default Portfolio',
    initial_cash NUMERIC(18, 2) NOT NULL,
    current_cash NUMERIC(18, 2),
    total_equity NUMERIC(18, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Paper positions table
CREATE TABLE paper_positions (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    quantity NUMERIC(18, 6) NOT NULL,
    entry_price NUMERIC(18, 6) NOT NULL,
    entry_date TIMESTAMPTZ NOT NULL,
    exit_price NUMERIC(18, 6),
    exit_date TIMESTAMPTZ,
    stop_loss NUMERIC(18, 6),
    target_price NUMERIC(18, 6),
    status VARCHAR(20) DEFAULT 'open',
    pnl_realized NUMERIC(18, 2),
    strategy_id INTEGER REFERENCES strategies(id),
    signal_id INTEGER REFERENCES signals(id),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_paper_positions_portfolio ON paper_positions (portfolio_id);
CREATE INDEX idx_paper_positions_status ON paper_positions (status);

-- Portfolio snapshots (daily equity curve)
CREATE TABLE portfolio_snapshots (
    time TIMESTAMPTZ NOT NULL,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id) ON DELETE CASCADE,
    cash NUMERIC(18, 2),
    equity NUMERIC(18, 2),
    unrealized_pnl NUMERIC(18, 2),
    realized_pnl NUMERIC(18, 2),
    exposure NUMERIC(8, 4),
    PRIMARY KEY (portfolio_id, time)
);

SELECT create_hypertable('portfolio_snapshots', 'time');

-- Models table (ML models)
CREATE TABLE models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    model_type VARCHAR(50),
    version VARCHAR(20) NOT NULL,
    training_start_date DATE,
    training_end_date DATE,
    test_start_date DATE,
    test_end_date DATE,
    metrics_json JSONB,
    feature_list TEXT[],
    model_path VARCHAR(255),
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Experiments table (for research tracking)
CREATE TABLE experiments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    hypothesis TEXT,
    parameters JSONB,
    results_json JSONB,
    status VARCHAR(20) DEFAULT 'running',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Insert default SPY asset for benchmarking
INSERT INTO assets (ticker, name, exchange, sector, industry, status)
VALUES ('SPY', 'SPDR S&P 500 ETF Trust', 'ARCA', 'ETF', 'Broad Market', 'active')
ON CONFLICT (ticker) DO NOTHING;

-- Insert default QQQ asset
INSERT INTO assets (ticker, name, exchange, sector, industry, status)
VALUES ('QQQ', 'Invesco QQQ Trust', 'NASDAQ', 'ETF', 'Technology', 'active')
ON CONFLICT (ticker) DO NOTHING;

-- Insert default portfolio
INSERT INTO paper_portfolio (name, initial_cash, current_cash, total_equity)
VALUES ('Paper Trading Portfolio', 100000.00, 100000.00, 100000.00);
