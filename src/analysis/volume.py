"""Volume analysis components — Phase 3.

Implements Volume Profile, Volume Spread Analysis (VSA), Price-Volume Divergence,
and Volume Anomaly detection.

Book references:
- Dalton "Mind Over Markets": Market Profile & Volume Profile
- Weis "Trades About to Happen": Volume Spread Analysis
- Coulling "Volume Price Analysis": VSA principles
- Easley/Lopez de Prado/O'Hara: Volume-Synchronized Probability of Informed Trading (VPIN)

Performance target: Volume profile computation < 5ms for 500 bars. All detectors combined < 10ms.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from config.settings import VolumeProfileSettings


class VSASignalType(StrEnum):
    # Buying signals (Weis/Coulling)
    DEMAND_BAR = "DEMAND_BAR"  # Wide spread up, close near high, volume above average
    NO_SUPPLY = "NO_SUPPLY"  # Narrow spread down, close near high, volume below average
    STOPPING_VOLUME = "STOPPING_VOLUME"  # High volume on down bar, close near middle/high
    CLIMACTIC_SELL = "CLIMACTIC_SELL"  # Ultra-high volume, wide spread down, close near low → selling climax

    # Selling signals
    SUPPLY_BAR = "SUPPLY_BAR"  # Wide spread down, close near low, volume above average
    NO_DEMAND = "NO_DEMAND"  # Narrow spread up, close near low, volume below average
    EFFORT_VS_RESULT_UP = "EFFORT_VS_RESULT_UP"  # High volume but narrow spread up → buying exhaustion
    EFFORT_VS_RESULT_DOWN = "EFFORT_VS_RESULT_DOWN"  # High volume but narrow spread down → selling exhaustion
    CLIMACTIC_BUY = "CLIMACTIC_BUY"  # Ultra-high volume, wide spread up, close near low → buying climax


class VSASignal(BaseModel):
    bar_index: int = Field(description="Index of the bar producing the signal")
    signal_type: VSASignalType = Field(description="VSA signal classification")
    confidence: float = Field(ge=0.0, le=1.0, description="Signal confidence [0, 1]")
    context: dict[str, float | str] = Field(
        default_factory=dict, description="Supporting data: volume_pct, spread_pct, close_position"
    )


class PriceVolumeDivergence(BaseModel):
    divergence_type: str = Field(description="BEARISH_DIVERGENCE or BULLISH_DIVERGENCE")
    price_swings: list[float] = Field(description="Price swing points")
    volume_swings: list[float] = Field(description="Volume swing points")
    bar_indices: list[int] = Field(description="Bar indices of swing points")
    strength: float = Field(ge=0.0, le=1.0, description="Divergence strength")


class VolumeAnomaly(BaseModel):
    bar_index: int
    volume_ratio: float = Field(description="Current volume / mean volume")
    z_score: float = Field(description="(volume - mean) / stddev")
    is_spike: bool = Field(description="Volume > mean + 2σ")
    price_rejection: bool = Field(description="True if price has long wick suggesting rejection")


class VolumeProfileResult(BaseModel):
    poc_price: float | None = Field(None, description="Point of Control: price level with highest volume")
    vah: float | None = Field(None, description="Value Area High: top of 68.2% value area")
    val: float | None = Field(None, description="Value Area Low: bottom of 68.2% value area")
    profile: dict[float, float] = Field(default_factory=dict, description="price_bin → volume mapping")
    total_volume: float = Field(0.0)
    relative_position: str | None = Field(
        None, description="CURRENT_ABOVE_VA, CURRENT_IN_VA, CURRENT_BELOW_VA, CURRENT_AT_POC"
    )


class VolumeSignals(BaseModel):
    profile: VolumeProfileResult = Field(default=VolumeProfileResult())
    vsa_signals: list[VSASignal] = Field(default_factory=list)
    divergences: list[PriceVolumeDivergence] = Field(default_factory=list)
    anomalies: list[VolumeAnomaly] = Field(default_factory=list)


class VolumeProfileComputer:
    """Computes volume profile: POC, Value Area, VAH, VAL.

    Value Area = 68.2% of total volume (CME/Dalton canonical standard = 1 standard deviation).
    NOT 70% (common approximation). The 68.2% matches the Gaussian 1σ and Dalton's original specification.

    Reference: Dalton "Mind Over Markets", CME Market Profile handbook.
    """

    def __init__(self, settings: VolumeProfileSettings) -> None:
        self._settings = settings

    def compute(
        self,
        high: NDArray[np.float64],
        low: NDArray[np.float64],
        close: NDArray[np.float64],
        volume: NDArray[np.float64],
    ) -> VolumeProfileResult:
        """Compute volume profile from OHLCV data."""
        if len(close) < 2:
            return VolumeProfileResult()

        price_min = float(np.min(low))
        price_max = float(np.max(high))
        if price_max == price_min:
            return VolumeProfileResult()

        num_bins = self._settings.NUM_PRICE_BINS
        bin_size = (price_max - price_min) / num_bins

        # Distribute volume across price bins
        # Each bar's volume is split uniformly across its high-low range
        bin_volumes = np.zeros(num_bins)
        bin_prices = np.array([price_min + (i + 0.5) * bin_size for i in range(num_bins)])

        for i in range(len(close)):
            bar_low = low[i]
            bar_high = high[i]
            bar_vol = volume[i]

            if bar_high == bar_low or bar_vol == 0:
                continue

            # Find bins that overlap with this bar's range
            for b in range(num_bins):
                bin_low = price_min + b * bin_size
                bin_high = bin_low + bin_size

                overlap = min(bar_high, bin_high) - max(bar_low, bin_low)
                if overlap > 0:
                    fraction = overlap / (bar_high - bar_low)
                    bin_volumes[b] += bar_vol * fraction

        total_volume = float(np.sum(bin_volumes))
        if total_volume == 0:
            return VolumeProfileResult()

        # POC: bin with highest volume
        poc_bin = int(np.argmax(bin_volumes))
        poc_price = float(bin_prices[poc_bin])

        # Value Area: expand from POC until we encompass 68.2% of total volume
        va_target = total_volume * self._settings.VALUE_AREA_PCT
        vah_idx = poc_bin
        val_idx = poc_bin
        current_vol = bin_volumes[poc_bin]

        while current_vol < va_target and (val_idx > 0 or vah_idx < num_bins - 1):
            add_below = bin_volumes[val_idx - 1] if val_idx > 0 else 0
            add_above = bin_volumes[vah_idx + 1] if vah_idx < num_bins - 1 else 0

            if add_below >= add_above and val_idx > 0:
                val_idx -= 1
                current_vol += add_below
            elif vah_idx < num_bins - 1:
                vah_idx += 1
                current_vol += add_above
            elif val_idx > 0:
                val_idx -= 1
                current_vol += add_below
            else:
                break

        vah = float(bin_prices[vah_idx] + bin_size / 2)
        val = float(bin_prices[val_idx] - bin_size / 2)

        # Relative position of current price to profile
        last_close = float(close[-1])
        if last_close > vah:
            rel_pos = "CURRENT_ABOVE_VA"
        elif last_close < val:
            rel_pos = "CURRENT_BELOW_VA"
        elif abs(last_close - poc_price) < bin_size:
            rel_pos = "CURRENT_AT_POC"
        else:
            rel_pos = "CURRENT_IN_VA"

        profile_dict = {round(float(bin_prices[i]), 2): round(float(bin_volumes[i]), 2) for i in range(num_bins)}

        return VolumeProfileResult(
            poc_price=round(poc_price, 2),
            vah=round(vah, 2),
            val=round(val, 2),
            profile=profile_dict,
            total_volume=round(total_volume, 2),
            relative_position=rel_pos,
        )


class VSASignalDetector:
    """Volume Spread Analysis signal detection.

    Implements Wyckoff/Weis/Coulling VSA methodology with 5-bar context window
    (2 prior + current + 2 after) for signal confirmation.

    References:
    - Weis "Trades About to Happen" Ch.3: context window for VSA signals
    - Coulling "Volume Price Analysis": demand/supply bar definitions
    - Dalton "Mind Over Markets": market profile + VSA integration
    """

    def __init__(self, settings: VolumeProfileSettings) -> None:
        self._settings = settings

    def detect(self, ohlcv: NDArray[np.float64]) -> list[VSASignal]:
        """Detect VSA signals across all bars with sufficient context.

        Args:
            ohlcv: numpy array with columns [open, high, low, close, volume]
        """
        if len(ohlcv) < self._settings.VSA_CONTEXT_WINDOW:
            return []

        signals: list[VSASignal] = []
        context_half = self._settings.VSA_CONTEXT_WINDOW // 2

        open_ = ohlcv[:, 0]
        high = ohlcv[:, 1]
        low = ohlcv[:, 2]
        close = ohlcv[:, 3]
        volume = ohlcv[:, 4]

        # Precompute averages
        avg_volume = float(np.mean(volume[-self._settings.VSA_SPREAD_COMPARISON_PERIOD :]))
        avg_spread = float(
            np.mean(
                high[-self._settings.VSA_SPREAD_COMPARISON_PERIOD :]
                - low[-self._settings.VSA_SPREAD_COMPARISON_PERIOD :]
            )
        )

        for i in range(context_half, len(close) - context_half):
            signal = self._analyze_bar(open_, high, low, close, volume, i, avg_volume, avg_spread)
            if signal is not None:
                # Validate with context window
                if self._confirm_with_context(signal, close, volume, i, context_half):
                    signals.append(signal)

        return signals

    def _analyze_bar(
        self,
        open_: NDArray[np.float64],
        high: NDArray[np.float64],
        low: NDArray[np.float64],
        close: NDArray[np.float64],
        volume: NDArray[np.float64],
        i: int,
        avg_vol: float,
        avg_spread: float,
    ) -> VSASignal | None:
        """Analyze a single bar for VSA signals."""
        spread = high[i] - low[i]
        vol = volume[i]

        if avg_vol == 0 or avg_spread == 0:
            return None

        vol_pct = vol / avg_vol
        spread_pct = spread / avg_spread

        # Close position within the bar: 0 = at low, 1 = at high
        close_position = (close[i] - low[i]) / spread if spread > 0 else 0.5

        # --- Demand signals ---

        # Demand bar: wide spread up, close near high, volume above average
        if spread_pct > 1.2 and close[i] > open_[i] and close_position > 0.7 and vol_pct > 1.0:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.DEMAND_BAR,
                confidence=min(vol_pct / 3.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        # No supply: narrow spread down, close near high, volume below average
        if spread_pct < 0.8 and close[i] < open_[i] and close_position > 0.6 and vol_pct < 0.8:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.NO_SUPPLY,
                confidence=min((1.0 - vol_pct) / 2.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        # Stopping volume: high volume on down bar, close near middle/high
        if vol_pct > self._settings.VSA_VOLUME_SPIKE_MULTIPLIER and close[i] < open_[i] and close_position > 0.4:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.STOPPING_VOLUME,
                confidence=min(vol_pct / 4.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        # Climactic sell: ultra-high volume, wide spread down, close near low (selling exhaustion)
        if vol_pct > self._settings.VSA_VOLUME_SPIKE_MULTIPLIER * 2 and close[i] < open_[i] and close_position < 0.3:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.CLIMACTIC_SELL,
                confidence=min(vol_pct / 6.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        # --- Supply signals ---

        # Supply bar: wide spread down, close near low, volume above average
        if spread_pct > 1.2 and close[i] < open_[i] and close_position < 0.3 and vol_pct > 1.0:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.SUPPLY_BAR,
                confidence=min(vol_pct / 3.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        # No demand: narrow spread up, close near low, volume below average
        if spread_pct < 0.8 and close[i] > open_[i] and close_position < 0.4 and vol_pct < 0.8:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.NO_DEMAND,
                confidence=min((1.0 - vol_pct) / 2.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        # Effort vs result UP: high volume, narrow spread up → buying exhaustion
        if vol_pct > self._settings.VSA_VOLUME_SPIKE_MULTIPLIER and close[i] > open_[i] and spread_pct < 0.6:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.EFFORT_VS_RESULT_UP,
                confidence=min(vol_pct / 4.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        # Effort vs result DOWN: high volume, narrow spread down → selling exhaustion
        if vol_pct > self._settings.VSA_VOLUME_SPIKE_MULTIPLIER and close[i] < open_[i] and spread_pct < 0.6:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.EFFORT_VS_RESULT_DOWN,
                confidence=min(vol_pct / 4.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        # Climactic buy: ultra-high volume, wide spread up, close near low → buying climax
        if vol_pct > self._settings.VSA_VOLUME_SPIKE_MULTIPLIER * 2 and close[i] > open_[i] and close_position < 0.3:
            return VSASignal(
                bar_index=i,
                signal_type=VSASignalType.CLIMACTIC_BUY,
                confidence=min(vol_pct / 6.0, 1.0),
                context={
                    "volume_pct": round(vol_pct, 2),
                    "spread_pct": round(spread_pct, 2),
                    "close_position": round(close_position, 2),
                },
            )

        return None

    def _confirm_with_context(
        self, signal: VSASignal, close: NDArray[np.float64], volume: NDArray[np.float64], i: int, context_half: int
    ) -> bool:
        """Weis Ch.3: 5-bar context window confirmation.

        A VSA signal is confirmed if the surrounding bars support the thesis:
        - For buying signals: prior bars should show selling pressure diminishing
        - For selling signals: prior bars should show buying pressure diminishing
        """
        # Simple confirmation: volume trend in context window
        start = i - context_half
        end = i + context_half + 1

        context_volumes = volume[start:end]
        if len(context_volumes) < 3:
            return True  # Insufficient context — allow by default

        # Check that signal bar's volume is a local peak or near-peak
        vol_rank = sum(1 for cv in context_volumes if volume[i] >= cv) / len(context_volumes)

        # Signal is confirmed if its volume is in the top 40% of context window
        return vol_rank >= 0.4


class PriceVolumeDivergenceDetector:
    """Detects price-volume divergences.

    Bearish divergence: price making higher highs + volume making lower highs
    Bullish divergence: price making lower lows + volume making lower lows
    """

    def __init__(self, settings: VolumeProfileSettings) -> None:
        self._settings = settings

    def detect(
        self,
        high: NDArray[np.float64],
        low: NDArray[np.float64],
        close: NDArray[np.float64],
        volume: NDArray[np.float64],
    ) -> list[PriceVolumeDivergence]:
        """Detect divergences between price and volume."""
        if len(close) < self._settings.DIVERGENCE_LOOKBACK:
            return []

        divergences = []

        # Find swing highs and lows in price and volume
        lookback = self._settings.DIVERGENCE_LOOKBACK
        recent_high = high[-lookback:]
        recent_low = low[-lookback:]
        recent_vol = volume[-lookback:]

        price_swings_high = self._find_swing_points(recent_high)
        price_swings_low = self._find_swing_points(recent_low)
        vol_swings = self._find_swing_points(recent_vol)

        # Bearish divergence: price higher highs + volume lower highs
        if (
            len(price_swings_high) >= self._settings.DIVERGENCE_MIN_SWINGS
            and len(vol_swings) >= self._settings.DIVERGENCE_MIN_SWINGS
        ):
            price_trend = self._trend_direction(price_swings_high)
            vol_trend = self._trend_direction(vol_swings)

            if price_trend > 0 and vol_trend < 0:
                strength = min(abs(price_trend), abs(vol_trend))
                divergences.append(
                    PriceVolumeDivergence(
                        divergence_type="BEARISH_DIVERGENCE",
                        price_swings=[float(recent_high[i]) for i in price_swings_high[-2:]],
                        volume_swings=[float(recent_vol[i]) for i in vol_swings[-2:]],
                        bar_indices=[int(i + len(high) - lookback) for i in price_swings_high[-2:]],
                        strength=min(strength, 1.0),
                    )
                )

        # Bullish divergence: price lower lows + volume lower lows
        if (
            len(price_swings_low) >= self._settings.DIVERGENCE_MIN_SWINGS
            and len(vol_swings) >= self._settings.DIVERGENCE_MIN_SWINGS
        ):
            price_trend = self._trend_direction(price_swings_low)
            vol_trend = self._trend_direction(vol_swings)

            if price_trend < 0 and vol_trend < 0:
                strength = min(abs(price_trend), abs(vol_trend))
                divergences.append(
                    PriceVolumeDivergence(
                        divergence_type="BULLISH_DIVERGENCE",
                        price_swings=[float(recent_low[i]) for i in price_swings_low[-2:]],
                        volume_swings=[float(recent_vol[i]) for i in vol_swings[-2:]],
                        bar_indices=[int(i + len(low) - lookback) for i in price_swings_low[-2:]],
                        strength=min(strength, 1.0),
                    )
                )

        return divergences

    @staticmethod
    def _find_swing_points(data: NDArray[np.float64], window: int = 3) -> list[int]:
        """Find local maxima/minima indices (swing points)."""
        swings = []
        for i in range(window, len(data) - window):
            if all(data[i] >= data[i - j] for j in range(1, window + 1)) and all(
                data[i] >= data[i + j] for j in range(1, window + 1)
            ):
                swings.append(i)
            elif all(data[i] <= data[i - j] for j in range(1, window + 1)) and all(
                data[i] <= data[i + j] for j in range(1, window + 1)
            ):
                swings.append(i)
        return swings

    @staticmethod
    def _trend_direction(swing_indices: list[int]) -> float:
        """Determine trend direction from swing points. Returns +1 (up), -1 (down), 0 (flat)."""
        if len(swing_indices) < 2:
            return 0.0
        recent = swing_indices[-2:]
        diff = recent[1] - recent[0]
        if diff > 0:
            return 1.0
        elif diff < 0:
            return -1.0
        return 0.0


class VolumeAnomalyDetector:
    """Detect volume anomalies: spikes, unusual activity, price rejection patterns."""

    def __init__(self, settings: VolumeProfileSettings) -> None:
        self._settings = settings

    def detect(self, ohlcv: NDArray[np.float64]) -> list[VolumeAnomaly]:
        """Detect volume anomalies across the data."""
        if len(ohlcv) < self._settings.ANOMALY_LOOKBACK + 1:
            return []

        anomalies: list[VolumeAnomaly] = []
        lookback = self._settings.ANOMALY_LOOKBACK

        open_ = ohlcv[:, 0]
        high = ohlcv[:, 1]
        low = ohlcv[:, 2]
        close = ohlcv[:, 3]
        volume = ohlcv[:, 4]

        for i in range(lookback, len(close)):
            vol_mean = float(np.mean(volume[i - lookback : i]))
            vol_std = float(np.std(volume[i - lookback : i], ddof=1))

            if vol_mean == 0 or vol_std == 0:
                continue

            z_score = (volume[i] - vol_mean) / vol_std
            vol_ratio = volume[i] / vol_mean
            is_spike = z_score > self._settings.ANOMALY_STDDEV_THRESHOLD

            # Price rejection: long wick relative to body
            spread = high[i] - low[i]
            body = abs(close[i] - open_[i])
            wick_ratio = (spread - body) / spread if spread > 0 else 0.0
            price_rejection = wick_ratio > self._settings.VSA_WICK_RATIO_THRESHOLD and is_spike

            if is_spike:
                anomalies.append(
                    VolumeAnomaly(
                        bar_index=i,
                        volume_ratio=round(float(vol_ratio), 2),
                        z_score=round(float(z_score), 2),
                        is_spike=True,
                        price_rejection=price_rejection,
                    )
                )

        return anomalies
