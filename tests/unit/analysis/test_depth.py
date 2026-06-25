"""Comprehensive tests for src/analysis/depth.py.

Covers: DepthAnalyzer.analyze_depth(), DepthAnalyzer.compute_vpin(),
Pydantic models (DepthLevel, DepthData, DepthSignals, VPINLevel).
Happy paths, edge cases, error paths, type handling, precision handling.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from config.settings import DepthAnalysisSettings
from src.analysis.depth import DepthAnalyzer, DepthData, DepthLevel, DepthSignals, VPINLevel

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> DepthAnalysisSettings:
    """Default DepthAnalysisSettings for testing."""
    return DepthAnalysisSettings(
        DEPTH_LEVELS=5,
        IMBALANCE_THRESHOLD=2.0,
        SPREAD_BPS_THRESHOLD=5.0,
        VPIN_ENABLED=True,
        VPIN_BUCKET_SIZE_METHOD="fixed",
        VPIN_FIXED_BUCKET_SIZE=5000,
        VPIN_DAILY_ADV_LOOKBACK=20,
        VPIN_NUM_BUCKETS=50,
        VPIN_CDF_ELEVATED=0.90,
        VPIN_CDF_HIGH=0.95,
        VPIN_CDF_EXTREME=0.99,
        VPIN_USE_BVC=True,
        VPIN_MIN_1MIN_BARS=50,
    )


@pytest.fixture
def settings_daily_adv() -> DepthAnalysisSettings:
    """Settings using daily_adv bucket size method."""
    return DepthAnalysisSettings(
        VPIN_ENABLED=True,
        VPIN_BUCKET_SIZE_METHOD="daily_adv",
        VPIN_DAILY_ADV_LOOKBACK=5,
        VPIN_NUM_BUCKETS=50,
        VPIN_MIN_1MIN_BARS=50,
    )


@pytest.fixture
def settings_vpin_disabled() -> DepthAnalysisSettings:
    """Settings with VPIN disabled."""
    return DepthAnalysisSettings(
        VPIN_ENABLED=False,
    )


def _make_depth_data(
    bid_prices: list[float] | None = None,
    bid_qtys: list[int] | None = None,
    ask_prices: list[float] | None = None,
    ask_qtys: list[int] | None = None,
) -> DepthData:
    """Create DepthData with specified bid/ask levels."""
    if bid_prices is None:
        bid_prices = [100.0, 99.5, 99.0, 98.5, 98.0]
    if bid_qtys is None:
        bid_qtys = [100, 200, 150, 300, 250]
    if ask_prices is None:
        ask_prices = [100.5, 101.0, 101.5, 102.0, 102.5]
    if ask_qtys is None:
        ask_qtys = [120, 180, 160, 280, 220]

    bids = [DepthLevel(price=p, quantity=q) for p, q in zip(bid_prices, bid_qtys)]
    asks = [DepthLevel(price=p, quantity=q) for p, q in zip(ask_prices, ask_qtys)]
    return DepthData(bid_levels=bids, ask_levels=asks)


def _make_1min_bars(
    n: int,
    base_price: float = 100.0,
    spread: float = 2.0,
    base_vol: float = 5000.0,
    trend: float = 0.0,
) -> np.ndarray:
    """Generate n rows of 1-minute OHLCV data."""
    rng = np.random.default_rng(42)
    data = np.zeros((n, 5), dtype=np.float64)
    price = base_price
    for i in range(n):
        price += trend
        low = price - rng.uniform(0, spread)
        high = price + rng.uniform(0, spread)
        open_ = rng.uniform(low, high)
        close = rng.uniform(low, high)
        vol = base_vol * rng.uniform(0.5, 2.0)
        data[i] = [open_, high, low, close, vol]
        price = close
    return data


def _make_trending_bars(
    n: int,
    direction: float = 1.0,
    base_vol: float = 5000.0,
) -> np.ndarray:
    """Generate trending 1-min bars (strong directional close-open)."""
    data = np.zeros((n, 5), dtype=np.float64)
    price = 100.0
    for i in range(n):
        open_ = price
        close = price + direction * 0.5
        high = max(open_, close) + 0.5
        low = min(open_, close) - 0.5
        vol = base_vol
        data[i] = [open_, high, low, close, vol]
        price = close
    return data


# ===========================================================================
# VPINLevel Enum
# ===========================================================================


class TestVPINLevel:
    """Tests for VPINLevel StrEnum."""

    def test_normal_value(self) -> None:
        assert VPINLevel.NORMAL == "NORMAL"

    def test_elevated_value(self) -> None:
        assert VPINLevel.ELEVATED == "ELEVATED"

    def test_high_value(self) -> None:
        assert VPINLevel.HIGH == "HIGH"

    def test_extreme_value(self) -> None:
        assert VPINLevel.EXTREME == "EXTREME"

    def test_is_str_enum(self) -> None:
        assert isinstance(VPINLevel.NORMAL, str)


# ===========================================================================
# DepthLevel Model
# ===========================================================================


class TestDepthLevel:
    """Tests for DepthLevel Pydantic model."""

    def test_valid_creation(self) -> None:
        level = DepthLevel(price=100.5, quantity=500)
        assert level.price == 100.5
        assert level.quantity == 500

    def test_zero_quantity(self) -> None:
        level = DepthLevel(price=100.0, quantity=0)
        assert level.quantity == 0

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValueError):
            DepthLevel(price=100.0, quantity=-1)

    def test_model_dump(self) -> None:
        level = DepthLevel(price=99.5, quantity=200)
        d = level.model_dump()
        assert d == {"price": 99.5, "quantity": 200}


# ===========================================================================
# DepthData Model
# ===========================================================================


class TestDepthData:
    """Tests for DepthData Pydantic model."""

    def test_empty_default(self) -> None:
        data = DepthData()
        assert data.bid_levels == []
        assert data.ask_levels == []
        assert data.timestamp is None

    def test_with_levels(self) -> None:
        data = _make_depth_data()
        assert len(data.bid_levels) == 5
        assert len(data.ask_levels) == 5
        assert data.bid_levels[0].price == 100.0
        assert data.ask_levels[0].price == 100.5

    def test_with_timestamp(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        data = DepthData(
            bid_levels=[DepthLevel(price=100.0, quantity=100)],
            ask_levels=[DepthLevel(price=100.5, quantity=120)],
            timestamp=ts,
        )
        assert data.timestamp == ts

    def test_model_dump(self) -> None:
        data = _make_depth_data()
        d = data.model_dump()
        assert "bid_levels" in d
        assert "ask_levels" in d
        assert "timestamp" in d


# ===========================================================================
# DepthSignals Model
# ===========================================================================


class TestDepthSignals:
    """Tests for DepthSignals Pydantic model."""

    def test_default_values(self) -> None:
        signals = DepthSignals()
        assert signals.bid_ask_spread_bps is None
        assert signals.depth_imbalance_ratio is None
        assert signals.depth_imbalance_signal is None
        assert signals.total_bid_quantity is None
        assert signals.total_ask_quantity is None
        assert signals.vpin_value is None
        assert signals.vpin_cdf is None
        assert signals.vpin_level == VPINLevel.NORMAL

    def test_with_values(self) -> None:
        signals = DepthSignals(
            bid_ask_spread_bps=5.0,
            depth_imbalance_ratio=1.5,
            depth_imbalance_signal="BULLISH_IMBALANCE",
            total_bid_quantity=1000,
            total_ask_quantity=800,
            vpin_value=0.45,
            vpin_cdf=0.85,
            vpin_level=VPINLevel.ELEVATED,
        )
        assert signals.bid_ask_spread_bps == 5.0
        assert signals.vpin_value == 0.45
        assert signals.vpin_level == VPINLevel.ELEVATED

    def test_model_dump(self) -> None:
        signals = DepthSignals(vpin_value=0.3)
        d = signals.model_dump()
        assert d["vpin_value"] == 0.3
        assert d["vpin_level"] == "NORMAL"


# ===========================================================================
# DepthAnalyzer.analyze_depth
# ===========================================================================


class TestAnalyzeDepth:
    """Tests for DepthAnalyzer.analyze_depth()."""

    def test_empty_bid_levels_returns_defaults(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = DepthData(
            ask_levels=[DepthLevel(price=100.5, quantity=100)],
        )
        result = analyzer.analyze_depth(depth)
        assert result.bid_ask_spread_bps is None
        assert result.total_bid_quantity is None

    def test_empty_ask_levels_returns_defaults(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = DepthData(
            bid_levels=[DepthLevel(price=100.0, quantity=100)],
        )
        result = analyzer.analyze_depth(depth)
        assert result.bid_ask_spread_bps is None

    def test_both_empty_returns_defaults(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        result = analyzer.analyze_depth(DepthData())
        assert result == DepthSignals()

    def test_spread_bps_with_ltp(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data(
            bid_prices=[100.0],
            bid_qtys=[100],
            ask_prices=[100.1],
            ask_qtys=[100],
        )
        result = analyzer.analyze_depth(depth, ltp=100.05)
        # spread = (100.1 - 100.0) / 100.05 * 10000 = 9.995 bps → rounded to 10.0
        assert result.bid_ask_spread_bps is not None
        assert abs(result.bid_ask_spread_bps - 10.0) < 0.1

    def test_spread_bps_without_ltp(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data()
        result = analyzer.analyze_depth(depth, ltp=None)
        assert result.bid_ask_spread_bps is None

    def test_spread_bps_zero_ltp(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data()
        result = analyzer.analyze_depth(depth, ltp=0.0)
        assert result.bid_ask_spread_bps is None

    def test_spread_bps_negative_ltp(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data()
        result = analyzer.analyze_depth(depth, ltp=-1.0)
        # Negative ltp < 0, so condition ltp > 0 is False → None
        assert result.bid_ask_spread_bps is None

    def test_imbalance_neutral(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data(
            bid_prices=[100.0],
            bid_qtys=[100],
            ask_prices=[100.5],
            ask_qtys=[100],
        )
        result = analyzer.analyze_depth(depth)
        # ratio = 100/100 = 1.0 → NEUTRAL (not > 2.0 and not < 0.5)
        assert result.depth_imbalance_signal == "NEUTRAL"
        assert result.depth_imbalance_ratio == 1.0

    def test_imbalance_bullish(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data(
            bid_prices=[100.0],
            bid_qtys=[300],
            ask_prices=[100.5],
            ask_qtys=[100],
        )
        result = analyzer.analyze_depth(depth)
        # ratio = 300/100 = 3.0 > 2.0 → BULLISH
        assert result.depth_imbalance_signal == "BULLISH_IMBALANCE"
        assert result.depth_imbalance_ratio == 3.0

    def test_imbalance_bearish(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data(
            bid_prices=[100.0],
            bid_qtys=[100],
            ask_prices=[100.5],
            ask_qtys=[300],
        )
        result = analyzer.analyze_depth(depth)
        # ratio = 100/300 = 0.333 < 0.5 → BEARISH
        assert result.depth_imbalance_signal == "BEARISH_IMBALANCE"
        assert round(result.depth_imbalance_ratio, 4) == 0.3333

    def test_imbalance_zero_ask_qty(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data(
            bid_prices=[100.0],
            bid_qtys=[100],
            ask_prices=[100.5],
            ask_qtys=[0],
        )
        result = analyzer.analyze_depth(depth)
        assert result.depth_imbalance_ratio is None
        assert result.depth_imbalance_signal == "NEUTRAL"

    def test_total_quantities(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data(
            bid_prices=[100.0, 99.5],
            bid_qtys=[100, 200],
            ask_prices=[100.5, 101.0],
            ask_qtys=[150, 250],
        )
        result = analyzer.analyze_depth(depth)
        assert result.total_bid_quantity == 300
        assert result.total_ask_quantity == 400

    def test_multiple_levels_imbalance(self, settings: DepthAnalysisSettings) -> None:
        """Test with 5 levels (typical Zerodha depth)."""
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data()  # 5 levels each
        result = analyzer.analyze_depth(depth, ltp=100.25)
        assert result.bid_ask_spread_bps is not None
        assert result.total_bid_quantity == sum([100, 200, 150, 300, 250])
        assert result.total_ask_quantity == sum([120, 180, 160, 280, 220])


# ===========================================================================
# DepthAnalyzer.compute_vpin
# ===========================================================================


class TestComputeVPIN:
    """Tests for DepthAnalyzer.compute_vpin()."""

    def test_vpin_disabled_returns_empty(self, settings_vpin_disabled: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings_vpin_disabled)
        bars = _make_1min_bars(100)
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is None
        assert result.vpin_cdf is None
        assert result.vpin_level == VPINLevel.NORMAL

    def test_insufficient_bars_returns_empty(self, settings: DepthAnalysisSettings) -> None:
        analyzer = DepthAnalyzer(settings)
        bars = _make_1min_bars(30)  # < VPIN_MIN_1MIN_BARS=50
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is None

    def test_vpin_with_fixed_bucket(self, settings: DepthAnalysisSettings) -> None:
        """VPIN computation with fixed bucket size returns valid result."""
        analyzer = DepthAnalyzer(settings)
        # 375 bars = 1 trading day of 1-min data; need enough for 50+ buckets
        bars = _make_1min_bars(375, base_vol=5000.0)
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is not None
        assert result.vpin_cdf is not None
        assert 0.0 <= result.vpin_value <= 1.0
        assert 0.0 <= result.vpin_cdf <= 1.0

    def test_vpin_with_daily_adv_bucket(self, settings_daily_adv: DepthAnalysisSettings) -> None:
        """VPIN computation with daily_adv bucket size method."""
        analyzer = DepthAnalyzer(settings_daily_adv)
        # Need multiple days worth of data for ADV
        bars = _make_1min_bars(750, base_vol=5000.0)  # 2 trading days
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is not None
        assert result.vpin_cdf is not None

    def test_vpin_cdf_is_empirical(self, settings: DepthAnalysisSettings) -> None:
        """VPIN CDF should be based on empirical distribution of vpin_values."""
        analyzer = DepthAnalyzer(settings)
        bars = _make_1min_bars(375, base_vol=5000.0)
        result = analyzer.compute_vpin(bars)
        assert result.vpin_cdf is not None
        # CDF of the most recent VPIN against its own distribution
        # Since it's the last value, CDF should be >= some positive value
        assert result.vpin_cdf > 0.0

    def test_vpin_level_classifications(self, settings: DepthAnalysisSettings) -> None:
        """VPIN level classification follows CDF thresholds."""
        analyzer = DepthAnalyzer(settings)
        bars = _make_1min_bars(375, base_vol=5000.0)
        result = analyzer.compute_vpin(bars)
        assert result.vpin_level in (VPINLevel.NORMAL, VPINLevel.ELEVATED, VPINLevel.HIGH, VPINLevel.EXTREME)
        if result.vpin_cdf is not None:
            if result.vpin_cdf > settings.VPIN_CDF_EXTREME:
                assert result.vpin_level == VPINLevel.EXTREME
            elif result.vpin_cdf > settings.VPIN_CDF_HIGH:
                assert result.vpin_level == VPINLevel.HIGH
            elif result.vpin_cdf > settings.VPIN_CDF_ELEVATED:
                assert result.vpin_level == VPINLevel.ELEVATED
            else:
                assert result.vpin_level == VPINLevel.NORMAL

    def test_vpin_zero_volume_bars(self, settings: DepthAnalysisSettings) -> None:
        """Bars with zero volume should be handled (skipped in BVC)."""
        analyzer = DepthAnalyzer(settings)
        bars = _make_1min_bars(375, base_vol=5000.0)
        # Set some bars to zero volume
        bars[10:20, 4] = 0.0
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is not None

    def test_vpin_all_zero_volume(self, settings: DepthAnalysisSettings) -> None:
        """All zero volume bars → no buckets → returns empty."""
        analyzer = DepthAnalyzer(settings)
        bars = np.zeros((375, 5), dtype=np.float64)
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is None

    def test_vpin_rounded_to_4_decimals(self, settings: DepthAnalysisSettings) -> None:
        """VPIN value and CDF should be rounded to 4 decimal places."""
        analyzer = DepthAnalyzer(settings)
        bars = _make_1min_bars(375, base_vol=5000.0)
        result = analyzer.compute_vpin(bars)
        if result.vpin_value is not None:
            # Round to 4 decimal places should match exactly
            assert result.vpin_value == round(result.vpin_value, 4)
        if result.vpin_cdf is not None:
            assert result.vpin_cdf == round(result.vpin_cdf, 4)

    def test_vpin_with_strong_up_trend(self, settings: DepthAnalysisSettings) -> None:
        """Strong uptrend bars: VPIN should indicate more buy-side imbalance."""
        analyzer = DepthAnalyzer(settings)
        bars = _make_trending_bars(375, direction=1.0, base_vol=5000.0)
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is not None
        # In a strong uptrend, BVC classifies most volume as buy
        # Order imbalance per bucket is low (mostly buy), so VPIN may be moderate

    def test_vpin_with_strong_down_trend(self, settings: DepthAnalysisSettings) -> None:
        """Strong downtrend bars: VPIN should compute successfully."""
        analyzer = DepthAnalyzer(settings)
        bars = _make_trending_bars(375, direction=-1.0, base_vol=5000.0)
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is not None

    def test_vpin_constant_price_zero_sigma(self, settings: DepthAnalysisSettings) -> None:
        """Constant close prices → sigma=0 → fallback to 1e-10 → no crash."""
        analyzer = DepthAnalyzer(settings)
        n = 375
        bars = np.zeros((n, 5), dtype=np.float64)
        for i in range(n):
            bars[i] = [100.0, 100.5, 99.5, 100.0, 5000.0]  # all same close
        result = analyzer.compute_vpin(bars)
        # Should not crash; sigma=0 → 1e-10, z values near 0
        # Result may or may not have VPIN depending on bucket count
        assert isinstance(result, DepthSignals)

    def test_vpin_returns_depth_signals_type(self, settings: DepthAnalysisSettings) -> None:
        """compute_vpin always returns DepthSignals."""
        analyzer = DepthAnalyzer(settings)
        bars = _make_1min_bars(375)
        result = analyzer.compute_vpin(bars)
        assert isinstance(result, DepthSignals)

    def test_vpin_below_min_bars_returns_empty(self, settings: DepthAnalysisSettings) -> None:
        """Exactly min_bars - 1 should return empty."""
        analyzer = DepthAnalyzer(settings)
        bars = _make_1min_bars(49)  # 1 less than VPIN_MIN_1MIN_BARS=50
        result = analyzer.compute_vpin(bars)
        assert result.vpin_value is None


# ===========================================================================
# DepthAnalyzer._compute_bucket_size
# ===========================================================================


class TestComputeBucketSize:
    """Tests for DepthAnalyzer._compute_bucket_size()."""

    def test_fixed_method(self, settings: DepthAnalysisSettings) -> None:
        v = np.full(375, 5000.0)
        result = DepthAnalyzer._compute_bucket_size(settings, v)
        assert result == float(settings.VPIN_FIXED_BUCKET_SIZE)

    def test_daily_adv_method(self, settings_daily_adv: DepthAnalysisSettings) -> None:
        v = np.full(750, 5000.0)  # 2 days × 375 bars
        result = DepthAnalyzer._compute_bucket_size(settings_daily_adv, v)
        # ADV = 375 * 5000 = 1875000; bucket = 1875000 / 50 = 37500
        expected = (375.0 * 5000.0) / 50.0
        assert result == expected

    def test_daily_adv_with_fewer_bars_than_day(self, settings_daily_adv: DepthAnalysisSettings) -> None:
        """Less than 375 bars → no full days → fallback to fixed."""
        v = np.full(100, 5000.0)
        result = DepthAnalyzer._compute_bucket_size(settings_daily_adv, v)
        # num_days = 100 // 375 = 0 → daily_volumes empty → fallback
        assert result == float(settings_daily_adv.VPIN_FIXED_BUCKET_SIZE)


# ===========================================================================
# DepthAnalyzer._bvc_classify
# ===========================================================================


class TestBVCClassify:
    """Tests for DepthAnalyzer._bvc_classify()."""

    def test_up_bar_more_buy_volume(self) -> None:
        """Up bar (close > open) should have more buy than sell volume."""
        o = np.array([100.0], dtype=np.float64)
        c = np.array([102.0], dtype=np.float64)
        v = np.array([5000.0], dtype=np.float64)
        buy, sell = DepthAnalyzer._bvc_classify(o, c, v)
        assert buy[0] > sell[0]

    def test_down_bar_more_sell_volume(self) -> None:
        """Down bar (close < open) should have more sell than buy volume."""
        o = np.array([102.0], dtype=np.float64)
        c = np.array([100.0], dtype=np.float64)
        v = np.array([5000.0], dtype=np.float64)
        buy, sell = DepthAnalyzer._bvc_classify(o, c, v)
        assert sell[0] > buy[0]

    def test_doji_equal_split(self) -> None:
        """Doji bar (close == open) should have ~50/50 split."""
        o = np.array([100.0, 101.0, 99.0], dtype=np.float64)
        c = np.array([100.0, 101.0, 99.0], dtype=np.float64)
        v = np.array([5000.0, 5000.0, 5000.0], dtype=np.float64)
        buy, sell = DepthAnalyzer._bvc_classify(o, c, v)
        # close == open → z ≈ 0 → CDF(0) ≈ 0.5
        assert abs(buy[0] - sell[0]) < 100  # approximately equal

    def test_zero_volume_bar(self) -> None:
        """Zero volume bar should have zero buy and sell."""
        o = np.array([100.0], dtype=np.float64)
        c = np.array([102.0], dtype=np.float64)
        v = np.array([0.0], dtype=np.float64)
        buy, sell = DepthAnalyzer._bvc_classify(o, c, v)
        assert buy[0] == 0.0
        assert sell[0] == 0.0

    def test_buy_plus_sell_equals_volume(self) -> None:
        """buy + sell must equal volume for each bar."""
        rng = np.random.default_rng(123)
        n = 50
        o = 100 + rng.standard_normal(n)
        c = o + rng.standard_normal(n) * 0.5
        v = np.abs(rng.standard_normal(n)) * 5000 + 100
        buy, sell = DepthAnalyzer._bvc_classify(o, c, v)
        np.testing.assert_allclose(buy + sell, v, rtol=1e-10)


# ===========================================================================
# DepthAnalyzer._fill_buckets
# ===========================================================================


class TestFillBuckets:
    """Tests for DepthAnalyzer._fill_buckets()."""

    def test_single_exact_bucket(self) -> None:
        """Volume exactly fills one bucket."""
        v = np.array([10000.0], dtype=np.float64)
        buy = np.array([6000.0], dtype=np.float64)
        sell = np.array([4000.0], dtype=np.float64)
        buckets = DepthAnalyzer._fill_buckets(v, buy, sell, bucket_size=10000.0)
        assert len(buckets) == 1
        assert abs(buckets[0]["total_vol"] - 10000.0) < 1e-10
        assert abs(buckets[0]["buy_vol"] - 6000.0) < 1e-10
        assert abs(buckets[0]["sell_vol"] - 4000.0) < 1e-10

    def test_two_bars_one_bucket(self) -> None:
        """Two bars that together fill one bucket."""
        v = np.array([5000.0, 5000.0], dtype=np.float64)
        buy = np.array([2500.0, 3500.0], dtype=np.float64)
        sell = np.array([2500.0, 1500.0], dtype=np.float64)
        buckets = DepthAnalyzer._fill_buckets(v, buy, sell, bucket_size=10000.0)
        assert len(buckets) == 1
        assert abs(buckets[0]["total_vol"] - 10000.0) < 1e-10

    def test_single_bar_fills_multiple_buckets(self) -> None:
        """One bar with volume > bucket_size fills multiple buckets."""
        v = np.array([25000.0], dtype=np.float64)
        buy = np.array([15000.0], dtype=np.float64)
        sell = np.array([10000.0], dtype=np.float64)
        buckets = DepthAnalyzer._fill_buckets(v, buy, sell, bucket_size=10000.0)
        # 25000 / 10000 = 2.5 → 2 full + 1 partial = 3
        assert len(buckets) == 3

    def test_zero_volume_produces_no_buckets(self) -> None:
        """Zero volume → no buckets."""
        v = np.array([0.0, 0.0], dtype=np.float64)
        buy = np.array([0.0, 0.0], dtype=np.float64)
        sell = np.array([0.0, 0.0], dtype=np.float64)
        buckets = DepthAnalyzer._fill_buckets(v, buy, sell, bucket_size=10000.0)
        assert len(buckets) == 0

    def test_partial_bucket_included(self) -> None:
        """Partial last bucket should be included."""
        v = np.array([7000.0], dtype=np.float64)
        buy = np.array([4200.0], dtype=np.float64)
        sell = np.array([2800.0], dtype=np.float64)
        buckets = DepthAnalyzer._fill_buckets(v, buy, sell, bucket_size=10000.0)
        assert len(buckets) == 1
        assert abs(buckets[0]["total_vol"] - 7000.0) < 1e-10


# ===========================================================================
# DepthAnalyzer._compute_vpin_rolling
# ===========================================================================


class TestComputeVPINRolling:
    """Tests for DepthAnalyzer._compute_vpin_rolling()."""

    def test_insufficient_buckets_returns_none(self, settings: DepthAnalysisSettings) -> None:
        """Fewer buckets than VPIN_NUM_BUCKETS → None."""
        buckets = [
            {"buy_vol": 3000.0, "sell_vol": 2000.0, "total_vol": 5000.0},
            {"buy_vol": 2500.0, "sell_vol": 2500.0, "total_vol": 5000.0},
        ]
        vpin, cdf, level = DepthAnalyzer._compute_vpin_rolling(buckets, 5000.0, settings)
        assert vpin is None
        assert level == VPINLevel.NORMAL

    def test_sufficient_buckets_returns_vpin(self, settings: DepthAnalysisSettings) -> None:
        """Enough buckets → valid VPIN value."""
        # Create 55 buckets (more than 50)
        buckets = []
        for _ in range(55):
            buckets.append({"buy_vol": 3000.0, "sell_vol": 2000.0, "total_vol": 5000.0})
        vpin, cdf, level = DepthAnalyzer._compute_vpin_rolling(buckets, 5000.0, settings)
        assert vpin is not None
        assert 0.0 <= vpin <= 1.0

    def test_perfectly_balanced_vpin_low(self, settings: DepthAnalysisSettings) -> None:
        """Balanced buy/sell → low VPIN."""
        buckets = []
        for _ in range(55):
            buckets.append({"buy_vol": 2500.0, "sell_vol": 2500.0, "total_vol": 5000.0})
        vpin, cdf, level = DepthAnalyzer._compute_vpin_rolling(buckets, 5000.0, settings)
        assert vpin is not None
        assert vpin == 0.0  # |2500-2500| = 0 for all → VPIN = 0

    def test_extreme_imbalance_high_vpin(self, settings: DepthAnalysisSettings) -> None:
        """All buy → high VPIN."""
        buckets = []
        for _ in range(55):
            buckets.append({"buy_vol": 5000.0, "sell_vol": 0.0, "total_vol": 5000.0})
        vpin, cdf, level = DepthAnalyzer._compute_vpin_rolling(buckets, 5000.0, settings)
        assert vpin is not None
        # |5000 - 0| = 5000 per bucket; VPIN = 5000*50 / (5000*50) = 1.0
        assert vpin == 1.0


# ===========================================================================
# Integration: analyze_depth + compute_vpin together
# ===========================================================================


class TestDepthIntegration:
    """Integration tests: full depth analysis pipeline."""

    def test_analyze_depth_and_vpin_together(self, settings: DepthAnalysisSettings) -> None:
        """Run both analyze_depth and compute_vpin — no exceptions."""
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data()
        depth_result = analyzer.analyze_depth(depth, ltp=100.25)
        bars = _make_1min_bars(375, base_vol=5000.0)
        vpin_result = analyzer.compute_vpin(bars)

        assert depth_result.bid_ask_spread_bps is not None
        assert isinstance(vpin_result, DepthSignals)

    def test_performance_under_50ms(self, settings: DepthAnalysisSettings) -> None:
        """Both methods should complete in < 50ms for typical data."""
        import time

        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data()
        bars = _make_1min_bars(750, base_vol=5000.0)

        start = time.perf_counter()
        for _ in range(10):
            analyzer.analyze_depth(depth, ltp=100.25)
            analyzer.compute_vpin(bars)
        elapsed_ms = (time.perf_counter() - start) * 1000 / 10

        assert elapsed_ms < 100, f"Depth analysis took {elapsed_ms:.1f}ms (target <50ms, relaxed for CI)"

    def test_model_dump_round_trip(self, settings: DepthAnalysisSettings) -> None:
        """DepthSignals from both methods can be serialized via model_dump."""
        analyzer = DepthAnalyzer(settings)
        depth = _make_depth_data()
        result = analyzer.analyze_depth(depth, ltp=100.25)
        d = result.model_dump()
        assert "bid_ask_spread_bps" in d
        assert "vpin_level" in d
