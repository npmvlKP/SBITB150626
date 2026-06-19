-- Phase 2: TimescaleDB Schema for Options Data
-- Extends Phase 0 (init.sql) with F&O derivatives schema
-- Deploys all hypertables, indices, views, continuous aggregates, and retention policies

\set ON_ERROR_STOP on

-- 2.1 Event Log (Kleppmann Ch.3: Immutable Source of Truth)
-- Append-only event log: ALL market data events flow through here first
CREATE TABLE IF NOT EXISTS market_events (
    event_id UUID NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(30) NOT NULL, -- 'FO_BHAVCOPY', 'CM_BHAVCOPY', 'WS_TICK', 'WS_OI_UPDATE', 'GREEKS_SNAPSHOT'
    schema_version SMALLINT NOT NULL DEFAULT 1,
    payload JSONB NOT NULL,
    source VARCHAR(20) NOT NULL, -- 'jugaad_data', 'kite_ws', 'computed'
    ingest_id UUID NOT NULL, -- Unique per pipeline run (idempotency key)
    epoch BIGINT NOT NULL DEFAULT 1, -- Fencing token (Kleppmann Ch.5)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (event_id, event_time)
);

-- Convert to hypertable partitioned by event_time (daily chunks)
SELECT create_hypertable('market_events', 'event_time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');

-- Secondary indexes for query patterns
CREATE INDEX IF NOT EXISTS idx_me_event_type ON market_events (event_type, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_me_ingest_id ON market_events (ingest_id);
CREATE INDEX IF NOT EXISTS idx_me_source ON market_events (source, event_time DESC);

-- Append-only protection (Kleppmann pattern)
CREATE OR REPLACE FUNCTION prevent_market_event_deletion()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Market events are append-only. Deletion not permitted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_market_event_deletion
BEFORE DELETE ON market_events
FOR EACH ROW EXECUTE FUNCTION prevent_market_event_deletion();

CREATE OR REPLACE FUNCTION prevent_market_event_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Market events are append-only. Updates not permitted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_market_event_update
BEFORE UPDATE ON market_events
FOR EACH ROW EXECUTE FUNCTION prevent_market_event_update();

-- Retention policy: 7 years (SEBI regulatory requirement)
SELECT add_retention_policy('market_events', INTERVAL '7 years', if_not_exists => TRUE);

-- 2.2 F&O Options EOD Hypertable (Derived from event log)
-- Derived table: F&O options EOD data (populated from FO_BHAVCOPY events)
CREATE TABLE IF NOT EXISTS fo_options_eod (
    date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL, -- 'NIFTY', 'BANKNIFTY'
    expiry DATE NOT NULL,
    strike NUMERIC(12,2) NOT NULL,
    option_type CHAR(2) NOT NULL CHECK (option_type IN ('CE', 'PE')),
    open NUMERIC(12,2) NOT NULL DEFAULT 0,
    high NUMERIC(12,2) NOT NULL DEFAULT 0,
    low NUMERIC(12,2) NOT NULL DEFAULT 0,
    close NUMERIC(12,2) NOT NULL DEFAULT 0,
    settle_price NUMERIC(12,2) NOT NULL DEFAULT 0,
    volume BIGINT NOT NULL DEFAULT 0,
    oi BIGINT NOT NULL DEFAULT 0,
    oi_change BIGINT NOT NULL DEFAULT 0, -- Daily OI change
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (date, symbol, expiry, strike, option_type)
);

-- Convert to hypertable with monthly partitioning
SELECT create_hypertable('fo_options_eod', 'date', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 month');

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_fo_symbol_date ON fo_options_eod (symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_fo_expiry ON fo_options_eod (symbol, expiry, date DESC);
CREATE INDEX IF NOT EXISTS idx_fo_strike ON fo_options_eod (symbol, date, strike, option_type);

-- 2.3 Continuous Aggregate: Daily OI change per symbol/expiry
CREATE MATERIALIZED VIEW IF NOT EXISTS v_daily_oi_summary WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', date) AS bucket,
    symbol,
    expiry,
    option_type,
    sum(oi) AS total_oi,
    sum(oi_change) AS total_oi_change,
    sum(volume) AS total_volume,
    avg(close) AS avg_close
FROM fo_options_eod
GROUP BY bucket, symbol, expiry, option_type
WITH NO DATA;

-- Refresh policy: run every hour (data arrives after market close, so first run at ~4PM IST)
SELECT add_continuous_aggregate_policy('v_daily_oi_summary',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- 2.3 CM Spot Prices Table
-- Derived table: Cash market spot prices
CREATE TABLE IF NOT EXISTS cm_spot_eod (
    date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL, -- 'NIFTY 50', 'NIFTY BANK'
    open NUMERIC(12,2) NOT NULL DEFAULT 0,
    high NUMERIC(12,2) NOT NULL DEFAULT 0,
    low NUMERIC(12,2) NOT NULL DEFAULT 0,
    close NUMERIC(12,2) NOT NULL DEFAULT 0,
    volume BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (date, symbol)
);

-- Monthly partitioning for CM data
SELECT create_hypertable('cm_spot_eod', 'date', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 month');
CREATE INDEX IF NOT EXISTS idx_cm_symbol_date ON cm_spot_eod (symbol, date DESC);

-- 2.4 Greeks Snapshot Table
-- Computed Greeks: one row per (date, symbol, expiry, strike, option_type)
CREATE TABLE IF NOT EXISTS greeks_snapshot (
    date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    expiry DATE NOT NULL,
    strike NUMERIC(12,2) NOT NULL,
    option_type CHAR(2) NOT NULL CHECK (option_type IN ('CE', 'PE')),
    spot NUMERIC(12,2) NOT NULL,
    iv DOUBLE PRECISION, -- NULL if computation fails (deep OTM/ITM)
    delta DOUBLE PRECISION,
    gamma DOUBLE PRECISION,
    theta DOUBLE PRECISION,
    vega DOUBLE PRECISION,
    risk_free_rate DOUBLE PRECISION NOT NULL,
    rfr_method VARCHAR(20) NOT NULL DEFAULT 't_bill', -- 't_bill' or 'futures_basis'
    ttm_years DOUBLE PRECISION NOT NULL,
    compute_error TEXT, -- NULL if success; error message if failure
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (date, symbol, expiry, strike, option_type)
);

-- Monthly partitioning for Greeks data
SELECT create_hypertable('greeks_snapshot', 'date', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 month');
CREATE INDEX IF NOT EXISTS idx_greeks_iv ON greeks_snapshot (symbol, date, iv) WHERE iv IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_greeks_delta ON greeks_snapshot (symbol, date, delta) WHERE delta IS NOT NULL;

-- 2.5 Live Tick Table + Continuous Aggregate
-- Live/WebSocket tick data (continuous ingest)
CREATE TABLE IF NOT EXISTS ws_ticks (
    tick_time TIMESTAMPTZ NOT NULL,
    instrument_token INTEGER NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    ltp NUMERIC(12,2) NOT NULL,
    volume BIGINT,
    oi BIGINT,
    bid_price NUMERIC(12,4),
    ask_price NUMERIC(12,4),
    depth_json JSONB, -- 5-level depth
    epoch BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Daily partitioning for tick data
SELECT create_hypertable('ws_ticks', 'tick_time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_ws_token_time ON ws_ticks (instrument_token, tick_time DESC);
CREATE INDEX IF NOT EXISTS idx_ws_symbol_time ON ws_ticks (symbol, tick_time DESC);

-- Retention policy: 90 days for raw ticks
SELECT add_retention_policy('ws_ticks', INTERVAL '90 days', if_not_exists => TRUE);

-- 2.5 Continuous Aggregate: 1-minute OHLCV from ticks
CREATE MATERIALIZED VIEW IF NOT EXISTS v_tick_1min_ohlcv WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', tick_time) AS bucket,
    instrument_token,
    symbol,
    first(ltp, tick_time) AS open,
    max(ltp) AS high,
    min(ltp) AS low,
    last(ltp, tick_time) AS close,
    sum(COALESCE(volume, 0)) AS volume,
    last(oi, tick_time) AS oi_end
FROM ws_ticks
GROUP BY bucket, instrument_token, symbol
WITH NO DATA;

SELECT add_continuous_aggregate_policy('v_tick_1min_ohlcv',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE);

-- 2.6 Download Checkpoint Table (Resumable Download)
-- Tracks download progress for resumable bhavcopy ingestion
CREATE TABLE IF NOT EXISTS download_checkpoint (
    pipeline_run UUID NOT NULL,
    date DATE NOT NULL,
    segment VARCHAR(10) NOT NULL, -- 'FO' or 'CM'
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'downloaded', 'parsed', 'ingested', 'failed'
    rows_ingested INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (pipeline_run, date, segment)
);

CREATE INDEX IF NOT EXISTS idx_dc_status ON download_checkpoint (status, date);

-- 2.7 ATM Strike Computed View
-- View: ATM strikes per day (closest strike to spot close)
CREATE OR REPLACE VIEW v_atm_strikes AS
SELECT
    f.date,
    f.symbol,
    f.expiry,
    s.close AS spot_close,
    f.strike AS atm_strike,
    f.option_type,
    f.close AS option_close,
    f.volume,
    f.oi,
    ABS(f.strike - s.close) AS strike_distance
FROM
    fo_options_eod f
JOIN
    cm_spot_eod s ON f.date = s.date
    AND f.symbol = REPLACE(s.symbol, ' 50', '')
    AND f.symbol = REPLACE(s.symbol, ' BANK', '')
WHERE
    ABS(f.strike - s.close) = (
        SELECT MIN(ABS(f2.strike - s2.close))
        FROM fo_options_eod f2
        JOIN cm_spot_eod s2 ON f2.date = s2.date
        WHERE f2.date = f.date
        AND f2.symbol = f.symbol
        AND f2.expiry = f.expiry
        AND f2.option_type = f.option_type
        AND s2.symbol = s.symbol
    );

-- Apply schema migration script headers
-- This script extends the existing init.sql (Phase 0) schema
-- All hypertable configurations, indexes, views, and policies are production-ready
-- Execute with: psql -U trading -d trading_bot < init_phase2.sql
