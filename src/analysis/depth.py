"""Market depth analysis and VPIN (Volume-Synchronized Probability of Informed Trading).

Analyzes 5-level depth data from Zerodha WebSocket full mode.
VPIN uses BVC (Bulk Volume Classification) since tick-level trade
direction is unavailable (Easley/Lopez de Prado/O'Hara 2012).

References:
- Easley, Lopez de Prado, O'Hara (2012): VPIN methodology
- Bhabra et al.: BVC for trade direction estimation
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import numpy as np
import structlog
from numpy.typing import NDArray
from pydantic import BaseModel, Field
from scipy.stats import norm

from config.settings import DepthAnalysisSettings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class VPINLevel(StrEnum):
    """VPIN toxicity level classification."""

    NORMAL = "NORMAL"  # VPIN CDF ≤ 0.90
    ELEVATED = "ELEVATED"  # VPIN CDF > 0.90
    HIGH = "HIGH"  # VPIN CDF > 0.95
    EXTREME = "EXTREME"  # VPIN CDF > 0.99


class DepthLevel(BaseModel):
    """Single depth level (price + quantity)."""

    price: float = Field(description="Price level")
    quantity: int = Field(ge=0, description="Quantity at this price level")


class DepthData(BaseModel):
    """Market depth data with bid/ask levels."""

    bid_levels: list[DepthLevel] = Field(default_factory=list, description="Bid levels (best bid first)")
    ask_levels: list[DepthLevel] = Field(default_factory=list, description="Ask levels (best ask first)")
    timestamp: datetime | None = Field(default=None, description="UTC timestamp of the depth snapshot")


class DepthSignals(BaseModel):
    """Computed depth-derived signals."""

    bid_ask_spread_bps: float | None = Field(None, description="Bid-ask spread in basis points")
    depth_imbalance_ratio: float | None = Field(None, description="Total bid qty / Total ask qty")
    depth_imbalance_signal: str | None = Field(None, description="BULLISH_IMBALANCE or BEARISH_IMBALANCE or NEUTRAL")
    total_bid_quantity: int | None = None
    total_ask_quantity: int | None = None
    vpin_value: float | None = Field(None, description="VPIN raw value")
    vpin_cdf: float | None = Field(None, description="VPIN CDF value [0, 1]")
    vpin_level: VPINLevel = Field(VPINLevel.NORMAL, description="VPIN toxicity level")


# ---------------------------------------------------------------------------
# DepthAnalyzer
# ---------------------------------------------------------------------------


class DepthAnalyzer:
    """Analyzes market depth data and computes VPIN.

    Zerodha provides 5-level depth via WebSocket full mode.
    Dhan provides 200-level depth (deferred to Phase 12 multi-broker integration).

    VPIN (Volume-Synchronized Probability of Informed Trading):
    - Easley, López de Prado, O'Hara (2012)
    - Uses BVC (Bulk Volume Classification) since Zerodha lacks tick-level trade direction
    - BVC accuracy: ~85-95% (sufficient for toxicity estimation)
    - Requires 1-min OHLCV data (NOT 5-level depth — depth is insufficient for VPIN)

    Algorithm (4 steps):
    1. Compute ADV (Average Daily Volume) over VPIN_DAILY_ADV_LOOKBACK days
    2. Compute bucket_size = ADV / 50 (or use VPIN_FIXED_BUCKET_SIZE)
    3. Classify volume into buckets using BVC
    4. VPIN = rolling sum of order imbalance / (bucket_size * num_buckets)
    """

    def __init__(self, settings: DepthAnalysisSettings) -> None:
        self._settings = settings

    def analyze_depth(self, depth: DepthData, ltp: float | None = None) -> DepthSignals:
        """Analyze 5-level depth data from Zerodha WebSocket.

        Args:
            depth: Depth data with bid/ask levels
            ltp: Last traded price (for spread computation in bps)
        """
        if not depth.bid_levels or not depth.ask_levels:
            return DepthSignals(
                bid_ask_spread_bps=None,
                depth_imbalance_ratio=None,
                depth_imbalance_signal=None,
                total_bid_quantity=None,
                total_ask_quantity=None,
                vpin_value=None,
                vpin_cdf=None,
                vpin_level=VPINLevel.NORMAL,
            )

        best_bid = depth.bid_levels[0].price
        best_ask = depth.ask_levels[0].price

        # Bid-ask spread in basis points
        spread_bps: float | None = None
        if ltp is not None and ltp > 0:
            spread_bps = ((best_ask - best_bid) / ltp) * 10000

        # Depth imbalance
        total_bid_qty = sum(level.quantity for level in depth.bid_levels)
        total_ask_qty = sum(level.quantity for level in depth.ask_levels)
        imbalance_ratio: float | None = total_bid_qty / total_ask_qty if total_ask_qty > 0 else None

        imbalance_signal = "NEUTRAL"
        if imbalance_ratio is not None:
            if imbalance_ratio > self._settings.IMBALANCE_THRESHOLD:
                imbalance_signal = "BULLISH_IMBALANCE"
            elif imbalance_ratio < 1.0 / self._settings.IMBALANCE_THRESHOLD:
                imbalance_signal = "BEARISH_IMBALANCE"

        return DepthSignals(
            bid_ask_spread_bps=round(spread_bps, 2) if spread_bps is not None else None,
            depth_imbalance_ratio=round(imbalance_ratio, 4) if imbalance_ratio is not None else None,
            depth_imbalance_signal=imbalance_signal,
            total_bid_quantity=total_bid_qty,
            total_ask_quantity=total_ask_qty,
            vpin_value=None,
            vpin_cdf=None,
            vpin_level=VPINLevel.NORMAL,
        )

    def compute_vpin(self, bars_1min: np.ndarray | NDArray[np.float64]) -> DepthSignals:
        """Compute VPIN from 1-minute OHLCV bars.

        Args:
            bars_1min: numpy array with columns [open, high, low, close, volume]
                       Must have at least VPIN_MIN_1MIN_BARS rows.

        Algorithm:
        1. Compute bucket_size (from ADV or fixed)
        2. Fill volume buckets using BVC (Bulk Volume Classification)
        3. For each bucket: V_buy = V * CDF(Z), V_sell = V * (1 - CDF(Z))
           where Z = (close - open) / (σ * √dt), dt = bar_duration / day_duration
        4. Order imbalance = |V_buy - V_sell| per bucket
        5. VPIN = rolling sum of imbalances / (bucket_size * num_buckets)

        Returns DepthSignals with VPIN fields populated.
        """
        s = self._settings

        if not s.VPIN_ENABLED or len(bars_1min) < s.VPIN_MIN_1MIN_BARS:
            return DepthSignals(
                bid_ask_spread_bps=None,
                depth_imbalance_ratio=None,
                depth_imbalance_signal=None,
                total_bid_quantity=None,
                total_ask_quantity=None,
                vpin_value=None,
                vpin_cdf=None,
                vpin_level=VPINLevel.NORMAL,
            )

        o = bars_1min[:, 0].astype(np.float64)
        c = bars_1min[:, 3].astype(np.float64)
        v = bars_1min[:, 4].astype(np.float64)

        # Step 1: Compute bucket size
        bucket_size = self._compute_bucket_size(s, v)

        if bucket_size <= 0:
            return DepthSignals(
                bid_ask_spread_bps=None,
                depth_imbalance_ratio=None,
                depth_imbalance_signal=None,
                total_bid_quantity=None,
                total_ask_quantity=None,
                vpin_value=None,
                vpin_cdf=None,
                vpin_level=VPINLevel.NORMAL,
            )

        # Step 2: BVC volume classification
        buy_volumes, sell_volumes = self._bvc_classify(o, c, v)

        # Step 3: Fill volume buckets
        buckets = self._fill_buckets(v, buy_volumes, sell_volumes, bucket_size)

        # Step 4: Compute VPIN (rolling sum of order imbalance)
        vpin, vpin_cdf, vpin_level = self._compute_vpin_rolling(buckets, bucket_size, s)

        if vpin is None:
            return DepthSignals(
                bid_ask_spread_bps=None,
                depth_imbalance_ratio=None,
                depth_imbalance_signal=None,
                total_bid_quantity=None,
                total_ask_quantity=None,
                vpin_value=None,
                vpin_cdf=None,
                vpin_level=VPINLevel.NORMAL,
            )

        return DepthSignals(
            bid_ask_spread_bps=None,
            depth_imbalance_ratio=None,
            depth_imbalance_signal=None,
            total_bid_quantity=None,
            total_ask_quantity=None,
            vpin_value=round(vpin, 4),
            vpin_cdf=round(vpin_cdf, 4) if vpin_cdf is not None else None,
            vpin_level=vpin_level,
        )

    @staticmethod
    def _compute_bucket_size(s: DepthAnalysisSettings, v: NDArray[np.float64]) -> float:
        """Compute volume bucket size from ADV or fixed setting."""
        daily_volumes: list[float] = []
        # Assume 375 1-min bars per trading day (6.25 hours × 60)
        bars_per_day = 375
        num_days = len(v) // bars_per_day
        for d in range(num_days):
            day_vol = float(np.sum(v[d * bars_per_day : (d + 1) * bars_per_day]))
            daily_volumes.append(day_vol)

        if s.VPIN_BUCKET_SIZE_METHOD == "daily_adv" and daily_volumes:
            lookback_days = min(s.VPIN_DAILY_ADV_LOOKBACK, len(daily_volumes))
            adv = float(np.mean(daily_volumes[-lookback_days:]))
            return adv / 50

        return float(s.VPIN_FIXED_BUCKET_SIZE)

    @staticmethod
    def _bvc_classify(
        o: NDArray[np.float64],
        c: NDArray[np.float64],
        v: NDArray[np.float64],
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Bulk Volume Classification: V_buy = V * CDF(Z), V_sell = V * (1-CDF(Z)).

        Z = (close - open) / (σ * √dt) where dt = 1/bars_per_day.
        """
        price_changes = np.diff(c)
        sigma = float(np.std(price_changes)) if len(price_changes) > 1 else 1.0
        if sigma == 0:
            sigma = 1e-10

        # BVC normalization factor
        bars_per_day = 375
        sqrt_dt = np.sqrt(1.0 / bars_per_day)
        denom = sigma * sqrt_dt

        buy_volumes = np.zeros(len(v), dtype=np.float64)
        sell_volumes = np.zeros(len(v), dtype=np.float64)

        for i in range(len(v)):
            if v[i] == 0:
                continue
            z = (c[i] - o[i]) / denom if denom != 0 else 0.0
            cdf_val = float(norm.cdf(z))
            buy_volumes[i] = v[i] * cdf_val
            sell_volumes[i] = v[i] * (1.0 - cdf_val)

        return buy_volumes, sell_volumes

    @staticmethod
    def _fill_buckets(
        v: NDArray[np.float64],
        buy_volumes: NDArray[np.float64],
        sell_volumes: NDArray[np.float64],
        bucket_size: float,
    ) -> list[dict[str, float]]:
        """Fill volume buckets preserving buy/sell proportions."""
        buckets: list[dict[str, float]] = []
        current: dict[str, float] = {"buy_vol": 0.0, "sell_vol": 0.0, "total_vol": 0.0}

        for i in range(len(v)):
            remaining = v[i]
            buy_share = buy_volumes[i] / v[i] if v[i] > 0 else 0.5
            sell_share = sell_volumes[i] / v[i] if v[i] > 0 else 0.5

            while remaining > 0:
                space = bucket_size - current["total_vol"]
                fill = min(remaining, space)

                current["buy_vol"] += fill * buy_share
                current["sell_vol"] += fill * sell_share
                current["total_vol"] += fill

                remaining -= fill

                if current["total_vol"] >= bucket_size:
                    buckets.append(current.copy())
                    current = {"buy_vol": 0.0, "sell_vol": 0.0, "total_vol": 0.0}

        # Handle partial last bucket
        if current["total_vol"] > 0:
            buckets.append(current)

        return buckets

    @staticmethod
    def _compute_vpin_rolling(
        buckets: list[dict[str, float]],
        bucket_size: float,
        s: DepthAnalysisSettings,
    ) -> tuple[float | None, float | None, VPINLevel]:
        """Compute VPIN from filled volume buckets.

        Returns (vpin_value, vpin_cdf, vpin_level).
        """
        num_buckets = s.VPIN_NUM_BUCKETS
        if len(buckets) < num_buckets:
            return None, None, VPINLevel.NORMAL

        imbalances = [abs(b["buy_vol"] - b["sell_vol"]) for b in buckets]

        vpin_values: list[float] = []
        for i in range(num_buckets - 1, len(imbalances)):
            window = imbalances[i - num_buckets + 1 : i + 1]
            vpin_val = sum(window) / (bucket_size * num_buckets)
            vpin_values.append(vpin_val)

        if not vpin_values:
            return None, None, VPINLevel.NORMAL

        vpin = float(vpin_values[-1])

        # VPIN CDF (empirical)
        vpin_cdf = float(np.mean(np.array(vpin_values) <= vpin))

        # Classify VPIN level
        vpin_level = VPINLevel.NORMAL
        if vpin_cdf > s.VPIN_CDF_EXTREME:
            vpin_level = VPINLevel.EXTREME
        elif vpin_cdf > s.VPIN_CDF_HIGH:
            vpin_level = VPINLevel.HIGH
        elif vpin_cdf > s.VPIN_CDF_ELEVATED:
            vpin_level = VPINLevel.ELEVATED

        return vpin, vpin_cdf, vpin_level
