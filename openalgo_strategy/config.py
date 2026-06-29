"""Strategy configuration for OpenAlgo NIFTY Options Strategy.

Self-contained config (no dependency on config/settings.py which pulls in
pydantic-settings, psycopg, redis etc.). Uses plain dataclasses for zero
external dependencies beyond stdlib + openalgo SDK.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class StrategyConfig:
    """Immutable strategy configuration — NIFTY options rule-based strategy.

    References:
    - Kaufman Ch.9-10: Position sizing, strangle exits
    - Chan Ch.5-6: Mean-reversion (IV selling) vs momentum (IV buying)
    - Natenberg Ch.4-8: Delta-targeted strike selection
    """

    # ── Identity ────────────────────────────────────────────────────────
    strategy_id: str = field(default_factory=lambda: os.environ.get("STRATEGY_ID", "sbitb_openalgo_001"))
    version: str = "1.0.0"

    # ── Symbol / segment ────────────────────────────────────────────────
    underlying: str = "NSE:NIFTY"
    exchange: str = "NSE"
    segment: str = "options"
    product: str = "MIS"
    nifty_lot_size: int = 25

    # ── Technical indicator periods ─────────────────────────────────────
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    adx_period: int = 14
    atr_period: int = 14
    ema_fast: int = 9
    ema_slow: int = 21
    ema_macro_fast: int = 50
    ema_macro_slow: int = 200
    bbands_period: int = 20
    bbands_stddev: float = 2.0

    # ── Regime thresholds ───────────────────────────────────────────────
    adx_trending_threshold: float = 25.0
    vix_elevated: float = 20.0
    vix_high: float = 25.0
    vix_extreme: float = 35.0

    # ── Options selling (mean-reversion) ────────────────────────────────
    selling_iv_rank_min: float = 40.0
    selling_adx_max: float = 25.0
    selling_strike_sd: float = 2.0
    selling_premium_decay_exit: float = 0.50
    selling_sl_multiplier: float = 2.0
    selling_days_before_expiry: int = 2

    # ── Options buying (momentum) ───────────────────────────────────────
    buying_iv_rank_max: float = 30.0
    buying_adx_min: float = 25.0
    buying_delta_min: float = 0.50
    buying_delta_max: float = 0.60
    buying_target_rr: float = 2.0
    buying_days_before_expiry: int = 3

    # ── Risk management ─────────────────────────────────────────────────
    fixed_fractional_pct: Decimal = Decimal("0.02")
    max_lots_per_trade: int = 10
    max_daily_signals: int = 6
    max_open_positions: int = 4
    max_order_value: Decimal = Decimal("200000")
    sebi_max_ops: int = 3

    # ── Candle interval ────────────────────────────────────────────────
    candle_interval: str = "5minute"
    lookback_bars: int = 250

    # ── SEBI compliance constants ──────────────────────────────────────
    trading_start_ist: str = "09:15"
    trading_end_ist: str = "15:30"


_DEFAULT_STRATEGY_ID = "sbitb_openalgo_001"


def get_config() -> StrategyConfig:
    """Build config from environment variables (OpenAlgo injects these)."""
    return StrategyConfig(
        strategy_id=os.environ.get("STRATEGY_ID", _DEFAULT_STRATEGY_ID),
    )
