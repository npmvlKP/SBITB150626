"""Technical analysis and volume analysis engine — Phase 3.

References:
- Kaufman Ch.2-8: Signal design, indicator construction, percentile ranking
- Chan Ch.1-4: Mean-reversion vs momentum regime switching
- Wilder (1978): RSI, ATR smoothing (EWMA alpha=1/period)
"""

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
from src.analysis.volume import (
    PriceVolumeDivergence,
    PriceVolumeDivergenceDetector,
    VolumeAnomaly,
    VolumeAnomalyDetector,
    VolumeProfileComputer,
    VolumeProfileResult,
    VolumeSignals,
    VSASignal,
    VSASignalDetector,
    VSASignalType,
)

__all__ = [
    # Technical indicators
    "MarketRegime",
    "MomentumIndicators",
    "TechnicalIndicatorPipeline",
    "TechnicalIndicators",
    "TrendIndicators",
    "VIXLevel",
    "VolatilityIndicators",
    "VolumeIndicators",
    # Volume analysis
    "PriceVolumeDivergence",
    "PriceVolumeDivergenceDetector",
    "VolumeAnomaly",
    "VolumeAnomalyDetector",
    "VolumeProfileComputer",
    "VolumeProfileResult",
    "VolumeSignals",
    "VSASignal",
    "VSASignalDetector",
    "VSASignalType",
]
