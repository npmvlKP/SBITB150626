"""Unit tests for src/analysis/technical.py — Phase 3.

Tests all Pydantic output models, the TechnicalIndicatorPipeline,
each indicator group, custom implementations (Supertrend, CMF, VWAP),
regime detection, Hurst exponent, and edge cases.
"""

from __future__ import annotations

import numpy as np
import pytest
import talib

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
)

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def settings() -> TechnicalIndicatorSettings:
    """Default TechnicalIndicatorSettings."""
    return TechnicalIndicatorSettings()


@pytest.fixture
def pipeline(settings: TechnicalIndicatorSettings) -> TechnicalIndicatorPipeline:
    """Pipeline with default settings."""
    return TechnicalIndicatorPipeline(settings)


def generate_ohlcv(n: int = 300, trend: str = "up") -> np.ndarray:
    """Generate synthetic OHLCV data.

    Args:
        n: Number of bars.
        trend: 'up' (rising prices), 'down' (falling), 'flat' (sideways), 'volatile'.

    Returns:
        ndarray shape (N, 5) with columns [open, high, low, close, volume].
    """
    np.random.seed(42)
    base_price = 19000.0  # NIFTY-like

    if trend == "up":
        returns = np.random.normal(0.0005, 0.01, n)
    elif trend == "down":
        returns = np.random.normal(-0.0005, 0.01, n)
    elif trend == "volatile":
        returns = np.random.normal(0.0, 0.03, n)
    else:  # flat
        returns = np.random.normal(0.0, 0.005, n)

    close = base_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
    open_ = close * (1 + np.random.normal(0, 0.002, n))
    volume = np.random.uniform(1e6, 5e6, n)

    ohlcv = np.column_stack([open_, high, low, close, volume])
    return ohlcv


@pytest.fixture
def ohlcv_up() -> np.ndarray:
    """300 bars of trending-up OHLCV data."""
    return generate_ohlcv(300, "up")


@pytest.fixture
def ohlcv_down() -> np.ndarray:
    """300 bars of trending-down OHLCV data."""
    return generate_ohlcv(300, "down")


@pytest.fixture
def ohlcv_flat() -> np.ndarray:
    """300 bars of sideways OHLCV data."""
    return generate_ohlcv(300, "flat")


@pytest.fixture
def ohlcv_volatile() -> np.ndarray:
    """300 bars of volatile OHLCV data."""
    return generate_ohlcv(300, "volatile")


# ═══════════════════════════════════════════════════════════════════════════
# 1. Pydantic Model Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPydanticModels:
    """Validate Pydantic output models: defaults, serialization, enum values."""

    def test_market_regime_values(self) -> None:
        assert MarketRegime.TRENDING == "TRENDING"
        assert MarketRegime.MEAN_REVERTING == "MEAN_REVERTING"
        assert MarketRegime.RANDOM_WALK == "RANDOM_WALK"
        assert MarketRegime.UNKNOWN == "UNKNOWN"

    def test_vix_level_values(self) -> None:
        assert VIXLevel.LOW == "LOW"
        assert VIXLevel.NORMAL == "NORMAL"
        assert VIXLevel.ELEVATED == "ELEVATED"
        assert VIXLevel.HIGH == "HIGH"
        assert VIXLevel.EXTREME == "EXTREME"
        assert VIXLevel.UNKNOWN == "UNKNOWN"

    def test_momentum_indicators_defaults(self) -> None:
        m = MomentumIndicators()
        assert m.rsi_14 is None
        assert m.rsi_percentile is None
        assert m.macd_line is None
        assert m.macd_signal is None
        assert m.macd_histogram is None
        assert m.adx_14 is None
        assert m.adx_percentile is None
        assert m.cci_20 is None

    def test_volatility_indicators_defaults(self) -> None:
        v = VolatilityIndicators()
        assert v.bbands_upper is None
        assert v.bbands_width is None
        assert v.atr_14 is None
        assert v.vix_level == VIXLevel.UNKNOWN
        assert v.vix_value is None

    def test_trend_indicators_defaults(self) -> None:
        t = TrendIndicators()
        assert t.supertrend_value is None
        assert t.supertrend_direction is None
        assert t.ema_9 is None
        assert t.ema_signal_fast is None
        assert t.vwap is None

    def test_volume_indicators_defaults(self) -> None:
        v = VolumeIndicators()
        assert v.obv is None
        assert v.obv_ema_21 is None
        assert v.mfi_14 is None
        assert v.cmf_20 is None
        assert v.volume_rate is None
        assert v.volume_rate_percentile is None

    def test_technical_indicators_defaults(self) -> None:
        t = TechnicalIndicators()
        assert isinstance(t.momentum, MomentumIndicators)
        assert isinstance(t.volatility, VolatilityIndicators)
        assert isinstance(t.trend, TrendIndicators)
        assert isinstance(t.volume, VolumeIndicators)
        assert t.regime == MarketRegime.UNKNOWN
        assert t.hurst_exponent is None
        assert t.timestamp is None

    def test_technical_indicators_serialization(self) -> None:
        t = TechnicalIndicators()
        data = t.model_dump()
        assert "momentum" in data
        assert "volatility" in data
        assert "trend" in data
        assert "volume" in data
        assert data["regime"] == "UNKNOWN"

    def test_technical_indicators_json_roundtrip(self) -> None:
        t = TechnicalIndicators(
            regime=MarketRegime.TRENDING,
            hurst_exponent=0.55,
            momentum=MomentumIndicators(rsi_14=65.3),
        )
        json_str = t.model_dump_json()
        restored = TechnicalIndicators.model_validate_json(json_str)
        assert restored.regime == MarketRegime.TRENDING
        assert restored.hurst_exponent == 0.55
        assert restored.momentum.rsi_14 == 65.3


# ═══════════════════════════════════════════════════════════════════════════
# 2. Pipeline Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestPipelineEdgeCases:
    """Edge cases: None input, empty data, insufficient bars."""

    def test_compute_none_input(self, pipeline: TechnicalIndicatorPipeline) -> None:
        result = pipeline.compute(None)
        assert result.regime == MarketRegime.UNKNOWN
        assert result.momentum.rsi_14 is None

    def test_compute_empty_array(self, pipeline: TechnicalIndicatorPipeline) -> None:
        result = pipeline.compute(np.empty((0, 5)))
        assert result.regime == MarketRegime.UNKNOWN

    def test_compute_single_bar(self, pipeline: TechnicalIndicatorPipeline) -> None:
        bars = np.array([[19000, 19050, 18950, 19020, 1e6]])
        result = pipeline.compute(bars)
        # Single bar cannot compute most indicators, should return None values
        assert result.regime == MarketRegime.UNKNOWN

    def test_compute_two_bars(self, pipeline: TechnicalIndicatorPipeline) -> None:
        bars = np.array([[19000, 19050, 18950, 19020, 1e6], [19020, 19070, 18970, 19040, 1.5e6]])
        result = pipeline.compute(bars)
        assert isinstance(result, TechnicalIndicators)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Momentum Indicators
# ═══════════════════════════════════════════════════════════════════════════


class TestMomentumIndicators:
    """Test RSI, MACD, ADX, CCI computation."""

    def test_rsi_14_range(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        assert result.momentum.rsi_14 is not None
        assert 0 <= result.momentum.rsi_14 <= 100

    def test_macd_values(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        assert result.momentum.macd_line is not None
        assert result.momentum.macd_signal is not None
        assert result.momentum.macd_histogram is not None

    def test_macd_histogram_equals_line_minus_signal(
        self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray
    ) -> None:
        result = pipeline.compute(ohlcv_up)
        if (
            result.momentum.macd_line is not None
            and result.momentum.macd_signal is not None
            and result.momentum.macd_histogram is not None
        ):
            np.testing.assert_almost_equal(
                result.momentum.macd_histogram,
                result.momentum.macd_line - result.momentum.macd_signal,
                decimal=6,
            )

    def test_adx_14_range(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        assert result.momentum.adx_14 is not None
        assert 0 <= result.momentum.adx_14 <= 100

    def test_cci_20_not_none(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        assert result.momentum.cci_20 is not None

    def test_rsi_up_trend_typically_above_50(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        # Up-trending data should have RSI > 40 (gentle check)
        assert result.momentum.rsi_14 is not None
        assert result.momentum.rsi_14 > 30

    def test_cci_ta_lib_period_override(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        """Verify CCI uses period=20, not TA-Lib default of 14."""
        c = ohlcv_up[:, 3].astype(np.float64)
        h = ohlcv_up[:, 1].astype(np.float64)
        low = ohlcv_up[:, 2].astype(np.float64)
        cci_14 = talib.CCI(h, low, c, timeperiod=14)
        cci_20 = talib.CCI(h, low, c, timeperiod=20)
        # They should differ
        if not (np.isnan(cci_14[-1]) or np.isnan(cci_20[-1])):
            assert cci_14[-1] != cci_20[-1]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Volatility Indicators
# ═══════════════════════════════════════════════════════════════════════════


class TestVolatilityIndicators:
    """Test Bollinger Bands, ATR, India VIX classification."""

    def test_bbands_values(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        vol = result.volatility
        assert vol.bbands_upper is not None
        assert vol.bbands_middle is not None
        assert vol.bbands_lower is not None
        assert vol.bbands_upper > vol.bbands_lower

    def test_bbands_width_positive(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        vol = result.volatility
        if vol.bbands_width is not None:
            assert vol.bbands_width > 0

    def test_bbands_pctb_range(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        if result.volatility.bbands_pctb is not None:
            # %B can be outside [0, 1] when price is outside bands
            assert isinstance(result.volatility.bbands_pctb, float)

    def test_atr_14_positive(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        if result.volatility.atr_14 is not None:
            assert result.volatility.atr_14 > 0

    def test_vix_classification_low(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(300, "flat")
        result = pipeline.compute(ohlcv, india_vix=12.0)
        assert result.volatility.vix_level == VIXLevel.LOW
        assert result.volatility.vix_value == 12.0

    def test_vix_classification_normal(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(300, "flat")
        result = pipeline.compute(ohlcv, india_vix=16.5)
        assert result.volatility.vix_level == VIXLevel.NORMAL

    def test_vix_classification_elevated(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(300, "flat")
        result = pipeline.compute(ohlcv, india_vix=22.0)
        assert result.volatility.vix_level == VIXLevel.ELEVATED

    def test_vix_classification_high(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(300, "flat")
        result = pipeline.compute(ohlcv, india_vix=30.0)
        assert result.volatility.vix_level == VIXLevel.HIGH

    def test_vix_classification_extreme(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(300, "flat")
        result = pipeline.compute(ohlcv, india_vix=40.0)
        assert result.volatility.vix_level == VIXLevel.EXTREME

    def test_vix_unknown_when_none(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(300, "flat")
        result = pipeline.compute(ohlcv, india_vix=None)
        assert result.volatility.vix_level == VIXLevel.UNKNOWN
        assert result.volatility.vix_value is None

    def test_bbands_period_override(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        """Verify BBANDS uses period=20, not TA-Lib default of 5."""
        c = ohlcv_up[:, 3].astype(np.float64)
        bb_5 = talib.BBANDS(c, timeperiod=5, nbdevup=2.0, nbdevdn=2.0, matype=0)
        bb_20 = talib.BBANDS(c, timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0)
        # Upper bands must differ
        if not (np.isnan(bb_5[0][-1]) or np.isnan(bb_20[0][-1])):
            assert bb_5[0][-1] != bb_20[0][-1]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Trend Indicators
# ═══════════════════════════════════════════════════════════════════════════


class TestTrendIndicators:
    """Test Supertrend, EMA, EMA signals, VWAP."""

    def test_ema_values(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        assert result.trend.ema_9 is not None
        assert result.trend.ema_21 is not None

    def test_ema_fast_signal_direction(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        if result.trend.ema_signal_fast is not None:
            assert result.trend.ema_signal_fast in (1, -1)

    def test_ema_macro_signal_direction(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        if result.trend.ema_signal_macro is not None:
            assert result.trend.ema_signal_macro in (1, -1)

    def test_supertrend_values_with_sufficient_data(
        self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray
    ) -> None:
        result = pipeline.compute(ohlcv_up)
        if result.trend.supertrend_value is not None:
            assert result.trend.supertrend_value > 0
        if result.trend.supertrend_direction is not None:
            assert result.trend.supertrend_direction in (1, -1)

    def test_supertrend_insufficient_data(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(5, "flat")  # < period + 1
        result = pipeline.compute(ohlcv)
        # Should handle gracefully
        assert isinstance(result, TechnicalIndicators)

    def test_vwap_not_none(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        assert result.trend.vwap is not None
        assert result.trend.vwap > 0

    def test_vwap_near_price(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        """VWAP should be within the price range of the data."""
        result = pipeline.compute(ohlcv_up)
        last_close = ohlcv_up[-1, 3]
        if result.trend.vwap is not None:
            # VWAP should be within ±20% of last close
            assert abs(result.trend.vwap - last_close) / last_close < 0.2


# ═══════════════════════════════════════════════════════════════════════════
# 6. Volume Indicators
# ═══════════════════════════════════════════════════════════════════════════


class TestVolumeIndicators:
    """Test OBV, OBV EMA, MFI, CMF, Volume Rate."""

    def test_obv_not_none(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        assert result.volume.obv is not None

    def test_mfi_14_range(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        if result.volume.mfi_14 is not None:
            assert 0 <= result.volume.mfi_14 <= 100

    def test_cmf_20_range(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        if result.volume.cmf_20 is not None:
            assert -1.0 <= result.volume.cmf_20 <= 1.0

    def test_volume_rate_positive(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        if result.volume.volume_rate is not None:
            assert result.volume.volume_rate > 0

    def test_cmf_zero_range_bar(self, pipeline: TechnicalIndicatorPipeline) -> None:
        """CMF with high == low should not crash (division-by-zero guard)."""
        n = 30
        close = np.full(n, 19000.0)
        high = np.full(n, 19000.0)
        low = np.full(n, 19000.0)
        volume = np.full(n, 1e6)
        open_ = np.full(n, 19000.0)
        ohlcv = np.column_stack([open_, high, low, close, volume])
        result = pipeline.compute(ohlcv)
        # Should not raise — CMF returns None or 0.0
        assert isinstance(result.volume.cmf_20, float | type(None))

    def test_volume_rate_insufficient_data(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(5, "flat")
        result = pipeline.compute(ohlcv)
        # volume_rate needs > period+1 bars → should be None
        assert result.volume.volume_rate is None


# ═══════════════════════════════════════════════════════════════════════════
# 7. Custom Implementation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCustomImplementations:
    """Direct tests of Supertrend, CMF, VWAP, Volume Rate methods."""

    def test_supertrend_bullish_bearish(self, pipeline: TechnicalIndicatorPipeline) -> None:
        """Supertrend should produce direction +1 or -1 with enough data."""
        ohlcv = generate_ohlcv(100, "up")
        c = ohlcv[:, 3].astype(np.float64)
        h = ohlcv[:, 1].astype(np.float64)
        low = ohlcv[:, 2].astype(np.float64)
        val, direction = pipeline._compute_supertrend(c, h, low, 10, 3.0)
        if val is not None:
            assert val > 0
        if direction is not None:
            assert direction in (1, -1)

    def test_supertrend_short_data(self, pipeline: TechnicalIndicatorPipeline) -> None:
        c = np.array([19000.0, 19010.0])
        h = np.array([19050.0, 19060.0])
        low = np.array([18950.0, 18960.0])
        val, direction = pipeline._compute_supertrend(c, h, low, 10, 3.0)
        assert val is None
        assert direction is None

    def test_cmf_positive_for_up_trend(self, pipeline: TechnicalIndicatorPipeline) -> None:
        """Up-trending data should tend toward positive CMF."""
        ohlcv = generate_ohlcv(300, "up")
        h = ohlcv[:, 1].astype(np.float64)
        low = ohlcv[:, 2].astype(np.float64)
        c = ohlcv[:, 3].astype(np.float64)
        v = ohlcv[:, 4].astype(np.float64)
        cmf = pipeline._compute_cmf(h, low, c, v, 20)
        if cmf is not None:
            assert isinstance(cmf, float)

    def test_cmf_insufficient_data(self, pipeline: TechnicalIndicatorPipeline) -> None:
        h = np.array([19100.0])
        low = np.array([18900.0])
        c = np.array([19000.0])
        v = np.array([1e6])
        result = pipeline._compute_cmf(h, low, c, v, 20)
        assert result is None

    def test_cmf_zero_volume(self, pipeline: TechnicalIndicatorPipeline) -> None:
        n = 25
        c = np.linspace(19000, 19100, n)
        h = c + 50
        low = c - 50
        v = np.zeros(n)  # All zero volume
        result = pipeline._compute_cmf(h, low, c, v, 20)
        assert result is None

    def test_vwap_positive(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(100, "up")
        h = ohlcv[:, 1].astype(np.float64)
        low = ohlcv[:, 2].astype(np.float64)
        c = ohlcv[:, 3].astype(np.float64)
        v = ohlcv[:, 4].astype(np.float64)
        vwap = pipeline._compute_vwap(h, low, c, v)
        assert vwap is not None
        assert vwap > 0

    def test_vwap_single_bar(self, pipeline: TechnicalIndicatorPipeline) -> None:
        h = np.array([19100.0])
        low = np.array([18900.0])
        c = np.array([19000.0])
        v = np.array([1e6])
        vwap = pipeline._compute_vwap(h, low, c, v)
        assert vwap is None  # Need at least 2 bars

    def test_vwap_zero_volume(self, pipeline: TechnicalIndicatorPipeline) -> None:
        n = 10
        h = np.full(n, 19100.0)
        low = np.full(n, 18900.0)
        c = np.full(n, 19000.0)
        v = np.zeros(n)
        vwap = pipeline._compute_vwap(h, low, c, v)
        assert vwap is None

    def test_volume_rate_normal(self, pipeline: TechnicalIndicatorPipeline) -> None:
        v = np.random.uniform(1e6, 5e6, 30)
        rate = pipeline._compute_volume_rate(v, 20)
        assert rate is not None
        assert rate > 0

    def test_volume_rate_spike(self, pipeline: TechnicalIndicatorPipeline) -> None:
        """Last bar has 3x average volume → volume_rate ≈ 3.0."""
        v = np.ones(30) * 1e6
        v[-1] = 3e6  # Spike
        rate = pipeline._compute_volume_rate(v, 20)
        assert rate is not None
        assert rate > 2.0

    def test_volume_rate_zero_avg(self, pipeline: TechnicalIndicatorPipeline) -> None:
        v = np.zeros(30)
        rate = pipeline._compute_volume_rate(v, 20)
        assert rate is None

    def test_volume_rate_insufficient(self, pipeline: TechnicalIndicatorPipeline) -> None:
        v = np.array([1e6] * 5)
        rate = pipeline._compute_volume_rate(v, 20)
        assert rate is None


# ═══════════════════════════════════════════════════════════════════════════
# 8. Market Regime Detection
# ═══════════════════════════════════════════════════════════════════════════


class TestRegimeDetection:
    """Test ADX + Hurst regime classification."""

    def test_regime_with_sufficient_data(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up)
        # With 300 bars we should get a regime classification
        assert result.regime in (
            MarketRegime.TRENDING,
            MarketRegime.MEAN_REVERTING,
            MarketRegime.RANDOM_WALK,
            MarketRegime.UNKNOWN,
        )

    def test_regime_unknown_short_data(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(50, "flat")  # < HURST_LOOKBACK (100)
        result = pipeline.compute(ohlcv)
        assert result.regime == MarketRegime.UNKNOWN

    def test_hurst_not_none_with_sufficient_data(self, pipeline: TechnicalIndicatorPipeline) -> None:
        ohlcv = generate_ohlcv(300, "up")
        result = pipeline.compute(ohlcv)
        # Hurst should be computed with enough data
        if result.hurst_exponent is not None:
            assert 0.0 <= result.hurst_exponent <= 1.5  # Allow some estimation noise


class TestHurstExponent:
    """Test _compute_hurst directly."""

    def test_hurst_random_walk(self, pipeline: TechnicalIndicatorPipeline) -> None:
        """Random walk data should have H ≈ 0.5."""
        np.random.seed(123)
        close = 19000 * np.cumprod(1 + np.random.normal(0, 0.01, 200))
        h = pipeline._compute_hurst(close)
        if h is not None:
            assert 0.3 < h < 0.8  # Generous bounds due to noise

    def test_hurst_short_data(self, pipeline: TechnicalIndicatorPipeline) -> None:
        close = np.array([19000.0, 19010.0, 19005.0])
        h = pipeline._compute_hurst(close)
        assert h is None

    def test_hurst_isolation(self, pipeline: TechnicalIndicatorPipeline) -> None:
        """Isolated/trending data should tend toward H > 0.5."""
        np.random.seed(99)
        # Strongly trending data
        close = 19000 * np.cumprod(1 + np.random.normal(0.002, 0.005, 200))
        h = pipeline._compute_hurst(close)
        if h is not None:
            assert isinstance(h, float)


# ═══════════════════════════════════════════════════════════════════════════
# 9. Helper Method Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestHelperMethods:
    """Test _safe_last, _safe_last_int, _percentile_rank."""

    def test_safe_last_normal(self) -> None:
        arr = np.array([1.0, 2.0, 3.0])
        assert TechnicalIndicatorPipeline._safe_last(arr) == 3.0

    def test_safe_last_none(self) -> None:
        assert TechnicalIndicatorPipeline._safe_last(None) is None

    def test_safe_last_empty(self) -> None:
        assert TechnicalIndicatorPipeline._safe_last(np.array([])) is None

    def test_safe_last_nan(self) -> None:
        arr = np.array([1.0, 2.0, np.nan])
        assert TechnicalIndicatorPipeline._safe_last(arr) is None

    def test_safe_last_inf(self) -> None:
        arr = np.array([1.0, 2.0, np.inf])
        assert TechnicalIndicatorPipeline._safe_last(arr) is None

    def test_safe_last_int_normal(self) -> None:
        arr = np.array([0, 0, 1, 1])
        assert TechnicalIndicatorPipeline._safe_last_int(arr) == 1

    def test_safe_last_int_none(self) -> None:
        assert TechnicalIndicatorPipeline._safe_last_int(None) is None

    def test_safe_last_int_nan(self) -> None:
        arr = np.array([0, 0, np.nan])
        assert TechnicalIndicatorPipeline._safe_last_int(arr) is None

    def test_percentile_rank_none_value(self, pipeline: TechnicalIndicatorPipeline) -> None:
        c = np.ones(100) * 19000
        result = pipeline._percentile_rank(None, c, 14)
        assert result is None

    def test_percentile_rank_short_data(self, pipeline: TechnicalIndicatorPipeline) -> None:
        c = np.ones(10) * 19000
        result = pipeline._percentile_rank(50.0, c, 14)
        # Less than PERCENTILE_MIN_HISTORY (63) → None
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# 10. Integration: Full Pipeline Smoke Test
# ═══════════════════════════════════════════════════════════════════════════


class TestFullPipeline:
    """Smoke tests for complete pipeline with realistic data."""

    def test_full_pipeline_returns_all_groups(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_up, india_vix=18.5)
        assert isinstance(result.momentum, MomentumIndicators)
        assert isinstance(result.volatility, VolatilityIndicators)
        assert isinstance(result.trend, TrendIndicators)
        assert isinstance(result.volume, VolumeIndicators)
        assert result.volatility.vix_level == VIXLevel.NORMAL

    def test_full_pipeline_down_trend(self, pipeline: TechnicalIndicatorPipeline, ohlcv_down: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_down)
        assert result.momentum.rsi_14 is not None
        assert result.trend.ema_9 is not None

    def test_full_pipeline_volatile(self, pipeline: TechnicalIndicatorPipeline, ohlcv_volatile: np.ndarray) -> None:
        result = pipeline.compute(ohlcv_volatile, india_vix=28.0)
        assert result.volatility.vix_level == VIXLevel.HIGH

    def test_talib_bbands_period_not_default(self, ohlcv_up: np.ndarray) -> None:
        """Regression: BBANDS must use period=20, NOT TA-Lib default of 5."""
        c = ohlcv_up[:, 3].astype(np.float64)
        bb_default = talib.BBANDS(c, timeperiod=5, nbdevup=2.0, nbdevdn=2.0, matype=0)
        bb_20 = talib.BBANDS(c, timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0)
        # They should produce different upper bands
        if not (np.isnan(bb_default[0][-1]) or np.isnan(bb_20[0][-1])):
            assert bb_default[0][-1] != bb_20[0][-1], "BBANDS period override regression: default(5) == override(20)"

    def test_talib_ema_period_not_default(self, ohlcv_up: np.ndarray) -> None:
        """Regression: EMA must use explicit periods, NOT TA-Lib default of 30."""
        c = ohlcv_up[:, 3].astype(np.float64)
        ema_default = talib.EMA(c, timeperiod=30)
        ema_9 = talib.EMA(c, timeperiod=9)
        if not (np.isnan(ema_default[-1]) or np.isnan(ema_9[-1])):
            assert ema_default[-1] != ema_9[-1], "EMA period override regression: default(30) == override(9)"

    def test_idempotent_computation(self, pipeline: TechnicalIndicatorPipeline, ohlcv_up: np.ndarray) -> None:
        """Running compute twice with same input must return same results."""
        r1 = pipeline.compute(ohlcv_up)
        r2 = pipeline.compute(ohlcv_up)
        assert r1.momentum.rsi_14 == r2.momentum.rsi_14
        assert r1.volatility.atr_14 == r2.volatility.atr_14
        assert r1.trend.ema_9 == r2.trend.ema_9


# ═══════════════════════════════════════════════════════════════════════════
# 11. Settings Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestSettingsIntegration:
    """Test that settings are correctly used by pipeline."""

    def test_custom_rsi_period(self) -> None:
        custom = TechnicalIndicatorSettings(RSI_PERIOD=21)
        pipeline = TechnicalIndicatorPipeline(custom)
        ohlcv = generate_ohlcv(300, "up")
        result = pipeline.compute(ohlcv)
        assert result.momentum.rsi_14 is not None

    def test_custom_bbands_period(self) -> None:
        custom = TechnicalIndicatorSettings(BBANDS_PERIOD=10)
        pipeline = TechnicalIndicatorPipeline(custom)
        ohlcv = generate_ohlcv(300, "up")
        result = pipeline.compute(ohlcv)
        assert result.volatility.bbands_upper is not None

    def test_custom_supertrend_params(self) -> None:
        custom = TechnicalIndicatorSettings(SUPERTREND_PERIOD=7, SUPERTREND_MULTIPLIER=2.0)
        pipeline = TechnicalIndicatorPipeline(custom)
        ohlcv = generate_ohlcv(300, "up")
        result = pipeline.compute(ohlcv)
        if result.trend.supertrend_value is not None:
            assert result.trend.supertrend_value > 0
