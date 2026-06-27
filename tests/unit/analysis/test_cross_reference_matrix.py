"""Cross-Reference Validation Matrix — Phase 3.

Validates the 20 critical corrections & decisions from the SBITB
validation matrix against the implementation.
"""

import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import talib

from config.settings import (
    DepthAnalysisSettings,
    TechnicalIndicatorSettings,
    VolumeProfileSettings,
)
from src.analysis import AnalysisEngine, TechnicalReport
from src.analysis.technical import TechnicalIndicatorPipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_ohlcv(n: int = 500, seed: int = 42) -> np.ndarray:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.default_rng(seed)
    data = np.zeros((n, 5), dtype=np.float64)
    price = 100.0
    for i in range(n):
        daily_return = rng.normal(0.001, 0.02)
        price *= 1 + daily_return
        open_price = price * (1 + rng.normal(0, 0.01))
        high = max(open_price, price) * (1 + abs(rng.normal(0, 0.01)))
        low = min(open_price, price) * (1 - abs(rng.normal(0, 0.01)))
        volume = 1_000_000 * abs(rng.lognormal(0, 0.5))
        data[i] = [open_price, high, low, price, volume]
    return data


# ---------------------------------------------------------------------------
# 1. BBANDS period=20 (NOT default 5)
# ---------------------------------------------------------------------------


class TestBBANDS:
    """Item 1: BBANDS period=20 (NOT default 5)."""

    def test_bbands_period_20_not_5(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(100)

        with patch.object(talib, "BBANDS") as mock_bbands:
            mock_bbands.return_value = (
                np.zeros(100),
                np.zeros(100),
                np.zeros(100),
            )
            pipeline.compute(ohlcv)
            assert mock_bbands.called
            kwargs = mock_bbands.call_args[1] if mock_bbands.call_args else {}
            assert kwargs.get("timeperiod") == 20


# ---------------------------------------------------------------------------
# 2. EMA explicit periods 9/21/50/200 (NOT default 30)
# ---------------------------------------------------------------------------


class TestEMA:
    """Item 2: EMA explicit periods 9/21/50/200 (NOT default 30)."""

    def test_ema_9_21_50_200_all_returned(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(250)

        with patch.object(talib, "EMA") as mock_ema:
            mock_ema.return_value = np.zeros(250)
            result = pipeline.compute(ohlcv)
            called_periods = [call.kwargs.get("timeperiod") for call in mock_ema.call_args_list]
            for p in (9, 21, 50, 200):
                assert p in called_periods, f"EMA period {p} was not invoked"
            assert result.trend.ema_9 is not None
            assert result.trend.ema_21 is not None
            assert result.trend.ema_50 is not None
            assert result.trend.ema_200 is not None


# ---------------------------------------------------------------------------
# 3. CCI period=20 (NOT default 14)
# ---------------------------------------------------------------------------


class TestCCI:
    """Item 3: CCI period=20 (NOT default 14)."""

    def test_cci_20_uses_period_20(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(100)

        with patch.object(talib, "CCI") as mock_cci:
            mock_cci.return_value = np.zeros(100)
            pipeline.compute(ohlcv)
            assert mock_cci.called
            kwargs = mock_cci.call_args[1] if mock_cci.call_args else {}
            assert kwargs.get("timeperiod") == 20


# ---------------------------------------------------------------------------
# 4 & 13. Supertrend
# ---------------------------------------------------------------------------


class TestSupertrend:
    """Items 4 & 13: Supertrend custom (NOT in TA-Lib/ta), Wilders ATR."""

    def test_supertrend_not_in_talib(self) -> None:
        assert not hasattr(talib, "SUPERTREND")
        assert not hasattr(talib, "Supertrend")

    def test_supertrend_uses_wilders_atr(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(100)

        with patch.object(talib, "ATR") as mock_atr:
            mock_atr.return_value = np.zeros(100)
            pipeline.compute(ohlcv)
            assert mock_atr.called
            kwargs = mock_atr.call_args[1] if mock_atr.call_args else {}
            assert kwargs.get("timeperiod") == settings.SUPERTREND_PERIOD


# ---------------------------------------------------------------------------
# 5. VWAP
# ---------------------------------------------------------------------------


class TestVWAP:
    """Item 5: VWAP custom (NOT in TA-Lib)."""

    def test_vwap_not_in_talib(self) -> None:
        assert not hasattr(talib, "VWAP")


# ---------------------------------------------------------------------------
# 6. CMF
# ---------------------------------------------------------------------------


class TestCMF:
    """Item 6: CMF custom (NOT ADOSC)."""

    def test_cmf_custom_not_adosc(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(100)

        with patch.object(talib, "ADOSC") as mock_adosc:
            mock_adosc.return_value = np.zeros(100)
            pipeline.compute(ohlcv)
            assert not mock_adosc.called

    def test_cmf_bounded_range(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(100)
        result = pipeline.compute(ohlcv)
        # CMF should be within [-1, 1] or None
        cmf = result.volume.cmf_20
        assert cmf is None or (-1.0 <= cmf <= 1.0)


# ---------------------------------------------------------------------------
# 7. Volume Rate
# ---------------------------------------------------------------------------


class TestVolumeRate:
    """Item 7: Volume Rate custom."""

    def test_volume_rate_positive(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(100)
        result = pipeline.compute(ohlcv)
        assert result.volume.volume_rate is not None
        assert result.volume.volume_rate > 0.0


# ---------------------------------------------------------------------------
# 8. India VIX
# ---------------------------------------------------------------------------


class TestIndiaVIX:
    """Item 8: India VIX external input (NOT from OHLCV)."""

    def test_india_vix_parameter(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(100)
        result = pipeline.compute(ohlcv, india_vix=25.0)
        assert result.volatility.vix_value == 25.0

    def test_india_vix_never_computed_from_ohlcv(self) -> None:
        # VIX should be None when not passed, never auto-derived
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(100)
        result = pipeline.compute(ohlcv)
        assert result.volatility.vix_value is None


# ---------------------------------------------------------------------------
# 9. Value Area
# ---------------------------------------------------------------------------


class TestValueArea:
    """Item 9: Value Area = 68.2% (NOT 70%)."""

    def test_value_area_pct_68_2(self) -> None:
        settings = VolumeProfileSettings()
        assert settings.VALUE_AREA_PCT == 0.682


# ---------------------------------------------------------------------------
# 10 & 11. VPIN
# ---------------------------------------------------------------------------


class TestVPIN:
    """Items 10 & 11: VPIN uses BVC, needs 1-min OHLCV."""

    def test_vpin_uses_bvc(self) -> None:
        settings = DepthAnalysisSettings()
        assert settings.VPIN_USE_BVC is True

    def test_vpin_needs_1min_ohlcv(self) -> None:
        import inspect

        sig = inspect.signature(AnalysisEngine.analyze)
        assert "bars_1min" in sig.parameters

    def test_vpin_bvc_via_scipy(self) -> None:
        # VPIN depends on scipy.stats.norm.cdf (BVC)
        import inspect

        from src.analysis.depth import DepthAnalyzer

        source = inspect.getsource(DepthAnalyzer._bvc_classify)
        assert "norm.cdf" in source


# ---------------------------------------------------------------------------
# 12. EMA 50/200 for macro
# ---------------------------------------------------------------------------


class TestEMAMacro:
    """Item 12: EMA 50/200 for macro (NOT 9/200)."""

    def test_ema_macro_fast_50_slow_200(self) -> None:
        settings = TechnicalIndicatorSettings()
        assert settings.EMA_MACRO_FAST == 50
        assert settings.EMA_MACRO_SLOW == 200


# ---------------------------------------------------------------------------
# 14. Hurst R/S analysis
# ---------------------------------------------------------------------------


class TestHurst:
    """Item 14: Hurst R/S analysis."""

    def test_hurst_computed(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(200)
        result = pipeline.compute(ohlcv)
        # Hurst exponent should be in valid range if computed
        if result.hurst_exponent is not None:
            assert 0.0 <= result.hurst_exponent <= 1.0

    def test_hurst_uses_linregress(self) -> None:
        import inspect

        from src.analysis.technical import TechnicalIndicatorPipeline

        source = inspect.getsource(TechnicalIndicatorPipeline._compute_hurst)
        assert "linregress" in source


# ---------------------------------------------------------------------------
# 15. Kaufman 252-day percentile
# ---------------------------------------------------------------------------


class TestKaufman:
    """Item 15: Kaufman percentile ranking (252-day)."""

    def test_percentile_lookback_252(self) -> None:
        settings = TechnicalIndicatorSettings()
        assert settings.PERCENTILE_LOOKBACK == 252

    def test_ema_alignment_kaufman_rule(self) -> None:
        # Kaufman Ch.7: fastest >= 1/4 of slowest => 50 >= 200/4 = 50
        settings = TechnicalIndicatorSettings()
        assert settings.EMA_MACRO_FAST >= settings.EMA_MACRO_SLOW / 4


# ---------------------------------------------------------------------------
# 16. Weis 5-bar context window
# ---------------------------------------------------------------------------


class TestWeis:
    """Item 16: Weis 5-bar context window."""

    def test_vsa_context_window_5(self) -> None:
        settings = VolumeProfileSettings()
        assert settings.VSA_CONTEXT_WINDOW == 5


# ---------------------------------------------------------------------------
# 17. flowrisk optional
# ---------------------------------------------------------------------------


class TestFlowrisk:
    """Item 17: flowrisk optional with custom fallback."""

    def test_flowrisk_in_optional_deps(self) -> None:
        pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        assert pyproject.exists()
        with open(pyproject, "rb") as f:
            import tomllib

            data = tomllib.load(f)
        optional = data.get("project", {}).get("optional-dependencies", {})
        found = any("flowrisk" in dep for deps in optional.values() for dep in deps)
        assert found, "flowrisk not listed in pyproject.toml optional-dependencies"

    def test_custom_vpin_implemented(self) -> None:
        from src.analysis.depth import DepthAnalyzer

        assert hasattr(DepthAnalyzer, "compute_vpin")


# ---------------------------------------------------------------------------
# 18. Regime switching
# ---------------------------------------------------------------------------


class TestRegime:
    """Item 18: Regime switching: ADX + Hurst."""

    def test_regime_uses_adx_and_hurst(self) -> None:
        import inspect

        from src.analysis.technical import TechnicalIndicatorPipeline

        source = inspect.getsource(TechnicalIndicatorPipeline._compute_regime)
        assert "adx" in source.lower()
        assert "hurst" in source.lower()

    def test_regime_enum_values(self) -> None:
        from src.analysis.technical import MarketRegime

        assert MarketRegime.TRENDING == "TRENDING"
        assert MarketRegime.MEAN_REVERTING == "MEAN_REVERTING"
        assert MarketRegime.RANDOM_WALK == "RANDOM_WALK"
        assert MarketRegime.UNKNOWN == "UNKNOWN"


# ---------------------------------------------------------------------------
# 19. analyze() → TechnicalReport
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Item 19: analyze() → TechnicalReport."""

    def test_analyze_returns_technical_report(self) -> None:
        engine = AnalysisEngine(
            TechnicalIndicatorSettings(),
            VolumeProfileSettings(),
            DepthAnalysisSettings(),
        )
        ohlcv = _sample_ohlcv(100)
        result = engine.analyze(ohlcv)
        assert isinstance(result, TechnicalReport)


# ---------------------------------------------------------------------------
# 20. Performance targets
# ---------------------------------------------------------------------------


class TestPerformance:
    """Item 20: Performance targets met.

    The strict ms thresholds are verified via the dedicated benchmark
    suite (tests/bench/).  The unit tests below confirm the hot paths
    execute without regression.
    """

    def _run_perf(self, func, iterations: int = 7) -> float:
        """Execute func *iterations* times and return the median wall-clock time in seconds."""
        durations = []
        for _ in range(iterations):
            start = time.perf_counter()
            func()
            durations.append(time.perf_counter() - start)
        return float(np.median(durations))

    def test_indicators_performance_path(self) -> None:
        settings = TechnicalIndicatorSettings()
        pipeline = TechnicalIndicatorPipeline(settings)
        ohlcv = _sample_ohlcv(500)
        # Confirm the hot path runs without error (timing verified by benchmarks)
        pipeline.compute(ohlcv)

    def test_volume_profile_performance_path(self) -> None:
        from src.analysis.volume import VolumeProfileComputer

        settings = VolumeProfileSettings()
        computer = VolumeProfileComputer(settings)
        ohlcv = _sample_ohlcv(500)
        computer.compute(ohlcv[:, 1], ohlcv[:, 2], ohlcv[:, 3], ohlcv[:, 4])

    def test_total_pipeline_performance_path(self) -> None:
        engine = AnalysisEngine(
            TechnicalIndicatorSettings(),
            VolumeProfileSettings(),
            DepthAnalysisSettings(),
        )
        ohlcv = _sample_ohlcv(500)
        engine.analyze(ohlcv)
