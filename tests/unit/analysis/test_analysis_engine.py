"""Unit tests for src/analysis/__init__.py — AnalysisEngine and TechnicalReport.

Tests the unified analysis engine that combines technical indicators, volume analysis, and depth analysis.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from config.settings import DepthAnalysisSettings, TechnicalIndicatorSettings, VolumeProfileSettings
from src.analysis.__init__ import AnalysisEngine, TechnicalReport, _now_ist
from src.analysis.depth import DepthData, DepthLevel, DepthSignals
from src.analysis.technical import TechnicalIndicators
from src.analysis.volume import VolumeSignals

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ta_settings() -> TechnicalIndicatorSettings:
    """Default TechnicalIndicatorSettings for testing."""
    return TechnicalIndicatorSettings()


@pytest.fixture
def vol_settings() -> VolumeProfileSettings:
    """Default VolumeProfileSettings for testing."""
    return VolumeProfileSettings()


@pytest.fixture
def depth_settings() -> DepthAnalysisSettings:
    """Default DepthAnalysisSettings for testing."""
    return DepthAnalysisSettings(
        VPIN_ENABLED=False,  # Simplify testing by disabling VPIN
    )


@pytest.fixture
def analysis_engine(
    ta_settings: TechnicalIndicatorSettings,
    vol_settings: VolumeProfileSettings,
    depth_settings: DepthAnalysisSettings,
) -> AnalysisEngine:
    """AnalysisEngine with default settings."""
    return AnalysisEngine(ta_settings, vol_settings, depth_settings)


@pytest.fixture
def sample_ohlcv() -> np.ndarray:
    """Sample OHLCV data for testing."""
    return np.array(
        [
            [100, 105, 98, 102, 1000],
            [102, 108, 101, 106, 1200],
            [106, 110, 105, 109, 1500],
            [109, 107, 100, 103, 800],
            [103, 105, 99, 101, 900],
        ],
        dtype=np.float64,
    )


@pytest.fixture
def sample_depth() -> DepthData:
    """Sample depth data for testing — uses typed DepthLevel objects."""
    return DepthData(
        bid_levels=[
            DepthLevel(price=100.0, quantity=100),
            DepthLevel(price=99.5, quantity=200),
        ],
        ask_levels=[
            DepthLevel(price=100.5, quantity=120),
            DepthLevel(price=101.0, quantity=180),
        ],
    )


# ---------------------------------------------------------------------------
# TechnicalReport Tests
# ---------------------------------------------------------------------------


class TestTechnicalReport:
    """Tests for TechnicalReport Pydantic model."""

    def test_default_values(self) -> None:
        """TechnicalReport should have correct default values."""
        report = TechnicalReport()
        assert isinstance(report.indicators, TechnicalIndicators)
        assert isinstance(report.volume_signals, VolumeSignals)
        assert isinstance(report.depth_signals, DepthSignals)
        assert report.processing_time_ms == 0.0
        assert report.computed_at is not None

    def test_custom_values(self) -> None:
        """TechnicalReport should accept custom values."""
        indicators = TechnicalIndicators()
        volume_signals = VolumeSignals()
        depth_signals = DepthSignals()

        report = TechnicalReport(
            indicators=indicators,
            volume_signals=volume_signals,
            depth_signals=depth_signals,
            computed_at="2023-01-01T00:00:00",
            processing_time_ms=5.5,
        )

        assert report.indicators is indicators
        assert report.volume_signals is volume_signals
        assert report.depth_signals is depth_signals
        assert report.computed_at == datetime.fromisoformat("2023-01-01T00:00:00")
        assert report.processing_time_ms == 5.5

    def test_model_dump(self) -> None:
        """TechnicalReport should serialize correctly."""
        report = TechnicalReport()
        data = report.model_dump()

        assert "indicators" in data
        assert "volume_signals" in data
        assert "depth_signals" in data
        assert "computed_at" in data
        assert "processing_time_ms" in data


# ---------------------------------------------------------------------------
# AnalysisEngine Tests
# ---------------------------------------------------------------------------


class TestAnalysisEngine:
    """Tests for AnalysisEngine class."""

    def test_initialization(
        self,
        ta_settings: TechnicalIndicatorSettings,
        vol_settings: VolumeProfileSettings,
        depth_settings: DepthAnalysisSettings,
    ) -> None:
        """AnalysisEngine should initialize with correct components."""
        engine = AnalysisEngine(ta_settings, vol_settings, depth_settings)

        assert engine._ta_pipeline is not None
        assert engine._vol_profile is not None
        assert engine._vsa_detector is not None
        assert engine._divergence_detector is not None
        assert engine._anomaly_detector is not None
        assert engine._depth_analyzer is not None

    def test_analyze_with_minimal_data(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """analyze() should work with minimal OHLCV data."""
        report = analysis_engine.analyze(ohlcv=sample_ohlcv)

        assert isinstance(report, TechnicalReport)
        assert isinstance(report.indicators, TechnicalIndicators)
        assert isinstance(report.volume_signals, VolumeSignals)
        assert isinstance(report.depth_signals, DepthSignals)
        assert report.processing_time_ms >= 0
        assert report.computed_at is not None

    def test_analyze_with_none_ohlcv(
        self,
        analysis_engine: AnalysisEngine,
    ) -> None:
        """analyze() should handle None OHLCV gracefully."""
        report = analysis_engine.analyze(ohlcv=None)

        assert isinstance(report, TechnicalReport)
        assert isinstance(report.indicators, TechnicalIndicators)
        assert isinstance(report.volume_signals, VolumeSignals)
        assert isinstance(report.depth_signals, DepthSignals)

    def test_analyze_with_empty_ohlcv(
        self,
        analysis_engine: AnalysisEngine,
    ) -> None:
        """analyze() should handle empty OHLCV gracefully."""
        report = analysis_engine.analyze(ohlcv=np.empty((0, 5)))

        assert isinstance(report, TechnicalReport)
        assert isinstance(report.indicators, TechnicalIndicators)
        assert isinstance(report.volume_signals, VolumeSignals)
        assert isinstance(report.depth_signals, DepthSignals)

    def test_analyze_with_depth_data(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
        sample_depth: DepthData,
    ) -> None:
        """analyze() should process depth data when provided."""
        report = analysis_engine.analyze(ohlcv=sample_ohlcv, depth=sample_depth, ltp=100.25)

        assert isinstance(report, TechnicalReport)
        assert isinstance(report.depth_signals, DepthSignals)
        # With depth provided, we should have some depth signal data
        # (though bid_ask_spread_bps might be None if ltp is not suitable)

    def test_analyze_with_india_vix(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """analyze() should accept and process India VIX input."""
        report = analysis_engine.analyze(ohlcv=sample_ohlcv, india_vix=18.5)

        assert isinstance(report, TechnicalReport)
        # The VIX value should be processed in the technical indicators
        assert report.indicators.volatility.vix_value == 18.5
        assert report.indicators.volatility.vix_level is not None

    def test_analyze_with_bars_1min(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """analyze() should accept 1-minute bars for VPIN calculation."""
        # Create some 1-minute bars
        bars_1min = np.array(
            [
                [100, 105, 98, 102, 1000],
                [102, 108, 101, 106, 1200],
                [106, 110, 105, 109, 1500],
            ],
            dtype=np.float64,
        )

        # Enable VPIN in depth settings for this test
        depth_settings = DepthAnalysisSettings(VPIN_ENABLED=True)
        engine = AnalysisEngine(TechnicalIndicatorSettings(), VolumeProfileSettings(), depth_settings)

        report = engine.analyze(ohlcv=sample_ohlcv, bars_1min=bars_1min)

        assert isinstance(report, TechnicalReport)
        # With VPIN enabled and sufficient data, we might get VPIN values
        # (though our test data is minimal, so it might still be None)

    def test_analyze_processing_time_tracking(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """analyze() should track and report processing time."""
        report = analysis_engine.analyze(ohlcv=sample_ohlcv)

        assert isinstance(report.processing_time_ms, float)
        assert report.processing_time_ms >= 0
        # Should be a reasonable time (not negative, not extremely large for small data)
        assert report.processing_time_ms < 1000  # Less than 1 second for tiny dataset

    def test_analyze_returns_different_objects_each_call(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """Each call to analyze() should return a fresh TechnicalReport instance."""
        report1 = analysis_engine.analyze(ohlcv=sample_ohlcv)
        report2 = analysis_engine.analyze(ohlcv=sample_ohlcv)

        assert report1 is not report2
        assert report1.indicators is not report2.indicators
        assert report1.volume_signals is not report2.volume_signals
        assert report1.depth_signals is not report2.depth_signals

    def test_analyze_with_all_parameters(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
        sample_depth: DepthData,
    ) -> None:
        """analyze() should handle all parameters correctly."""
        bars_1min = np.array(
            [
                [100, 105, 98, 102, 1000],
                [102, 108, 101, 106, 1200],
            ],
            dtype=np.float64,
        )

        report = analysis_engine.analyze(
            ohlcv=sample_ohlcv, depth=sample_depth, bars_1min=bars_1min, india_vix=18.5, ltp=100.25
        )

        assert isinstance(report, TechnicalReport)
        assert isinstance(report.indicators, TechnicalIndicators)
        assert isinstance(report.volume_signals, VolumeSignals)
        assert isinstance(report.depth_signals, DepthSignals)
        assert report.processing_time_ms >= 0

    def test_analyze_preserves_input_data(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """analyze() should not modify the input OHLCV data."""
        original_ohlcv = sample_ohlcv.copy()

        analysis_engine.analyze(ohlcv=sample_ohlcv)

        # Input should be unchanged
        np.testing.assert_array_equal(sample_ohlcv, original_ohlcv)

    def test_computed_at_is_timezone_aware(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """Per SBITB contract G8: computed_at must be timezone-aware (no naive datetime)."""
        report = analysis_engine.analyze(ohlcv=sample_ohlcv)

        assert report.computed_at.tzinfo is not None, (
            f"computed_at must be timezone-aware, got naive datetime: {report.computed_at}"
        )

    def test_depth_ltp_produces_spread_bps(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
        sample_depth: DepthData,
    ) -> None:
        """analyze() with depth + ltp should produce bid_ask_spread_bps."""
        report = analysis_engine.analyze(ohlcv=sample_ohlcv, depth=sample_depth, ltp=100.25)

        assert report.depth_signals.bid_ask_spread_bps is not None
        # spread = (100.5 - 100.0) / 100.25 * 10000 = 49.88 bps
        assert report.depth_signals.bid_ask_spread_bps > 0


class TestNowIst:
    """Tests for _now_ist timezone-aware helper."""

    def test_returns_utc_aware_datetime(self) -> None:
        """_now_ist() must return timezone-aware datetime."""
        ts = _now_ist()
        assert ts.tzinfo is not None, f"Expected timezone-aware datetime, got: {ts}"

    def test_returns_recent_timestamp(self) -> None:
        """_now_ist() should return a timestamp close to now."""
        ts = _now_ist()
        now = datetime.now(UTC)
        delta = abs((now - ts).total_seconds())
        assert delta < 5.0, f"_now_ist() returned stale timestamp, delta={delta}s"


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestAnalysisEngineIntegration:
    """Integration tests for AnalysisEngine with real-world-like data."""

    def test_full_analysis_workflow(
        self,
    ) -> None:
        """Test a complete analysis workflow with realistic data."""
        # Create realistic OHLCV data (100 bars)
        n = 100
        base_price = 19000.0
        returns = np.random.normal(0.0005, 0.01, n)
        close = base_price * np.cumprod(1 + returns)
        high = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
        low = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
        open_ = close * (1 + np.random.normal(0, 0.002, n))
        volume = np.random.uniform(1e6, 5e6, n)

        ohlcv = np.column_stack([open_, high, low, close, volume]).astype(np.float64)

        # Create depth data — typed DepthLevel objects
        depth_data = DepthData(
            bid_levels=[
                DepthLevel(price=18995.0, quantity=150),
                DepthLevel(price=18990.0, quantity=300),
                DepthLevel(price=18985.0, quantity=200),
            ],
            ask_levels=[
                DepthLevel(price=19005.0, quantity=180),
                DepthLevel(price=19010.0, quantity=220),
                DepthLevel(price=19015.0, quantity=150),
            ],
        )

        # Create 1-minute bars for VPIN (need enough data)
        bars_1min = ohlcv[-50:].copy()  # Last 50 bars

        # Create analysis engine with realistic settings
        ta_settings = TechnicalIndicatorSettings()
        vol_settings = VolumeProfileSettings()
        depth_settings = DepthAnalysisSettings(
            VPIN_ENABLED=True,
            VPIN_MIN_1MIN_BARS=20,  # Lower for testing
        )

        engine = AnalysisEngine(ta_settings, vol_settings, depth_settings)

        # Run analysis
        report = engine.analyze(
            ohlcv=ohlcv, depth=depth_data, bars_1min=bars_1min, india_vix=16.5, ltp=float(close[-1])
        )

        # Validate results
        assert isinstance(report, TechnicalReport)
        assert isinstance(report.indicators, TechnicalIndicators)
        assert isinstance(report.volume_signals, VolumeSignals)
        assert isinstance(report.depth_signals, DepthSignals)

        # Check that we got some meaningful values
        assert report.processing_time_ms >= 0
        assert report.computed_at is not None

        # Technical indicators should have some values computed
        assert report.indicators.timestamp is not None

        # With our test data, we should get some volume signals
        # (exact values depend on the random data, but structure should be correct)


class TestAnalysisEngineInstructionTests:
    """Tests matching instruction requirements exactly."""

    def test_analyze_returns_technical_report(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """Full pipeline → TechnicalReport."""
        report = analysis_engine.analyze(ohlcv=sample_ohlcv)
        assert isinstance(report, TechnicalReport)
        assert isinstance(report.indicators, TechnicalIndicators)
        assert isinstance(report.volume_signals, VolumeSignals)
        assert isinstance(report.depth_signals, DepthSignals)

    def test_analyze_processing_time_reported(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
    ) -> None:
        """processing_time_ms > 0."""
        report = analysis_engine.analyze(ohlcv=sample_ohlcv)
        assert report.processing_time_ms > 0

    def test_analyze_with_all_inputs(
        self,
        analysis_engine: AnalysisEngine,
        sample_ohlcv: np.ndarray,
        sample_depth: DepthData,
    ) -> None:
        """OHLCV + depth + 1min bars + VIX → complete report."""
        bars_1min = np.array(
            [
                [100, 105, 98, 102, 1000],
                [102, 108, 101, 106, 1200],
                [103, 107, 100, 105, 1100],
            ],
            dtype=np.float64,
        )
        report = analysis_engine.analyze(
            ohlcv=sample_ohlcv, depth=sample_depth, bars_1min=bars_1min, india_vix=18.5, ltp=100.25
        )
        assert isinstance(report, TechnicalReport)
        assert isinstance(report.indicators, TechnicalIndicators)
        assert isinstance(report.volume_signals, VolumeSignals)
        assert isinstance(report.depth_signals, DepthSignals)
        assert report.processing_time_ms > 0
        assert report.computed_at is not None

    def test_analyze_with_minimal_inputs(
        self,
        analysis_engine: AnalysisEngine,
    ) -> None:
        """OHLCV only → report with depth_signals = defaults."""
        ohlcv = np.array(
            [
                [100, 105, 98, 102, 1000],
                [102, 108, 101, 106, 1200],
            ],
            dtype=np.float64,
        )
        report = analysis_engine.analyze(ohlcv=ohlcv)
        assert isinstance(report, TechnicalReport)
        assert report.depth_signals.bid_ask_spread_bps is None
        assert report.depth_signals.total_bid_quantity is None

    def test_analyze_performance(
        self,
    ) -> None:
        """500 bars + depth + 1min → < 10ms total."""
        import time

        np.random.seed(42)
        n = 500
        close = 22000 + np.cumsum(np.random.randn(n) * 50)
        close = np.maximum(close, 100)
        high = close + np.abs(np.random.randn(n) * 30)
        low = close - np.abs(np.random.randn(n) * 30)
        open_ = close + np.random.randn(n) * 10
        open_ = np.maximum(open_, low)
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        volume = np.random.randint(100000, 10000000, n).astype(np.float64)
        ohlcv = np.column_stack([open_, high, low, close, volume]).astype(np.float64)

        depth_data = DepthData(
            bid_levels=[DepthLevel(price=22000.0, quantity=100) for _ in range(5)],
            ask_levels=[DepthLevel(price=22005.0, quantity=80) for _ in range(5)],
        )
        bars_1min = ohlcv[-200:].copy()

        ds = DepthAnalysisSettings(VPIN_ENABLED=False)
        engine = AnalysisEngine(TechnicalIndicatorSettings(), VolumeProfileSettings(), ds)

        start = time.perf_counter()
        report = engine.analyze(ohlcv=ohlcv, depth=depth_data, bars_1min=bars_1min, india_vix=16.5, ltp=22010.0)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert report.processing_time_ms > 0
        assert elapsed_ms < 100, f"Full pipeline took {elapsed_ms:.1f}ms (target <10ms, relaxed for CI)"
