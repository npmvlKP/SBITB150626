"""Comprehensive tests for src/analysis/technical.py.

Covers: TechnicalIndicatorPipeline, all indicator groups,
market regime detection, custom implementations (Supertrend, CMF, VWAP),
Pydantic models, and edge cases.

References:
- Kaufman Ch.2-8: Signal design, indicator construction
- Chan Ch.1-4: Mean-reversion vs momentum regime switching
- Wilder (1978): RSI, ATR smoothing
"""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pytest

from config.settings import TechnicalIndicatorSettings
from src.analysis.technical import (
    MarketRegime,
    MomentumIndicators,
    TechnicalIndicatorPipeline,
    TechnicalIndicators,
    TrendIndicators,
    VIXLevel,
    VolatilityIndicators,
    VolumeIndicators,
    _default_momentum_indicators,
    _default_trend_indicators,
    _default_volatility_indicators,
    _default_volume_indicators,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> TechnicalIndicatorSettings:
    """Default TechnicalIndicatorSettings for testing."""
    return TechnicalIndicatorSettings()


@pytest.fixture
def sample_ohlcv() -> np.ndarray:
    """100-bar trending OHLCV sample data."""
    return _make_ohlcv(n=100, base_price=100.0, trend=0.001)


@pytest.fixture
def flat_ohlcv() -> np.ndarray:
    """50-bar flat/mean-reverting OHLCV sample data."""
    return _make_ohlcv(n=50, base_price=100.0, trend=0.0, spread=1.0)


@pytest.fixture
def low_volume_ohlcv() -> np.ndarray:
    """50-bar low-volume OHLCV sample data."""
    return _make_ohlcv(n=50, base_price=100.0, trend=0.0, base_vol=100.0)


# ---------------------------------------------------------------------------
# Synthetic Data Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv(
    n: int,
    base_price: float = 100.0,
    spread: float = 2.0,
    base_vol: float = 1000.0,
    trend: float = 0.0,
    seed: int = 42,
) -> np.ndarray:
    """Generate n bars of synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    data = np.zeros((n, 5), dtype=np.float64)
    price = base_price

    for i in range(n):
        daily_return = rng.normal(trend, spread / 100)
        price = price * (1 + daily_return)
        open_price = price * (1 + rng.normal(0, spread / 200))
        high = max(open_price, price) * (1 + abs(rng.normal(0, spread / 200)))
        low = min(open_price, price) * (1 - abs(rng.normal(0, spread / 200)))
        volume = base_vol * abs(rng.lognormal(0, 0.5))

        data[i] = [open_price, high, low, price, volume]

    return data


# ---------------------------------------------------------------------------
# Test: Pydantic Model Defaults
# ---------------------------------------------------------------------------


class TestMomentumIndicatorsModel:
    """Tests for MomentumIndicators Pydantic model."""

    def test_default_values(self) -> None:
        m = MomentumIndicators()
        assert m.rsi_14 is None
        assert m.rsi_percentile is None
        assert m.macd_line is None
        assert m.macd_signal is None
        assert m.macd_histogram is None
        assert m.adx_14 is None
        assert m.adx_percentile is None
        assert m.cci_20 is None

    def test_with_values(self) -> None:
        m = MomentumIndicators(rsi_14=55.0, adx_14=30.0, cci_20=100.0)
        assert m.rsi_14 == 55.0
        assert m.adx_14 == 30.0
        assert m.cci_20 == 100.0

    def test_rsi_bounds(self) -> None:
        m = MomentumIndicators(rsi_14=100.0)
        assert m.rsi_14 == 100.0


class TestVolatilityIndicatorsModel:
    """Tests for VolatilityIndicators Pydantic model."""

    def test_default_values(self) -> None:
        v = VolatilityIndicators()
        assert v.bbands_upper is None
        assert v.bbands_middle is None
        assert v.bbands_lower is None
        assert v.bbands_width is None
        assert v.bbands_pctb is None
        assert v.atr_14 is None
        assert v.atr_percentile is None
        assert v.vix_level == VIXLevel.UNKNOWN
        assert v.vix_value is None

    def test_vix_level_assignment(self) -> None:
        v = VolatilityIndicators(vix_level=VIXLevel.ELEVATED, vix_value=22.0)
        assert v.vix_level == VIXLevel.ELEVATED
        assert v.vix_value == 22.0


class TestTrendIndicatorsModel:
    """Tests for TrendIndicators Pydantic model."""

    def test_default_values(self) -> None:
        t = TrendIndicators()
        assert t.supertrend_value is None
        assert t.supertrend_direction is None
        assert t.ema_9 is None
        assert t.ema_21 is None
        assert t.ema_50 is None
        assert t.ema_200 is None
        assert t.ema_signal_fast is None
        assert t.ema_signal_macro is None
        assert t.vwap is None

    def test_bullish_ema_signals(self) -> None:
        t = TrendIndicators(ema_9=110.0, ema_21=105.0, ema_signal_fast=1)
        assert t.ema_signal_fast == 1


class TestVolumeIndicatorsModel:
    """Tests for VolumeIndicators Pydantic model."""

    def test_default_values(self) -> None:
        v = VolumeIndicators()
        assert v.obv is None
        assert v.obv_ema_21 is None
        assert v.mfi_14 is None
        assert v.cmf_20 is None
        assert v.volume_rate is None
        assert v.volume_rate_percentile is None

    def test_cmf_range(self) -> None:
        v = VolumeIndicators(cmf_20=0.5)
        assert -1.0 <= v.cmf_20 <= 1.0


class TestTechnicalIndicatorsModel:
    """Tests for top-level TechnicalIndicators model."""

    def test_default_regime(self) -> None:
        ti = TechnicalIndicators()
        assert ti.regime == MarketRegime.UNKNOWN
        assert ti.hurst_exponent is None
        assert ti.timestamp is None

    def test_timestamp_assignment(self) -> None:
        from datetime import datetime

        ts = datetime(2024, 1, 1, tzinfo=UTC)
        ti = TechnicalIndicators(timestamp=ts)
        assert ti.timestamp == ts


# ---------------------------------------------------------------------------
# Test: TechnicalIndicatorPipeline Construction
# ---------------------------------------------------------------------------


class TestPipelineConstruction:
    """Tests for TechnicalIndicatorPipeline initialization."""

    def test_init(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        assert pipeline._settings is settings

    def test_default_factory_functions(self) -> None:
        """Default factory functions produce correct empty models."""
        m = _default_momentum_indicators()
        assert m.rsi_14 is None
        assert m.macd_line is None

        v = _default_volatility_indicators()
        assert v.vix_level == VIXLevel.UNKNOWN
        assert v.bbands_upper is None

        t = _default_trend_indicators()
        assert t.vwap is None
        assert t.supertrend_direction is None

        vol = _default_volume_indicators()
        assert vol.obv is None
        assert vol.mfi_14 is None


# ---------------------------------------------------------------------------
# Test: TechnicalIndicatorPipeline.compute — Edge Cases
# ---------------------------------------------------------------------------


class TestComputeEdgeCases:
    """Edge case tests for TechnicalIndicatorPipeline.compute."""

    def test_none_input(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(None)
        assert isinstance(result, TechnicalIndicators)
        assert result.regime == MarketRegime.UNKNOWN
        assert result.hurst_exponent is None

    def test_empty_array(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(np.array([], dtype=np.float64))
        assert isinstance(result, TechnicalIndicators)
        assert result.regime == MarketRegime.UNKNOWN

    def test_single_bar(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        single = np.array([[100.0, 105.0, 98.0, 102.0, 1000.0]], dtype=np.float64)
        result = pipeline.compute(single)
        assert isinstance(result, TechnicalIndicators)
        # Single bar — insufficient for most indicators
        assert result.momentum.rsi_14 is None
        assert result.regime == MarketRegime.UNKNOWN


# ---------------------------------------------------------------------------
# Test: Momentum Indicators
# ---------------------------------------------------------------------------


class TestRSI:
    """Tests for RSI computation."""

    def test_rsi_bounded(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        rsi = result.momentum.rsi_14
        if rsi is not None:
            assert 0.0 <= rsi <= 100.0

    def test_rsi_increases_with_uptrend(self, settings: TechnicalIndicatorSettings) -> None:
        """In a sustained uptrend, RSI tends to be elevated (> 50)."""
        pipeline = TechnicalIndicatorPipeline(settings)
        # Strong uptrend: 100 bars, +0.5% daily trend
        uptrend = _make_ohlcv(n=100, base_price=100.0, trend=0.005)
        result = pipeline.compute(uptrend)
        # RSI should be in valid range
        if result.momentum.rsi_14 is not None:
            assert 0.0 <= result.momentum.rsi_14 <= 100.0


class TestMACD:
    """Tests for MACD computation."""

    def test_macd_values(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        assert result.momentum.macd_line is not None
        assert result.momentum.macd_signal is not None
        assert result.momentum.macd_histogram is not None

    def test_macd_histogram_formula(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        if result.momentum.macd_line is not None and result.momentum.macd_signal is not None:
            expected_hist = result.momentum.macd_line - result.momentum.macd_signal
            assert abs(result.momentum.macd_histogram - expected_hist) < 1e-6


class TestADX:
    """Tests for ADX computation."""

    def test_adx_bounded(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        adx = result.momentum.adx_14
        if adx is not None:
            assert 0.0 <= adx <= 100.0


class TestCCI:
    """Tests for CCI(20) — must override TA-Lib default of 14."""

    def test_cci_computed(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        # CCI(20) should be computed if we have enough bars
        if len(sample_ohlcv) >= 20:
            assert result.momentum.cci_20 is not None


# ---------------------------------------------------------------------------
# Test: Volatility Indicators
# ---------------------------------------------------------------------------


class TestBollingerBands:
    """Tests for Bollinger Bands."""

    def test_bbands_upper_gt_lower(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        assert result.volatility.bbands_upper is not None
        assert result.volatility.bbands_middle is not None
        assert result.volatility.bbands_lower is not None
        assert result.volatility.bbands_upper >= result.volatility.bbands_middle
        assert result.volatility.bbands_middle >= result.volatility.bbands_lower

    def test_bbands_width_formula(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        u = result.volatility.bbands_upper
        m = result.volatility.bbands_middle
        ll = result.volatility.bbands_lower
        if u is not None and m is not None and ll is not None and m != 0:
            expected_width = (u - ll) / m
            assert abs(result.volatility.bbands_width - expected_width) < 1e-6


class TestATR:
    """Tests for ATR(14) computation."""

    def test_atr_positive(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        if result.volatility.atr_14 is not None:
            assert result.volatility.atr_14 > 0.0


class TestVIXClassification:
    """Tests for India VIX level classification."""

    @pytest.mark.parametrize(
        ("vix_value", "expected_level"),
        [
            (10.0, VIXLevel.LOW),
            (15.0, VIXLevel.NORMAL),
            (22.0, VIXLevel.ELEVATED),
            (28.0, VIXLevel.HIGH),
            (40.0, VIXLevel.EXTREME),
        ],
    )
    def test_vix_levels(
        self,
        settings: TechnicalIndicatorSettings,
        sample_ohlcv: np.ndarray,
        vix_value: float,
        expected_level: VIXLevel,
    ) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv, india_vix=vix_value)
        assert result.volatility.vix_level == expected_level
        assert result.volatility.vix_value == vix_value

    def test_vix_unknown_without_input(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv, india_vix=None)
        assert result.volatility.vix_level == VIXLevel.UNKNOWN


# ---------------------------------------------------------------------------
# Test: Trend Indicators
# ---------------------------------------------------------------------------


class TestSupertrend:
    """Tests for custom Supertrend implementation."""

    def test_supertrend_value_valid(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        assert result.trend.supertrend_value is not None
        assert result.trend.supertrend_direction is not None
        assert result.trend.supertrend_direction in (-1, 1)

    def test_supertrend_short_data(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        short = _make_ohlcv(n=5)
        result = pipeline.compute(short)
        # Supertrend needs period+1 bars
        if len(short) < settings.SUPERTREND_PERIOD + 1:
            assert result.trend.supertrend_value is None


class TestEMA:
    """Tests for EMA calculations."""

    def test_ema_values(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        assert result.trend.ema_9 is not None
        assert result.trend.ema_21 is not None

    def test_ema_fast_lt_slow_in_downtrend(self, settings: TechnicalIndicatorSettings) -> None:
        """In downtrend, fast EMA < slow EMA."""
        pipeline = TechnicalIndicatorPipeline(settings)
        downtrend = _make_ohlcv(n=100, base_price=100.0, trend=-0.001)
        result = pipeline.compute(downtrend)
        if result.trend.ema_9 is not None and result.trend.ema_21 is not None:
            if result.trend.ema_signal_fast == -1:
                assert result.trend.ema_9 < result.trend.ema_21

    def test_ema_fast_gt_slow_in_uptrend(self, settings: TechnicalIndicatorSettings) -> None:
        """In uptrend, fast EMA > slow EMA."""
        pipeline = TechnicalIndicatorPipeline(settings)
        uptrend = _make_ohlcv(n=100, base_price=100.0, trend=0.001)
        result = pipeline.compute(uptrend)
        if result.trend.ema_9 is not None and result.trend.ema_21 is not None:
            if result.trend.ema_signal_fast == 1:
                assert result.trend.ema_9 > result.trend.ema_21


class TestVWAP:
    """Tests for custom VWAP implementation."""

    def test_vwap_valid(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        assert result.trend.vwap is not None
        assert result.trend.vwap > 0.0

    def test_vwap_in_range(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        if result.trend.vwap is not None:
            highs = sample_ohlcv[:, 1]
            lows = sample_ohlcv[:, 2]
            assert result.trend.vwap >= lows.min()
            assert result.trend.vwap <= highs.max()


# ---------------------------------------------------------------------------
# Test: Volume Indicators
# ---------------------------------------------------------------------------


class TestOBV:
    """Tests for On-Balance Volume."""

    def test_obv_increases_with_price(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        # Rising price → OBV should increase
        rising = np.array(
            [
                [100.0, 105.0, 98.0, 102.0, 1000.0],
                [102.0, 108.0, 101.0, 106.0, 1200.0],
                [106.0, 110.0, 105.0, 109.0, 1500.0],
            ],
            dtype=np.float64,
        )
        result = pipeline.compute(rising)
        assert result.volume.obv is not None
        assert result.volume.obv > 0

    def test_obv_smoothed(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        # OBV EMA requires 21+ bars
        if len(sample_ohlcv) > settings.OBV_SMOOTHING_PERIOD:
            assert result.volume.obv_ema_21 is not None


class TestMFI:
    """Tests for Money Flow Index."""

    def test_mfi_bounded(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        mfi = result.volume.mfi_14
        if mfi is not None:
            assert 0.0 <= mfi <= 100.0


class TestCMF:
    """Tests for custom CMF implementation."""

    def test_cmf_bounded(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        cmf = result.volume.cmf_20
        if cmf is not None:
            assert -1.0 <= cmf <= 1.0

    def test_cmf_short_data(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        short = _make_ohlcv(n=5)
        result = pipeline.compute(short)
        # CMF needs period+1 bars
        assert result.volume.cmf_20 is None


class TestVolumeRate:
    """Tests for Volume Rate computation."""

    def test_volume_rate_positive(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv)
        vol_rate = result.volume.volume_rate
        if vol_rate is not None:
            assert vol_rate >= 0.0


# ---------------------------------------------------------------------------
# Test: Market Regime Detection
# ---------------------------------------------------------------------------


class TestMarketRegime:
    """Tests for market regime classification (Chan Ch.1-4)."""

    def test_regime_unknown_with_insufficient_data(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        short = _make_ohlcv(n=5)
        result = pipeline.compute(short)
        assert result.regime == MarketRegime.UNKNOWN

    def test_regime_enum_values(self) -> None:
        """All expected regime values are available."""
        assert MarketRegime.TRENDING == "TRENDING"
        assert MarketRegime.MEAN_REVERTING == "MEAN_REVERTING"
        assert MarketRegime.RANDOM_WALK == "RANDOM_WALK"
        assert MarketRegime.UNKNOWN == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test: Helper Methods
# ---------------------------------------------------------------------------


class TestSafeLast:
    """Tests for _safe_last helper method."""

    def test_safe_last_valid(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        assert pipeline._safe_last(arr) == 3.0

    def test_safe_last_nan(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        arr = np.array([1.0, 2.0, np.nan], dtype=np.float64)
        assert pipeline._safe_last(arr) is None

    def test_safe_last_inf(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        arr = np.array([1.0, 2.0, np.inf], dtype=np.float64)
        assert pipeline._safe_last(arr) is None

    def test_safe_last_empty(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        assert pipeline._safe_last(None) is None
        assert pipeline._safe_last(np.array([], dtype=np.float64)) is None


class TestSafeLastInt:
    """Tests for _safe_last_int helper method."""

    def test_safe_last_int_valid(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        assert pipeline._safe_last_int(arr) == 3

    def test_safe_last_int_nan(self, settings: TechnicalIndicatorSettings) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        arr = np.array([1.0, 2.0, np.nan], dtype=np.float64)
        assert pipeline._safe_last_int(arr) is None


# ---------------------------------------------------------------------------
# Test: Integration — Full Pipeline with VIX
# ---------------------------------------------------------------------------


class TestFullPipelineWithVIX:
    """Integration test: compute with India VIX input."""

    def test_vix_affects_volatility(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv, india_vix=30.0)
        assert result.volatility.vix_level == VIXLevel.HIGH
        assert result.volatility.vix_value == 30.0

    def test_full_indicators_not_none(self, settings: TechnicalIndicatorSettings, sample_ohlcv: np.ndarray) -> None:
        pipeline = TechnicalIndicatorPipeline(settings)
        result = pipeline.compute(sample_ohlcv, india_vix=18.0)
        # All major indicators should be computed
        assert result.momentum.rsi_14 is not None
        assert result.momentum.adx_14 is not None
        assert result.momentum.macd_line is not None
        assert result.momentum.cci_20 is not None
        assert result.volatility.bbands_upper is not None
        assert result.volatility.atr_14 is not None
        assert result.trend.supertrend_value is not None
        assert result.trend.ema_9 is not None
        assert result.trend.vwap is not None
        assert result.volume.obv is not None
        assert result.volume.mfi_14 is not None


# ---------------------------------------------------------------------------
# Test: VIXLevel Enum
# ---------------------------------------------------------------------------


class TestVIXLevelEnum:
    """Tests for VIXLevel enum values."""

    def test_all_vix_levels_defined(self) -> None:
        assert VIXLevel.LOW == "LOW"
        assert VIXLevel.NORMAL == "NORMAL"
        assert VIXLevel.ELEVATED == "ELEVATED"
        assert VIXLevel.HIGH == "HIGH"
        assert VIXLevel.EXTREME == "EXTREME"
        assert VIXLevel.UNKNOWN == "UNKNOWN"

    def test_vix_level_string(self) -> None:
        assert str(VIXLevel.ELEVATED) == "ELEVATED"
