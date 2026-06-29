"""Pure-Python technical indicators — no TA-Lib C library dependency.

Implements the same indicators as src/analysis/technical.py but using only
numpy + scipy (both available in OpenAlgo's environment).

Book references:
- Kaufman Ch.2-8: Signal design, indicator construction
- Wilder (1978): RSI, ATR EWMA smoothing (alpha=1/period)
- Chan Ch.1-4: Regime switching via ADX + Hurst

All functions return ``None`` when insufficient data is available, matching
the fail-safe behavior of the main project's TA-Lib pipeline.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray


class MomentumResult(NamedTuple):
    rsi: float | None
    macd_line: float | None
    macd_signal: float | None
    macd_hist: float | None
    adx: float | None


class VolatilityResult(NamedTuple):
    bbands_upper: float | None
    bbands_middle: float | None
    bbands_lower: float | None
    atr: float | None


class TrendResult(NamedTuple):
    ema_fast: float | None
    ema_slow: float | None
    ema_signal: int | None  # +1 bullish, -1 bearish
    supertrend_value: float | None
    supertrend_direction: int | None  # +1 bullish, -1 bearish


# ═══════════════════════════════════════════════════════════════════════
# Smoothing primitives
# ═══════════════════════════════════════════════════════════════════════


def _wilder_smooth(values: NDArray[np.float64], period: int) -> NDArray[np.float64]:
    """Wilder smoothing = EWMA with alpha = 1/period (NOT simple RMA).

    Reference: Wilder (1978) — used by RSI, ATR, ADX.
    Seed: simple average of first `period` values.
    """
    if len(values) < period:
        return np.array([], dtype=np.float64)

    alpha = 1.0 / period
    out = np.full(len(values), np.nan, dtype=np.float64)
    # Seed from first window with no NaN (handles leading NaN in DX/DI arrays)
    seed_idx: int | None = None
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        if not np.any(np.isnan(window)):
            out[i] = np.mean(window)
            seed_idx = i + 1
            break
    if seed_idx is None:
        return out
    for i in range(seed_idx, len(values)):
        if np.isnan(values[i]):
            continue
        prev = out[i - 1]
        if np.isnan(prev):
            out[i] = values[i]
        else:
            out[i] = alpha * values[i] + (1 - alpha) * prev
    return out


def _ema(values: NDArray[np.float64], period: int) -> NDArray[np.float64]:
    """Exponential Moving Average (standard EWMA)."""
    if len(values) < period:
        return np.array([], dtype=np.float64)
    alpha = 2.0 / (period + 1)
    out = np.full(len(values), np.nan, dtype=np.float64)
    out[period - 1] = np.mean(values[:period])
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _sma(values: NDArray[np.float64], period: int) -> NDArray[np.float64]:
    """Simple Moving Average."""
    if len(values) < period:
        return np.array([], dtype=np.float64)
    cumsum = np.cumsum(values, dtype=np.float64)
    cumsum[period:] = cumsum[period:] - cumsum[:-period]
    out = np.full(len(values), np.nan, dtype=np.float64)
    out[period - 1 :] = cumsum[period - 1 :] / period
    return out


def _safe_last(arr: NDArray[np.float64]) -> float | None:
    """Extract last non-NaN value, or None if array is empty/NaN/inf."""
    if arr is None or len(arr) == 0:
        return None
    val = arr[-1]
    if np.isnan(val) or np.isinf(val):
        return None
    return float(val)


def _true_range(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> NDArray[np.float64]:
    """True Range: max(H-L, |H-prev_C|, |L-prev_C|)."""
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)
    return np.maximum(tr1, np.maximum(tr2, tr3))


# ═══════════════════════════════════════════════════════════════════════
# Momentum indicators
# ═══════════════════════════════════════════════════════════════════════


def compute_rsi(close: NDArray[np.float64], period: int = 14) -> float | None:
    """RSI using Wilder smoothing (alpha=1/period).

    Reference: Wilder (1978), Kaufman Ch.4.
    """
    if len(close) < period + 1:
        return None
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = _wilder_smooth(gains, period)
    avg_loss = _wilder_smooth(losses, period)
    if len(avg_gain) == 0:
        return None
    last_gain = avg_gain[-1]
    last_loss = avg_loss[-1]
    if np.isnan(last_gain) or np.isnan(last_loss):
        return None
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def compute_macd(
    close: NDArray[np.float64],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float | None, float | None, float | None]:
    """MACD = EMA(fast) - EMA(slow), signal = EMA(signal) of MACD line."""
    if len(close) < slow + signal:
        return None, None, None
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    valid = ~(np.isnan(ema_fast) | np.isnan(ema_slow))
    macd_line = np.where(valid, ema_fast - ema_slow, np.nan)
    valid_macd = macd_line[~np.isnan(macd_line)]
    if len(valid_macd) < signal:
        return None, None, None
    signal_full = _ema(valid_macd, signal)
    return _safe_last(macd_line), _safe_last(signal_full), None


def compute_adx(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    period: int = 14,
) -> float | None:
    """ADX via Wilder smoothing — trend strength [0, 100]."""
    if len(close) < 2 * period:
        return None

    up_move = np.diff(high, prepend=high[0])
    down_move = np.diff(-low, prepend=-low[0])

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _true_range(high, low, close)
    atr_full = _wilder_smooth(tr, period)
    plus_dm_s = _wilder_smooth(plus_dm, period)
    minus_dm_s = _wilder_smooth(minus_dm, period)

    valid = ~(np.isnan(atr_full) | np.isnan(plus_dm_s) | np.isnan(minus_dm_s))
    if np.sum(valid) < period:
        return None

    safe_atr = np.where(atr_full > 0, atr_full, 1e-10)
    plus_di = 100.0 * plus_dm_s / safe_atr
    minus_di = 100.0 * minus_dm_s / safe_atr
    dx_denom = plus_di + minus_di
    safe_denom = np.where(dx_denom > 0, dx_denom, 1e-10)
    dx = 100.0 * np.abs(plus_di - minus_di) / safe_denom

    adx_arr = _wilder_smooth(dx, period)
    return _safe_last(adx_arr)


# ═══════════════════════════════════════════════════════════════════════
# Volatility indicators
# ═══════════════════════════════════════════════════════════════════════


def compute_atr(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    period: int = 14,
) -> float | None:
    """ATR via Wilder smoothing."""
    if len(close) < period + 1:
        return None
    tr = _true_range(high, low, close)
    atr = _wilder_smooth(tr, period)
    return _safe_last(atr)


def compute_bbands(
    close: NDArray[np.float64],
    period: int = 20,
    stddev: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    """Bollinger Bands (SMA-based, TA-Lib default=5 — override to 20)."""
    if len(close) < period:
        return None, None, None
    sma = _sma(close, period)
    if len(sma) < len(close):
        return None, None, None
    rolling_std = np.full(len(close), np.nan, dtype=np.float64)
    for i in range(period - 1, len(close)):
        rolling_std[i] = np.std(close[i - period + 1 : i + 1], ddof=0)
    upper = sma + stddev * rolling_std
    lower = sma - stddev * rolling_std
    return _safe_last(upper), _safe_last(sma), _safe_last(lower)


# ═══════════════════════════════════════════════════════════════════════
# Trend indicators
# ═══════════════════════════════════════════════════════════════════════


def compute_ema_pair(
    close: NDArray[np.float64],
    fast: int = 9,
    slow: int = 21,
) -> tuple[float | None, float | None, int | None]:
    """EMA crossover signal: +1 if fast>slow, -1 if fast<slow."""
    ema_f = _ema(close, fast)
    ema_s = _ema(close, slow)
    last_f = _safe_last(ema_f)
    last_s = _safe_last(ema_s)
    signal = None
    if last_f is not None and last_s is not None:
        signal = 1 if last_f > last_s else -1
    return last_f, last_s, signal


def compute_supertrend(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[float | None, int | None]:
    """Supertrend using Wilder-smoothed ATR (NOT simple RMA)."""
    if len(close) < period + 1:
        return None, None
    tr = _true_range(high, low, close)
    atr = _wilder_smooth(tr, period)
    hl2 = (high + low) / 2.0
    upper_band = np.full(len(close), np.nan)
    lower_band = np.full(len(close), np.nan)
    direction = np.zeros(len(close), dtype=int)

    for i in range(period, len(close)):
        if np.isnan(atr[i]):
            continue
        basic_upper = hl2[i] + multiplier * atr[i]
        basic_lower = hl2[i] - multiplier * atr[i]
        upper_band[i] = (
            basic_upper
            if (i == period or np.isnan(upper_band[i - 1]) or close[i - 1] > upper_band[i - 1])
            else min(basic_upper, upper_band[i - 1])
        )
        lower_band[i] = (
            basic_lower
            if (i == period or np.isnan(lower_band[i - 1]) or close[i - 1] < lower_band[i - 1])
            else max(basic_lower, lower_band[i - 1])
        )
        if i == period:
            direction[i] = 1 if close[i] > upper_band[i] else -1
        elif direction[i - 1] == 1:
            direction[i] = -1 if close[i] < lower_band[i] else 1
        else:
            direction[i] = 1 if close[i] > upper_band[i] else -1

    st_value = np.where(direction == 1, lower_band, upper_band)
    return _safe_last(st_value), int(direction[-1]) if len(direction) > 0 else None


# ═══════════════════════════════════════════════════════════════════════
# Regime detection
# ═══════════════════════════════════════════════════════════════════════


def compute_hurst(close: NDArray[np.float64]) -> float | None:
    """Hurst exponent via R/S (Rescaled Range) analysis.

    H < 0.5 = mean-reverting, H > 0.5 = trending, H approx 0.5 = random walk.
    """
    try:
        from scipy import stats as sp_stats
    except ImportError:
        return None

    if len(close) < 100:
        return None
    returns = np.diff(np.log(close))
    if len(returns) < 50:
        return None

    window_sizes = [10, 20, 50, 100]
    rs_values: list[tuple[int, float]] = []
    for w in window_sizes:
        if w > len(returns):
            continue
        num_subseries = len(returns) // w
        if num_subseries < 1:
            continue
        rs_subseries: list[float] = []
        for i in range(num_subseries):
            subset = returns[i * w : (i + 1) * w]
            mean_sub = np.mean(subset)
            deviations = np.cumsum(subset - mean_sub)
            r = np.max(deviations) - np.min(deviations)
            s = np.std(subset, ddof=1)
            if s > 0:
                rs_subseries.append(float(r / s))
        if rs_subseries:
            rs_values.append((w, float(np.mean(rs_subseries))))

    if len(rs_values) < 2:
        return None
    log_n = np.log([x[0] for x in rs_values])
    log_rs = np.log([x[1] for x in rs_values])
    slope, _, _, _, _ = sp_stats.linregress(log_n, log_rs)
    return float(slope)


def detect_regime(
    close: NDArray[np.float64],
    adx: float | None,
    adx_threshold: float = 25.0,
    hurst_threshold: float = 0.5,
) -> str:
    """Classify market regime: TRENDING / MEAN_REVERTING / RANDOM_WALK / UNKNOWN."""
    hurst = compute_hurst(close)
    if adx is None or hurst is None:
        return "UNKNOWN"
    if adx > adx_threshold and hurst > hurst_threshold:
        return "TRENDING"
    if adx <= adx_threshold and hurst < hurst_threshold:
        return "MEAN_REVERTING"
    return "RANDOM_WALK"
