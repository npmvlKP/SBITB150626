"""
Prometheus metrics for Phase 2 F&O data pipeline.

Defines counters, gauges, and histograms for monitoring:
- Historical bhavcopy download pipeline
- Live WebSocket tick ingestion
- TimescaleDB storage operations
- Risk-free rate computations
"""

from prometheus_client import Counter, Gauge, Histogram

# =============================================================================
# Historical pipeline metrics
# =============================================================================

DOWNLOAD_ATTEMPTS = Counter("pipeline_download_attempts_total", "Bhavcopy download attempts", ["segment", "status"])

DOWNLOAD_ROWS = Counter("pipeline_download_rows_total", "Rows ingested from bhavcopies", ["segment"])

GREEKS_COMPUTED = Counter(
    "pipeline_greeks_computed_total",
    "Greeks computations",
    ["symbol", "status"],  # status: success/failed
)

# =============================================================================
# Live pipeline metrics
# =============================================================================

WS_RECONNECTS = Counter("ws_reconnects_total", "WebSocket reconnections")

WS_TICKS_RECEIVED = Counter("ws_ticks_received_total", "Ticks received from WebSocket")

WS_TICKS_DROPPED = Counter("ws_ticks_dropped_total", "Ticks dropped due to backpressure")

WS_PERSIST_LAG = Histogram("ws_persist_lag_seconds", "Time between tick receipt and DB persist")

WS_PERSIST_ROWS = Counter("ws_persist_rows_total", "Ticks persisted to TimescaleDB")

# =============================================================================
# Storage metrics
# =============================================================================

DB_WRITE_LATENCY = Histogram("db_write_latency_seconds", "TimescaleDB write latency", ["table"])

DB_QUERY_LATENCY = Histogram("db_query_latency_seconds", "TimescaleDB query latency", ["table"])

REDIS_HIT_RATE = Gauge("redis_hit_rate", "Redis cache hit rate")

# =============================================================================
# Risk-free rate metrics
# =============================================================================

RFR_COMPUTED = Counter("rfr_computed_total", "Risk-free rate computations", ["method", "status"])
