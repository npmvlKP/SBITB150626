"""Property-based tests for Phase 3 technical indicators using Hypothesis.

Uses the ohlcv_strategy to generate random OHLCV data and verifies
invariant properties of all indicators.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from config.settings import TechnicalIndicatorSettings
from src.analysis.technical import TechnicalIndicatorPipeline


def _generate_ohlcv(
    n: int,
    base_price: float,
    vol_scale: float,
) -> np.ndarray:
    """Generate OHLCV data with realistic constraints.

    Args:
        n: Number of bars.
        base_price: Starting price level.
        vol_scale: Volume scaling factor.

    Returns:
        ndarray shape (N, 5) with columns [open, high, low, close, volume].
    """
    rng = np.random.default_rng(42)
    close = base_price + np.cumsum(rng.standard_normal(n) * base_price * 0.01)
    close = np.maximum(close, base_price * 0.5)  # Ensure positive
    high = close + np.abs(rng.standard_normal(n) * base_price * 0.02)
    low = close - np.abs(rng.standard_normal(n) * base_price * 0.02)
    open_ = close + rng.standard_normal(n) * base_price * 0.005
    open_ = np.clip(open_, low, high)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    volume = np.abs(rng.standard_normal(n)) * vol_scale + 1000
    return np.column_stack([open_, high, low, close, volume]).astype(np.float64)


# Strategy: generate OHLCV data with realistic constraints
ohlcv_strategy = st.builds(
    _generate_ohlcv,
    n=st.integers(min_value=50, max_value=500),
    base_price=st.floats(min_value=100, max_value=50000, allow_nan=False, allow_infinity=False),
    vol_scale=st.floats(min_value=1000, max_value=10000000, allow_nan=False, allow_infinity=False),
)


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_rsi_always_in_0_100(ohlcv: np.ndarray) -> None:
    """RSI ∈ [0, 100] or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)
    rsi = result.momentum.rsi_14
    if rsi is not None:
        assert 0.0 <= rsi <= 100.0


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_adx_always_in_0_100(ohlcv: np.ndarray) -> None:
    """ADX ∈ [0, 100] or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)
    adx = result.momentum.adx_14
    if adx is not None:
        assert 0.0 <= adx <= 100.0


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_mfi_always_in_0_100(ohlcv: np.ndarray) -> None:
    """MFI ∈ [0, 100] or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)
    mfi = result.volume.mfi_14
    if mfi is not None:
        assert 0.0 <= mfi <= 100.0


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_cmf_always_in_neg1_1(ohlcv: np.ndarray) -> None:
    """CMF ∈ [-1, 1] or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)
    cmf = result.volume.cmf_20
    if cmf is not None:
        assert -1.0 <= cmf <= 1.0


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_bbands_width_positive(ohlcv: np.ndarray) -> None:
    """BB width > 0 or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)
    width = result.volatility.bbands_width
    if width is not None:
        assert width > 0


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_atr_always_non_negative(ohlcv: np.ndarray) -> None:
    """ATR ≥ 0 or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)
    atr = result.volatility.atr_14
    if atr is not None:
        assert atr >= 0


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_supertrend_direction_is_plus_minus_1(ohlcv: np.ndarray) -> None:
    """direction ∈ {-1, +1} or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)
    direction = result.trend.supertrend_direction
    if direction is not None:
        assert direction in (-1, 1)


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_hurst_in_valid_range(ohlcv: np.ndarray) -> None:
    """Hurst ∈ (0, 1) or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)
    hurst = result.hurst_exponent
    if hurst is not None:
        assert 0.0 < hurst < 1.0


@given(ohlcv_strategy)
@settings(max_examples=50)
def test_no_indicator_returns_nan(ohlcv: np.ndarray) -> None:
    """No indicator value is ever NaN — must be float or None."""
    pipeline = TechnicalIndicatorPipeline(TechnicalIndicatorSettings())
    result = pipeline.compute(ohlcv)

    # Recursively check all fields for NaN
    def _check_nan(obj: object, path: str = "") -> None:
        if isinstance(obj, int | float) and not isinstance(obj, bool):
            assert not np.isnan(obj), f"NaN found at {path}: {obj}"
        elif isinstance(obj, np.ndarray):
            assert not np.any(np.isnan(obj)), f"NaN in array at {path}"
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _check_nan(item, f"{path}[{i}]")

    # Check all indicator sub-models
    for group_name in ("momentum", "volatility", "trend", "volume"):
        group = getattr(result, group_name, None)
        if group is not None:
            for field_name in type(group).model_fields:
                val = getattr(group, field_name)
                if val is not None:
                    _check_nan(val, f"{group_name}.{field_name}")

    # Check top-level fields
    _check_nan(result.hurst_exponent, "hurst_exponent")
