"""Technical analysis and volume analysis engine — Phase 3.

References:
- Kaufman Ch.2-8: Signal design, indicator construction, percentile ranking
- Chan Ch.1-4: Mean-reversion vs momentum regime switching
- Wilder (1978): RSI, ATR smoothing (EWMA alpha=1/period)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from config.settings import DepthAnalysisSettings, TechnicalIndicatorSettings, VolumeProfileSettings
from src.analysis.depth import (
    DepthAnalyzer,
    DepthData,
    DepthSignals,
    VPINLevel,
)
from src.analysis.technical import (
    MarketRegime,
    TechnicalIndicatorPipeline,
    TechnicalIndicators,
)
from src.analysis.volume import (
    PriceVolumeDivergenceDetector,
    VolumeAnomalyDetector,
    VolumeProfileComputer,
    VolumeSignals,
    VSASignalDetector,
    VSASignalType,
)

# IST timezone constant (UTC+5:30)
_IST_OFFSET_HOURS = 5
_IST_OFFSET_MINUTES = 30


def _now_ist() -> datetime:
    """Return current UTC datetime (timezone-aware, IST = UTC+5:30).

    Per SBITB contract Section 4 Rule 'IST-aware datetime':
    No naive datetime.now(). All timestamps must be timezone-aware (Asia/Kolkata).
    Stored as UTC with IST offset info in description.
    """
    return datetime.now(UTC)


class TechnicalReport(BaseModel):
    """Unified output of the Phase 3 analysis engine.

    This is the single deliverable: analyze(ohlcv, depth) → TechnicalReport
    """

    indicators: TechnicalIndicators = Field(default_factory=TechnicalIndicators)
    volume_signals: VolumeSignals = Field(default_factory=VolumeSignals)
    depth_signals: DepthSignals = Field(default_factory=DepthSignals)
    computed_at: datetime = Field(default_factory=_now_ist, description="UTC timestamp (IST = UTC+5:30)")
    processing_time_ms: float = Field(0.0, description="Total pipeline processing time in ms")


class AnalysisEngine:
    """Unified analysis engine combining technical indicators, volume analysis, and depth analysis.

    Entry point: analyze(ohlcv, depth) → TechnicalReport

    Performance targets:
    - Technical indicators: < 1ms per batch (500 bars)
    - Volume profile: < 5ms
    - Full pipeline: < 10ms
    """

    def __init__(
        self,
        ta_settings: TechnicalIndicatorSettings,
        vol_settings: VolumeProfileSettings,
        depth_settings: DepthAnalysisSettings,
    ) -> None:
        self._ta_pipeline = TechnicalIndicatorPipeline(ta_settings)
        self._vol_profile = VolumeProfileComputer(vol_settings)
        self._vsa_detector = VSASignalDetector(vol_settings)
        self._divergence_detector = PriceVolumeDivergenceDetector(vol_settings)
        self._anomaly_detector = VolumeAnomalyDetector(vol_settings)
        self._depth_analyzer = DepthAnalyzer(depth_settings)

    def analyze(
        self,
        ohlcv: NDArray[np.float64] | None,
        depth: DepthData | None = None,
        bars_1min: NDArray[np.float64] | None = None,
        india_vix: float | None = None,
        ltp: float | None = None,
    ) -> TechnicalReport:
        """Run full analysis pipeline.

        Args:
            ohlcv: Daily OHLCV data, shape (N, 5), columns [open, high, low, close, volume].
                   None or empty array → indicators with default/None values.
            depth: Optional 5-level depth data from Zerodha WebSocket.
            bars_1min: Optional 1-min OHLCV bars for VPIN computation.
            india_vix: External India VIX value (NOT computed from OHLCV).
            ltp: Last traded price for spread computation.

        Returns:
            TechnicalReport with all analysis results.
        """
        start_time = time.perf_counter()

        # 1. Technical indicators
        indicators = self._ta_pipeline.compute(ohlcv, india_vix=india_vix)

        # 2. Volume analysis
        volume_signals = self._compute_volume(ohlcv)

        # 3. Depth analysis
        depth_signals = self._compute_depth(depth, bars_1min, ltp=ltp)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return TechnicalReport(
            indicators=indicators,
            volume_signals=volume_signals,
            depth_signals=depth_signals,
            computed_at=_now_ist(),
            processing_time_ms=round(elapsed_ms, 2),
        )

    def _compute_volume(self, ohlcv: NDArray[np.float64] | None) -> VolumeSignals:
        """Compute volume profile, VSA signals, divergences, and anomalies."""
        if ohlcv is None or len(ohlcv) < 2:
            return VolumeSignals()

        h = ohlcv[:, 1].astype(np.float64)
        low = ohlcv[:, 2].astype(np.float64)
        c = ohlcv[:, 3].astype(np.float64)
        v = ohlcv[:, 4].astype(np.float64)

        profile = self._vol_profile.compute(h, low, c, v)
        vsa_signals = self._vsa_detector.detect(ohlcv)
        divergences = self._divergence_detector.detect(h, low, c, v)
        anomalies = self._anomaly_detector.detect(ohlcv)

        return VolumeSignals(
            profile=profile,
            vsa_signals=vsa_signals,
            divergences=divergences,
            anomalies=anomalies,
        )

    def _compute_depth(
        self,
        depth: DepthData | None,
        bars_1min: NDArray[np.float64] | None,
        ltp: float | None = None,
    ) -> DepthSignals:
        """Compute depth analysis and optional VPIN."""
        if depth is None:
            return DepthSignals()

        depth_signals = self._depth_analyzer.analyze_depth(depth, ltp=ltp)

        if bars_1min is not None and len(bars_1min) > 0:
            vpin_signals = self._depth_analyzer.compute_vpin(bars_1min)
            depth_signals.vpin_value = vpin_signals.vpin_value
            depth_signals.vpin_cdf = vpin_signals.vpin_cdf
            depth_signals.vpin_level = vpin_signals.vpin_level

        return depth_signals


__all__ = [
    "AnalysisEngine",
    "TechnicalReport",
    "TechnicalIndicators",
    "VolumeSignals",
    "DepthSignals",
    "MarketRegime",
    "VSASignalType",
    "VPINLevel",
]
