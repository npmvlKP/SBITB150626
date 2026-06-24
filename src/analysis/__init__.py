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

__all__ = [
    "MarketRegime",
    "MomentumIndicators",
    "TechnicalIndicatorPipeline",
    "TechnicalIndicators",
    "TrendIndicators",
    "VIXLevel",
    "VolatilityIndicators",
    "VolumeIndicators",
]
