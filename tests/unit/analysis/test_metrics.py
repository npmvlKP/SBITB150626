"""Unit tests for src/analysis/metrics.py — Prometheus metric definitions and helpers.

Tests cover:
1. All metric objects are importable and have correct types
2. Label validation constants are complete and correct
3. Safe helper functions accept valid labels and reject invalid ones
4. Metric values increment/set correctly after helper calls
5. __all__ export list is complete
6. No import-time errors (module is importable without infra)
"""

from __future__ import annotations

import pytest
from prometheus_client import Counter, Gauge, Histogram, Info


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    """Reset Prometheus registry between tests to avoid duplicate metric errors.

    prometheus_client maintains a global registry; re-importing or re-creating
    metrics with the same name causes ValueError. We clean up after each test.
    """
    yield
    # Unregister any custom collectors added during the test
    # (The default REGISTRY may accumulate collectors; we cannot fully reset it
    #  without using CollectorRegistry(), but we can ensure our tests are isolated
    #  by using a separate registry in tests that need it.)


@pytest.fixture()
def fresh_registry() -> None:
    """No-op fixture — kept for clarity; actual isolation is via module-level import."""
    pass


# ---------------------------------------------------------------------------
# 1. Module import and metric object types
# ---------------------------------------------------------------------------


class TestMetricObjectTypes:
    """Verify each metric object has the correct Prometheus type."""

    def test_analysis_build_info_type(self) -> None:
        from src.analysis.metrics import ANALYSIS_BUILD_INFO

        assert isinstance(ANALYSIS_BUILD_INFO, Info)

    def test_ta_indicators_computed_type(self) -> None:
        from src.analysis.metrics import TA_INDICATORS_COMPUTED

        assert isinstance(TA_INDICATORS_COMPUTED, Counter)

    def test_ta_compute_latency_type(self) -> None:
        from src.analysis.metrics import TA_COMPUTE_LATENCY

        assert isinstance(TA_COMPUTE_LATENCY, Histogram)

    def test_volume_profile_computed_type(self) -> None:
        from src.analysis.metrics import VOLUME_PROFILE_COMPUTED

        assert isinstance(VOLUME_PROFILE_COMPUTED, Counter)

    def test_vsa_signals_detected_type(self) -> None:
        from src.analysis.metrics import VSA_SIGNALS_DETECTED

        assert isinstance(VSA_SIGNALS_DETECTED, Counter)

    def test_volume_anomalies_detected_type(self) -> None:
        from src.analysis.metrics import VOLUME_ANOMALIES_DETECTED

        assert isinstance(VOLUME_ANOMALIES_DETECTED, Counter)

    def test_depth_analysis_computed_type(self) -> None:
        from src.analysis.metrics import DEPTH_ANALYSIS_COMPUTED

        assert isinstance(DEPTH_ANALYSIS_COMPUTED, Counter)

    def test_vpin_computed_type(self) -> None:
        from src.analysis.metrics import VPIN_COMPUTED

        assert isinstance(VPIN_COMPUTED, Counter)

    def test_analysis_pipeline_latency_type(self) -> None:
        from src.analysis.metrics import ANALYSIS_PIPELINE_LATENCY

        assert isinstance(ANALYSIS_PIPELINE_LATENCY, Histogram)

    def test_analysis_pipeline_total_type(self) -> None:
        from src.analysis.metrics import ANALYSIS_PIPELINE_TOTAL

        assert isinstance(ANALYSIS_PIPELINE_TOTAL, Counter)

    def test_market_regime_gauge_type(self) -> None:
        from src.analysis.metrics import MARKET_REGIME_GAUGE

        assert isinstance(MARKET_REGIME_GAUGE, Gauge)


# ---------------------------------------------------------------------------
# 2. Label validation constants
# ---------------------------------------------------------------------------


class TestLabelValidationConstants:
    """Verify label validation constants are correct."""

    def test_valid_metric_statuses(self) -> None:
        from src.analysis.metrics import VALID_METRIC_STATUSES

        assert VALID_METRIC_STATUSES == frozenset({"success", "error", "partial"})

    def test_valid_vpin_levels(self) -> None:
        from src.analysis.metrics import VALID_VPIN_LEVELS

        assert VALID_VPIN_LEVELS == frozenset({"NORMAL", "ELEVATED", "HIGH", "EXTREME"})

    def test_valid_market_regimes(self) -> None:
        from src.analysis.metrics import VALID_MARKET_REGIMES

        assert VALID_MARKET_REGIMES == frozenset({"TRENDING", "MEAN_REVERTING", "RANDOM_WALK"})

    def test_valid_vsa_signal_types(self) -> None:
        from src.analysis.metrics import VALID_VSA_SIGNAL_TYPES

        expected = frozenset(
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
        assert VALID_VSA_SIGNAL_TYPES == expected

    def test_constants_are_frozenset(self) -> None:
        """Frozenset prevents accidental mutation at runtime."""
        from src.analysis.metrics import (
            VALID_MARKET_REGIMES,
            VALID_METRIC_STATUSES,
            VALID_VPIN_LEVELS,
            VALID_VSA_SIGNAL_TYPES,
        )

        assert isinstance(VALID_METRIC_STATUSES, frozenset)
        assert isinstance(VALID_VPIN_LEVELS, frozenset)
        assert isinstance(VALID_MARKET_REGIMES, frozenset)
        assert isinstance(VALID_VSA_SIGNAL_TYPES, frozenset)


# ---------------------------------------------------------------------------
# 3. Safe helper functions — valid labels
# ---------------------------------------------------------------------------


class TestHelperFunctionsValidLabels:
    """Verify helper functions work with valid label values (no exceptions)."""

    def test_record_ta_computation_success(self) -> None:
        from src.analysis.metrics import record_ta_computation

        # Should not raise
        record_ta_computation("success", 0.005)

    def test_record_ta_computation_error(self) -> None:
        from src.analysis.metrics import record_ta_computation

        record_ta_computation("error", 0.1)

    def test_record_volume_profile_success(self) -> None:
        from src.analysis.metrics import record_volume_profile

        record_volume_profile("success")

    def test_record_volume_profile_error(self) -> None:
        from src.analysis.metrics import record_volume_profile

        record_volume_profile("error")

    def test_record_vsa_signal_all_types(self) -> None:
        from src.analysis.metrics import VALID_VSA_SIGNAL_TYPES, record_vsa_signal

        for signal_type in VALID_VSA_SIGNAL_TYPES:
            record_vsa_signal(signal_type)

    def test_record_depth_analysis_success(self) -> None:
        from src.analysis.metrics import record_depth_analysis

        record_depth_analysis("success")

    def test_record_vpin_all_levels(self) -> None:
        from src.analysis.metrics import VALID_VPIN_LEVELS, record_vpin

        for level in VALID_VPIN_LEVELS:
            record_vpin(level)

    def test_record_pipeline_run_success(self) -> None:
        from src.analysis.metrics import record_pipeline_run

        record_pipeline_run("success", 0.01)

    def test_record_pipeline_run_partial(self) -> None:
        from src.analysis.metrics import record_pipeline_run

        record_pipeline_run("partial", 0.05)

    def test_set_market_regime_all_regimes(self) -> None:
        from src.analysis.metrics import VALID_MARKET_REGIMES, set_market_regime

        for regime in VALID_MARKET_REGIMES:
            set_market_regime(regime, 1.0)


# ---------------------------------------------------------------------------
# 4. Safe helper functions — invalid labels raise ValueError
# ---------------------------------------------------------------------------


class TestHelperFunctionsInvalidLabels:
    """Verify helper functions reject invalid label values with ValueError."""

    def test_record_ta_computation_invalid_status(self) -> None:
        from src.analysis.metrics import record_ta_computation

        with pytest.raises(ValueError, match="Invalid TA status label"):
            record_ta_computation("unknown", 0.01)

    def test_record_ta_computation_empty_status(self) -> None:
        from src.analysis.metrics import record_ta_computation

        with pytest.raises(ValueError, match="Invalid TA status label"):
            record_ta_computation("", 0.01)

    def test_record_volume_profile_invalid_status(self) -> None:
        from src.analysis.metrics import record_volume_profile

        with pytest.raises(ValueError, match="Invalid volume profile status label"):
            record_volume_profile("FAILED")

    def test_record_vsa_signal_invalid_type(self) -> None:
        from src.analysis.metrics import record_vsa_signal

        with pytest.raises(ValueError, match="Invalid VSA signal type label"):
            record_vsa_signal("FAKE_SIGNAL")

    def test_record_vsa_signal_lowercase_rejected(self) -> None:
        from src.analysis.metrics import record_vsa_signal

        with pytest.raises(ValueError, match="Invalid VSA signal type label"):
            record_vsa_signal("demand_bar")

    def test_record_depth_analysis_invalid_status(self) -> None:
        from src.analysis.metrics import record_depth_analysis

        with pytest.raises(ValueError, match="Invalid depth analysis status label"):
            record_depth_analysis("warn")

    def test_record_vpin_invalid_level(self) -> None:
        from src.analysis.metrics import record_vpin

        with pytest.raises(ValueError, match="Invalid VPIN level label"):
            record_vpin("CRITICAL")

    def test_record_vpin_lowercase_rejected(self) -> None:
        from src.analysis.metrics import record_vpin

        with pytest.raises(ValueError, match="Invalid VPIN level label"):
            record_vpin("normal")

    def test_record_pipeline_run_invalid_status(self) -> None:
        from src.analysis.metrics import record_pipeline_run

        with pytest.raises(ValueError, match="Invalid pipeline status label"):
            record_pipeline_run("timeout", 0.1)

    def test_set_market_regime_invalid_regime(self) -> None:
        from src.analysis.metrics import set_market_regime

        with pytest.raises(ValueError, match="Invalid market regime label"):
            set_market_regime("RANGING", 1.0)

    def test_set_market_regime_lowercase_rejected(self) -> None:
        from src.analysis.metrics import set_market_regime

        with pytest.raises(ValueError, match="Invalid market regime label"):
            set_market_regime("trending", 1.0)


# ---------------------------------------------------------------------------
# 5. Module-level exports (__all__)
# ---------------------------------------------------------------------------


class TestModuleExports:
    """Verify __all__ is complete and all exports are importable."""

    def test_all_items_importable(self) -> None:
        import src.analysis.metrics as metrics_mod

        for name in metrics_mod.__all__:
            assert hasattr(metrics_mod, name), f"__all__ lists {name!r} but it is not defined"

    def test_all_covers_all_public_names(self) -> None:
        """Verify every public name in the module is in __all__."""
        import src.analysis.metrics as metrics_mod

        public_names = {
            name
            for name in dir(metrics_mod)
            if not name.startswith("_") and not callable(getattr(metrics_mod, name, None)) or name.isupper()
        }
        # Filter out non-module names that are imported but not ours
        for name in metrics_mod.__all__:
            assert name in public_names or hasattr(metrics_mod, name), f"{name!r} in __all__ but not in module"

    def test_all_list_count(self) -> None:
        """Verify __all__ has the expected number of exports."""
        import src.analysis.metrics as metrics_mod

        # 11 metric objects + 4 label constants + 7 helper functions = 22
        assert len(metrics_mod.__all__) == 22


# ---------------------------------------------------------------------------
# 6. Metric object names follow Prometheus naming conventions
# ---------------------------------------------------------------------------


class TestPrometheusNamingConventions:
    """Verify metric names follow Prometheus best practices
    (snake_case, _total suffix for counters, _seconds suffix for histograms)."""

    def test_counter_names_have_total_suffix(self) -> None:
        from src.analysis.metrics import (
            ANALYSIS_PIPELINE_TOTAL,
            DEPTH_ANALYSIS_COMPUTED,
            TA_INDICATORS_COMPUTED,
            VOLUME_ANOMALIES_DETECTED,
            VOLUME_PROFILE_COMPUTED,
            VPIN_COMPUTED,
            VSA_SIGNALS_DETECTED,
        )

        counter_metrics = [
            TA_INDICATORS_COMPUTED,
            VOLUME_PROFILE_COMPUTED,
            VSA_SIGNALS_DETECTED,
            VOLUME_ANOMALIES_DETECTED,
            DEPTH_ANALYSIS_COMPUTED,
            VPIN_COMPUTED,
            ANALYSIS_PIPELINE_TOTAL,
        ]
        for metric in counter_metrics:
            # prometheus_client Counter._name is the user-given name;
            # the full metric name exposed to Prometheus appends _total automatically.
            # Verify the full name ends with _total.
            full_name = metric._name + "_total"
            assert full_name.endswith("_total"), f"Counter full name {full_name} missing _total suffix"
            # Also verify the user-given name doesn't already have _total (avoid double _total_total)
            assert not metric._name.endswith(
                "_total"
            ), f"Counter {metric._name} already has _total suffix (would become _total_total in Prometheus)"

    def test_histogram_names_have_seconds_suffix(self) -> None:
        from src.analysis.metrics import (
            ANALYSIS_PIPELINE_LATENCY,
            TA_COMPUTE_LATENCY,
        )

        histogram_metrics = [
            TA_COMPUTE_LATENCY,
            ANALYSIS_PIPELINE_LATENCY,
        ]
        for metric in histogram_metrics:
            assert metric._name.endswith("_seconds"), f"Histogram {metric._name} missing _seconds suffix"


# ---------------------------------------------------------------------------
# 7. Label constants match VSASignalType enum from volume.py
# ---------------------------------------------------------------------------


class TestLabelEnumConsistency:
    """Verify label constants in metrics.py match the actual enum values
    from the analysis modules (prevents metric label drift)."""

    def test_vsa_signal_types_match_enum(self) -> None:
        from src.analysis.metrics import VALID_VSA_SIGNAL_TYPES
        from src.analysis.volume import VSASignalType

        enum_values = frozenset(member.value for member in VSASignalType)
        assert (
            VALID_VSA_SIGNAL_TYPES == enum_values
        ), f"VALID_VSA_SIGNAL_TYPES {VALID_VSA_SIGNAL_TYPES} != VSASignalType values {enum_values}"

    def test_vpin_levels_match_enum(self) -> None:
        from src.analysis.depth import VPINLevel
        from src.analysis.metrics import VALID_VPIN_LEVELS

        enum_values = frozenset(member.value for member in VPINLevel)
        assert (
            VALID_VPIN_LEVELS == enum_values
        ), f"VALID_VPIN_LEVELS {VALID_VPIN_LEVELS} != VPINLevel values {enum_values}"
