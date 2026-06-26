"""Prometheus metrics for the Phase 3 analysis engine.

Defines all Prometheus counters, gauges, and histograms consumed by the
technical-indicator pipeline, volume analysis, depth analysis, and the
unified analysis pipeline.

Design rules (per SBITB contract):
- structlog for all logging; no print() in src/
- Decimal for financial paths (not applicable here — metrics are int/float observability)
- No naive datetime — not used in metrics module
- Function size ≤50 LOC each
- prometheus_client ≥0.21.0 required (declared in pyproject.toml)

References:
- Prometheus best practices: https://prometheus.io/docs/practices/naming/
- Easley/Lopez de Prado/O'Hara (2012): VPIN methodology
- Kaufman Ch.2-8: Signal design, indicator construction
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

# ---------------------------------------------------------------------------
# Build / version info (observability best-practice)
# ---------------------------------------------------------------------------

ANALYSIS_BUILD_INFO = Info(
    "analysis_engine",
    "Analysis engine build/version metadata",
)

# ---------------------------------------------------------------------------
# Technical indicator pipeline
# ---------------------------------------------------------------------------

TA_INDICATORS_COMPUTED = Counter(
    "ta_indicators_computed_total",
    "Number of technical indicator computations",
    ["status"],  # status: success, error
)

TA_COMPUTE_LATENCY = Histogram(
    "ta_compute_latency_seconds",
    "Technical indicator pipeline latency",
    buckets=[0.0005, 0.001, 0.002, 0.005, 0.01, 0.025, 0.05],
)

# ---------------------------------------------------------------------------
# Volume analysis
# ---------------------------------------------------------------------------

VOLUME_PROFILE_COMPUTED = Counter(
    "volume_profile_computed_total",
    "Volume profile computations",
    ["status"],  # status: success, error
)

VSA_SIGNALS_DETECTED = Counter(
    "vsa_signals_detected_total",
    "VSA signals detected by type",
    ["signal_type"],  # Maps to VSASignalType enum values
)

VOLUME_ANOMALIES_DETECTED = Counter(
    "volume_anomalies_detected_total",
    "Volume anomalies detected",
)

# ---------------------------------------------------------------------------
# Depth analysis
# ---------------------------------------------------------------------------

DEPTH_ANALYSIS_COMPUTED = Counter(
    "depth_analysis_computed_total",
    "Depth analysis computations",
    ["status"],  # status: success, error
)

VPIN_COMPUTED = Counter(
    "vpin_computed_total",
    "VPIN computations",
    ["level"],  # NORMAL, ELEVATED, HIGH, EXTREME
)

# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

ANALYSIS_PIPELINE_LATENCY = Histogram(
    "analysis_pipeline_latency_seconds",
    "Full analysis pipeline latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)

ANALYSIS_PIPELINE_TOTAL = Counter(
    "analysis_pipeline_total",
    "Total analysis pipeline runs",
    ["status"],  # status: success, error, partial
)

# ---------------------------------------------------------------------------
# Market regime
# ---------------------------------------------------------------------------

MARKET_REGIME_GAUGE = Gauge(
    "market_regime",
    "Current market regime",
    ["regime"],  # TRENDING, MEAN_REVERTING, RANDOM_WALK
)

# ---------------------------------------------------------------------------
# Valid label constants — prevents typos at call sites
# ---------------------------------------------------------------------------

VALID_METRIC_STATUSES: frozenset[str] = frozenset({"success", "error", "partial"})
VALID_VPIN_LEVELS: frozenset[str] = frozenset({"NORMAL", "ELEVATED", "HIGH", "EXTREME"})
VALID_MARKET_REGIMES: frozenset[str] = frozenset({"TRENDING", "MEAN_REVERTING", "RANDOM_WALK"})
VALID_VSA_SIGNAL_TYPES: frozenset[str] = frozenset(
    {
        "DEMAND_BAR",
        "NO_SUPPLY",
        "STOPPING_VOLUME",
        "CLIMACTIC_SELL",
        "SUPPLY_BAR",
        "NO_DEMAND",
        "EFFORT_VS_RESULT_UP",
        "EFFORT_VS_RESULT_DOWN",
        "CLIMACTIC_BUY",
    }
)


# ---------------------------------------------------------------------------
# Safe metric helpers — validate label values before incrementing
# ---------------------------------------------------------------------------


def record_ta_computation(status: str, latency_seconds: float) -> None:
    """Record a technical indicator computation with latency.

    Args:
        status: Must be one of VALID_METRIC_STATUSES.
        latency_seconds: Wall-clock time of the computation.

    Raises:
        ValueError: If status is not a valid label.
    """
    if status not in VALID_METRIC_STATUSES:
        msg = f"Invalid TA status label: {status!r}, expected one of {VALID_METRIC_STATUSES}"
        raise ValueError(msg)
    TA_INDICATORS_COMPUTED.labels(status=status).inc()
    TA_COMPUTE_LATENCY.observe(latency_seconds)


def record_volume_profile(status: str) -> None:
    """Record a volume profile computation.

    Args:
        status: Must be one of VALID_METRIC_STATUSES.

    Raises:
        ValueError: If status is not a valid label.
    """
    if status not in VALID_METRIC_STATUSES:
        msg = f"Invalid volume profile status label: {status!r}, expected one of {VALID_METRIC_STATUSES}"
        raise ValueError(msg)
    VOLUME_PROFILE_COMPUTED.labels(status=status).inc()


def record_vsa_signal(signal_type: str) -> None:
    """Record a VSA signal detection.

    Args:
        signal_type: Must be one of VALID_VSA_SIGNAL_TYPES.

    Raises:
        ValueError: If signal_type is not a valid label.
    """
    if signal_type not in VALID_VSA_SIGNAL_TYPES:
        msg = f"Invalid VSA signal type label: {signal_type!r}, expected one of {VALID_VSA_SIGNAL_TYPES}"
        raise ValueError(msg)
    VSA_SIGNALS_DETECTED.labels(signal_type=signal_type).inc()


def record_depth_analysis(status: str) -> None:
    """Record a depth analysis computation.

    Args:
        status: Must be one of VALID_METRIC_STATUSES.

    Raises:
        ValueError: If status is not a valid label.
    """
    if status not in VALID_METRIC_STATUSES:
        msg = f"Invalid depth analysis status label: {status!r}, expected one of {VALID_METRIC_STATUSES}"
        raise ValueError(msg)
    DEPTH_ANALYSIS_COMPUTED.labels(status=status).inc()


def record_vpin(level: str) -> None:
    """Record a VPIN computation with toxicity level.

    Args:
        level: Must be one of VALID_VPIN_LEVELS.

    Raises:
        ValueError: If level is not a valid label.
    """
    if level not in VALID_VPIN_LEVELS:
        msg = f"Invalid VPIN level label: {level!r}, expected one of {VALID_VPIN_LEVELS}"
        raise ValueError(msg)
    VPIN_COMPUTED.labels(level=level).inc()


def record_pipeline_run(status: str, latency_seconds: float) -> None:
    """Record a full analysis pipeline run with latency.

    Args:
        status: Must be one of VALID_METRIC_STATUSES.
        latency_seconds: Wall-clock time of the full pipeline.

    Raises:
        ValueError: If status is not a valid label.
    """
    if status not in VALID_METRIC_STATUSES:
        msg = f"Invalid pipeline status label: {status!r}, expected one of {VALID_METRIC_STATUSES}"
        raise ValueError(msg)
    ANALYSIS_PIPELINE_TOTAL.labels(status=status).inc()
    ANALYSIS_PIPELINE_LATENCY.observe(latency_seconds)


def set_market_regime(regime: str, value: float) -> None:
    """Set the current market regime gauge value.

    Args:
        regime: Must be one of VALID_MARKET_REGIMES.
        value: Gauge value (typically 1.0 for current regime).

    Raises:
        ValueError: If regime is not a valid label.
    """
    if regime not in VALID_MARKET_REGIMES:
        msg = f"Invalid market regime label: {regime!r}, expected one of {VALID_MARKET_REGIMES}"
        raise ValueError(msg)
    MARKET_REGIME_GAUGE.labels(regime=regime).set(value)


# ---------------------------------------------------------------------------
# Module-level exports
# ---------------------------------------------------------------------------

__all__ = [
    # Raw metric objects
    "ANALYSIS_BUILD_INFO",
    "TA_INDICATORS_COMPUTED",
    "TA_COMPUTE_LATENCY",
    "VOLUME_PROFILE_COMPUTED",
    "VSA_SIGNALS_DETECTED",
    "VOLUME_ANOMALIES_DETECTED",
    "DEPTH_ANALYSIS_COMPUTED",
    "VPIN_COMPUTED",
    "ANALYSIS_PIPELINE_LATENCY",
    "ANALYSIS_PIPELINE_TOTAL",
    "MARKET_REGIME_GAUGE",
    # Label validation constants
    "VALID_METRIC_STATUSES",
    "VALID_VPIN_LEVELS",
    "VALID_MARKET_REGIMES",
    "VALID_VSA_SIGNAL_TYPES",
    # Safe metric helpers
    "record_ta_computation",
    "record_volume_profile",
    "record_vsa_signal",
    "record_depth_analysis",
    "record_vpin",
    "record_pipeline_run",
    "set_market_regime",
]
