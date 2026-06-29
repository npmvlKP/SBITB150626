"""Application settings with Pydantic BaseSettings — SEBI compliance constants
and risk limits."""

from datetime import date, time
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class KillSwitchLevel(StrEnum):
    """Kill switch levels — per MiFID II Art.

    17, NIST RS.RP-1, ISO A.8.26.
    """

    INACTIVE = "inactive"
    THROTTLE = "throttle"
    PAUSE = "pause"
    KILL = "kill"


class ComplianceSettings(BaseSettings):
    """SEBI compliance enforcement constants — verified against NSE/INVG/67858,
    SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013."""

    model_config = SettingsConfigDict(
        env_prefix="COMPLIANCE_",
        env_file=".env",
        extra="ignore",
    )

    MAX_ORDERS_PER_SECOND: int = Field(default=3, ge=1, le=10)
    MAX_ORDERS_PER_MINUTE: int = Field(default=60, ge=1, le=1000)
    MAX_ORDERS_PER_DAY: int = Field(default=500, ge=1, le=10000)
    SEBI_OPS_REGISTRATION_THRESHOLD: int = Field(default=10, ge=1)
    TRADING_START_IST: time = time(9, 15)
    TRADING_END_IST: time = time(15, 30)
    MCX_TRADING_START_IST: time = time(9, 0)
    MCX_TRADING_END_MORNING_IST: time = time(14, 30)
    MCX_TRADING_START_EVENING_IST: time = time(17, 0)
    MCX_TRADING_END_EVENING_IST: time = time(23, 30)
    ALLOWED_SEGMENTS: list[str] = ["NSE", "MCX"]
    ALLOWED_NSE_INSTRUMENTS: list[str] = ["NIFTY", "BANKNIFTY"]
    ALLOWED_MCX_INSTRUMENTS: list[str] = ["GOLD", "SILVER", "CRUDEOIL"]
    ALGO_TAG_FORMAT: str = "{strategy_id}:{version}"
    SEBI_ALGO_CIRCULAR: str = "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013"
    NSE_ATF_CIRCULAR: str = "NSE/INVG/67858"
    # NOTE: NO 500ms resting time constant — was proposed in 2016 discussion paper
    # but NEVER mandated per SEBI/HO/MRD/DP/CIR/P/2018/62

    @field_validator("MAX_ORDERS_PER_SECOND")
    @classmethod
    def validate_max_orders_per_second(cls, v: int) -> int:
        if v > 10:
            raise ValueError("MAX_ORDERS_PER_SECOND cannot exceed 10 per SEBI NSE/INVG/67858")
        return v


class RiskSettings(BaseSettings):
    """Client-side risk limits — self-imposed per CIR/MRD/DP/09/2012."""

    model_config = SettingsConfigDict(
        env_prefix="RISK_",
        env_file=".env",
        extra="ignore",
    )

    MAX_ORDER_VALUE_PER_TRADE: Decimal = Field(default=Decimal("200000"), ge=Decimal("0"))
    MAX_POSITION_NOTIONAL_PER_SYMBOL: Decimal = Field(default=Decimal("500000"), ge=Decimal("0"))
    MAX_TOTAL_EXPOSURE: Decimal = Field(default=Decimal("2000000"), ge=Decimal("0"))
    MARGIN_UTILIZATION_THRESHOLD: Decimal = Field(default=Decimal("0.80"), ge=Decimal("0"), le=Decimal("1"))
    MARGIN_UTILIZATION_KILL: Decimal = Field(default=Decimal("0.95"), ge=Decimal("0"), le=Decimal("1"))
    DAILY_LOSS_LIMIT: Decimal = Field(default=Decimal("50000"), ge=Decimal("0"))
    ORDER_REJECTION_THRESHOLD: int = Field(default=10, ge=1)
    CIRCUIT_LIMIT_PCT: Decimal = Field(default=Decimal("0.05"), ge=Decimal("0"), le=Decimal("1"))

    @model_validator(mode="after")
    def validate_margin_thresholds(self) -> "RiskSettings":
        if self.MARGIN_UTILIZATION_THRESHOLD >= self.MARGIN_UTILIZATION_KILL:
            raise ValueError("MARGIN_UTILIZATION_THRESHOLD must be less than MARGIN_UTILIZATION_KILL")
        return self


class KillSwitchSettings(BaseSettings):
    """Kill switch configuration — per MiFID II Art.

    17, NIST RS.RP-1, ISO A.8.26.
    """

    model_config = SettingsConfigDict(
        env_prefix="KILLSWITCH_",
        env_file=".env",
        extra="ignore",
    )

    THROTTLE_RATE_PCT: Decimal = Field(default=Decimal("0.10"), ge=Decimal("0"), le=Decimal("1"))
    REQUIRE_MANUAL_RE_ENABLE: bool = True
    ACTIVATION_PATHS: list[str] = ["keyboard", "telegram", "rest_api"]


class AuditSettings(BaseSettings):
    """Audit trail configuration — 7-year retention per SEBI requirement
    (5+)."""

    model_config = SettingsConfigDict(
        env_prefix="AUDIT_",
        env_file=".env",
        extra="ignore",
    )

    RETENTION_YEARS: int = Field(default=7, ge=5)
    CHECKSUM_ALGORITHM: str = "sha256"
    NTP_SERVER: str = "in.pool.ntp.org"
    MAX_NTP_OFFSET_MS: int = Field(default=500, ge=100)


class PositionLimitSettings(BaseSettings):
    """Position limit settings — per SEBI/EXCHANGE requirements."""

    model_config = SettingsConfigDict(
        env_prefix="POSITION_",
        env_file=".env",
        extra="ignore",
    )

    NIFTY_LOT_SIZE: int = Field(default=25, ge=1)
    BANKNIFY_LOT_SIZE: int = Field(default=15, ge=1)
    MAX_LOT_SIZE_PER_ORDER: int = Field(default=100, ge=1)
    MAX_POSITIONS_PER_SYMBOL: int = Field(default=10, ge=1)


class QuantitativeRiskSettings(BaseSettings):
    """Quantitative risk engine settings — VaR/GARCH/EVT parameters."""

    model_config = SettingsConfigDict(
        env_prefix="QUANT_",
        env_file=".env",
        extra="ignore",
    )

    VAR_CONFIDENCE_LEVEL: float = Field(default=0.99, ge=0.9, le=0.999)
    VAR_LOOKBACK_DAYS: int = Field(default=252, ge=30)
    VAR_HOLDING_PERIOD_DAYS: int = Field(default=1, ge=1)
    VAR_MAX_PORTFOLIO_VAR: Decimal = Field(default=Decimal("100000"), ge=Decimal("0"))
    VAR_MAX_PORTFOLIO_CVAR: Decimal = Field(default=Decimal("150000"), ge=Decimal("0"))
    VAR_ENGINE_TIMEOUT_SECONDS: float = Field(default=30.0, ge=1)
    VAR_ENGINE_FALLBACK_ON_TIMEOUT: bool = True
    VAR_METHOD: str = Field(default="garch")
    GARCH_MODEL_TYPE: str = Field(default="GARCH")
    GARCH_P: int = Field(default=1, ge=1, le=3)
    GARCH_Q: int = Field(default=1, ge=1, le=3)
    GARCH_DISTRIBUTION: str = Field(default="normal")
    GARCH_REFIT_FREQUENCY_DAYS: int = Field(default=7, ge=1)
    EVT_THRESHOLD_PERCENTILE: float = Field(default=0.95, ge=0.8, le=0.99)
    EVT_MIN_TAIL_SAMPLES: int = Field(default=30, ge=10)
    STRESS_SCENARIO_PCT_DROP: list[float] = Field(default_factory=lambda: [-0.05, -0.10, -0.15, -0.20, -0.25, -0.30])
    MONTE_CARLO_SIMULATIONS: int = Field(default=10000, ge=1000)


class BrokerSettings(BaseSettings):
    """Per-broker configurations — Zerodha primary, Angel One fallback."""

    model_config = SettingsConfigDict(
        env_prefix="BROKER_",
        env_file=".env",
        extra="ignore",
    )

    # Zerodha
    ZERODHA_API_KEY: str = Field(default="", validation_alias="ZERODHA_API_KEY")
    ZERODHA_API_SECRET: str = Field(default="", validation_alias="ZERODHA_API_SECRET")
    ZERODHA_ACCESS_TOKEN: str = Field(default="", validation_alias="ZERODHA_ACCESS_TOKEN")
    ZERODHA_TOTP_SECRET: str = Field(default="", validation_alias="ZERODHA_TOTP_SECRET")
    ZERODHA_API_RATE_QUOTES: int = Field(default=1, ge=1)
    ZERODHA_API_RATE_HISTORICAL: int = Field(default=3, ge=1)
    ZERODHA_API_RATE_ORDERS: int = Field(default=10, ge=1)
    ZERODHA_WS_MAX_CONNECTIONS: int = Field(default=3, ge=1, le=10)
    ZERODHA_WS_MAX_INSTRUMENTS: int = Field(default=9000, ge=1)
    ZERODHA_SESSION_EXPIRY_IST: time = Field(default=time(6, 0))
    ZERODHA_MARKET_PROTECTION: Decimal = Decimal("-1")
    ZERODHA_MONTHLY_FEE: int = Field(default=500, ge=0)
    ZERODHA_TAG_MAX_LENGTH: int = Field(default=20, ge=1, le=40)
    ZERODHA_NO_SANDBOX: bool = True

    # Angel One
    ANGEL_ONE_API_KEY: str = Field(default="", validation_alias="ANGEL_ONE_API_KEY")
    ANGEL_ONE_API_SECRET: str = Field(default="", validation_alias="ANGEL_ONE_API_SECRET")
    ANGEL_ONE_CLIENT_CODE: str = Field(default="", validation_alias="ANGEL_ONE_CLIENT_CODE")
    ANGEL_ONE_PASSWORD: str = Field(default="", validation_alias="ANGEL_ONE_PASSWORD")
    ANGEL_ONE_TOTP_SECRET: str = Field(default="", validation_alias="ANGEL_ONE_TOTP_SECRET")

    # Dhan
    DHAN_CLIENT_ID: str = Field(default="", validation_alias="DHAN_CLIENT_ID")
    DHAN_ACCESS_TOKEN: str = Field(default="", validation_alias="DHAN_ACCESS_TOKEN")

    # Notifications
    TELEGRAM_BOT_TOKEN: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")


# PHASE 2 ADDITIONS ─────────────────────────────────────────────────────────────────────


class DataPipelineSettings(BaseSettings):
    """Data pipeline configuration for market and price feed."""

    model_config = SettingsConfigDict(env_prefix="PIPELINE_", env_file=".env", extra="ignore")

    HISTORICAL_START_DATE: date = date(2023, 6, 1)  # 3 years back from today
    HISTORICAL_END_DATE: date = date(2026, 6, 1)  # Today; override for incremental
    FO_SYMBOLS: list[str] = ["NIFTY", "BANKNIFTY"]
    CM_SYMBOLS: list[str] = ["NIFTY 50", "NIFTY BANK"]
    MCX_SYMBOLS: list[str] = ["GOLD", "SILVER", "CRUDEOIL"]
    DOWNLOAD_DIR: str = "data/bhavcopy"
    CHECKPOINT_TABLE: str = "download_checkpoint"
    BATCH_SIZE: int = 5000  # Rows per bulk INSERT
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_SEC: float = 2.0
    EVENT_LOG_TABLE: str = "market_events"


class GreeksSettings(BaseSettings):
    """Greek calculation settings for option pricing models."""

    model_config = SettingsConfigDict(env_prefix="GREEKS_", env_file=".env", extra="ignore")

    RFR_METHOD: Literal["t_bill", "futures_basis"] = "t_bill"
    RFR_T_BILL_DEFAULT: float = 0.065  # RBI 91-day T-bill yield fallback
    RFR_T_BILL_FETCH_URL: str = "https://www.rbi.org.in/scripts/BS_NSDPDisplay.aspx"  # RBI yield page
    RFR_FUTURES_SYMBOL: str = "NIFTY"  # Use NIFTY futures for basis calculation
    MIN_TTM_DAYS: int = 1  # Minimum time-to-maturity in calendar days
    MIN_OPTION_PRICE: float = 0.05  # Skip IV computation for options priced below this
    IV_MAX_ITERATIONS: int = 100  # Newton-Raphson iterations for IV
    IV_PRECISION: float = 1e-6  # Convergence threshold
    IV_UPPER_BOUND: float = 5.0  # Max IV = 500%
    IV_LOWER_BOUND: float = 0.001  # Min IV = 0.1%
    QUANTLIB_CALENDAR: str = "India"  # QuantLib calendar for Indian holidays


class WebSocketSettings(BaseSettings):
    """WebSocket connections for market data streaming."""

    model_config = SettingsConfigDict(env_prefix="WS_", env_file=".env", extra="ignore")

    RECONNECT_INITIAL_DELAY_SEC: float = 1.0
    RECONNECT_MAX_DELAY_SEC: float = 60.0
    RECONNECT_BACKOFF_FACTOR: float = 2.0
    RECONNECT_MAX_ATTEMPTS: int = 100
    REAUTH_SCHEDULE_HOUR_IST: int = 6  # Daily re-auth at 6:XX AM IST
    REAUTH_SCHEDULE_MINUTE_IST: int = 1
    RING_BUFFER_SIZE: int = 10000  # Max ticks held before backpressure
    PERSIST_INTERVAL_SEC: float = 5.0  # Batch write ticks to TimescaleDB every N sec
    REDIS_TTL_SEC: int = 86400  # 24h TTL for Redis tick cache
    REDIS_KEY_PREFIX: str = "tick:"
    NIFTY_ATM_STRIKES_EACH_SIDE: int = 25  # 25 above + 25 below = 50 strikes
    MCX_INSTRUMENTS: list[str] = ["GOLD", "SILVER", "CRUDEOIL"]
    HEARTBEAT_TIMEOUT_SEC: float = 5.0  # Zerodha sends heartbeat every ~2-3s


# PHASE 3 ADDITIONS ─────────────────────────────────────────────────────────────────────
# Technical Analysis + Volume Analysis Engine Settings
# Reference: Kaufman Ch.2-8, Chan Ch.1-4, Dalton "Mind Over Markets", Weis "Trades About to Happen", Coulling "VPA"


class TechnicalIndicatorSettings(BaseSettings):
    """Technical indicator parameters — momentum, volatility, trend, volume, regime detection.

    CRITICAL TA-Lib default overrides documented in each field description:
    - BBANDS: TA-Lib default timeperiod=5 → override to 20
    - EMA: TA-Lib default timeperiod=30 → must pass explicit periods
    - CCI: TA-Lib default timeperiod=14 → override to 20
    - CMF: NOT TA-Lib ADOSC (different formula) — custom implementation required
    - Supertrend/VWAP/Volume Rate: NOT in TA-Lib — custom implementations required

    References:
    - Kaufman Ch.7: EMA alignment (fastest >= 1/4 slowest), percentile ranking
    - Kaufman Ch.4-5: RSI, MACD, ATR with Wilder smoothing
    - Chan Ch.1-4: Regime switching (ADX + Hurst for trending vs mean-reverting)
    - Wilder (1978): RSI, ATR EWMA smoothing (alpha=1/period)
    """

    model_config = SettingsConfigDict(env_prefix="TA_", env_file=".env", extra="ignore")

    # ── Momentum indicators ──────────────────────────────────────────────────────────

    RSI_PERIOD: int = Field(default=14, ge=2, le=100, description="RSI lookback period (Wilder smoothing alpha=1/14)")
    MACD_FAST: int = Field(default=12, ge=2, le=50, description="MACD fast EMA period")
    MACD_SLOW: int = Field(default=26, ge=5, le=100, description="MACD slow EMA period")
    MACD_SIGNAL: int = Field(default=9, ge=2, le=50, description="MACD signal line period")
    ADX_PERIOD: int = Field(default=14, ge=2, le=100, description="ADX lookback period")
    CCI_PERIOD: int = Field(
        default=20, ge=2, le=100, description="CCI lookback period (TA-Lib default=14, overridden to 20)"
    )

    # ── Volatility indicators ─────────────────────────────────────────────────────────

    BBANDS_PERIOD: int = Field(
        default=20, ge=2, le=100, description="Bollinger Bands period (TA-Lib default=5, overridden to 20)"
    )
    BBANDS_STDDEV: float = Field(default=2.0, ge=0.5, le=4.0, description="Bollinger Bands standard deviations")
    ATR_PERIOD: int = Field(default=14, ge=2, le=100, description="ATR lookback period (Wilder smoothing)")
    INDIA_VIX_ELEVATED: float = Field(default=20.0, ge=5.0, le=50.0, description="India VIX elevated threshold")
    INDIA_VIX_HIGH: float = Field(default=25.0, ge=10.0, le=60.0, description="India VIX high threshold")
    INDIA_VIX_EXTREME: float = Field(default=35.0, ge=15.0, le=80.0, description="India VIX extreme threshold")

    # ── Trend indicators ──────────────────────────────────────────────────────────────

    SUPERTREND_PERIOD: int = Field(
        default=10, ge=2, le=50, description="Supertrend ATR period (Wilders-smoothed, NOT simple RMA)"
    )
    SUPERTREND_MULTIPLIER: float = Field(default=3.0, ge=1.0, le=10.0, description="Supertrend ATR multiplier")
    EMA_PERIODS: list[int] = Field(
        default=[9, 21, 50, 200], description="EMA periods (9/21 for signal crossover, 50/200 for macro trend)"
    )
    VWAP_ANCHOR_TIME: time = Field(default=time(9, 15), description="VWAP session anchor (NSE open)")

    # ── Volume indicators ─────────────────────────────────────────────────────────────

    OBV_SMOOTHING_PERIOD: int = Field(default=21, ge=5, le=100, description="OBV EMA smoothing period (Kaufman Ch.6)")
    MFI_PERIOD: int = Field(default=14, ge=2, le=100, description="Money Flow Index period")
    CMF_PERIOD: int = Field(
        default=20, ge=5, le=100, description="Chaikin Money Flow period (custom CMF — NOT TA-Lib ADOSC)"
    )
    VOLUME_RATE_PERIOD: int = Field(default=20, ge=5, le=100, description="Volume rate SMA period")

    # ── Normalization (Kaufman Ch.7: percentile ranking for cross-indicator comparison) ─

    PERCENTILE_LOOKBACK: int = Field(
        default=252, ge=30, le=504, description="Percentile ranking lookback (1 trading year)"
    )
    PERCENTILE_MIN_HISTORY: int = Field(
        default=63, ge=20, le=126, description="Minimum bars required for percentile computation"
    )

    # ── EMA alignment validation (Kaufman Ch.7: fastest >= 1/4 of slowest) ────────────

    EMA_MACRO_FAST: int = Field(default=50, description="Macro trend fast EMA (must be >= 200/4 = 50 per Kaufman Ch.7)")
    EMA_MACRO_SLOW: int = Field(default=200, description="Macro trend slow EMA")

    # ── Regime detection (Chan Ch.1-4) ─────────────────────────────────────────────────

    ADX_TRENDING_THRESHOLD: float = Field(
        default=25.0, ge=15.0, le=40.0, description="ADX above this = trending regime"
    )
    HURST_TRENDING_THRESHOLD: float = Field(
        default=0.5, ge=0.4, le=0.7, description="Hurst exponent > this = trending regime (H<0.5 = mean-reverting)"
    )
    HURST_LOOKBACK: int = Field(default=100, ge=50, le=500, description="Hurst exponent R/S analysis lookback")


class VolumeProfileSettings(BaseSettings):
    """Volume profile, VSA (Volume Spread Analysis), price-volume divergence, and volume anomaly detection.

    References:
    - Dalton "Mind Over Markets" & CME Market Profile handbook: 68.2% value area (canonical 1 sigma)
    - Weis "Trades About to Happen" Ch.3: 5-bar context window for VSA confirmation
    - Coulling "Volume Price Analysis": demand/supply bar classification
    """

    model_config = SettingsConfigDict(env_prefix="VOLPROF_", env_file=".env", extra="ignore")

    # ── Volume profile ────────────────────────────────────────────────────────────────

    NUM_PRICE_BINS: int = Field(default=24, ge=10, le=100, description="Number of price bins for volume histogram")
    VALUE_AREA_PCT: float = Field(
        default=0.682, ge=0.5, le=0.95, description="Value area = 68.2% (CME/Dalton canonical 1 sigma, NOT 70%)"
    )
    POC_MIN_VOLUME_PCT: float = Field(
        default=0.05, ge=0.01, le=0.20, description="POC bin must have >= this percentage of total volume"
    )

    # ── VSA (Volume Spread Analysis — Weis + Coulling) ────────────────────────────────

    VSA_CONTEXT_WINDOW: int = Field(
        default=5,
        ge=3,
        le=10,
        description="Surrounding bars for VSA signal confirmation (Weis Ch.3: 2 prior + current + 2 after)",
    )
    VSA_VOLUME_SPIKE_MULTIPLIER: float = Field(
        default=2.0, ge=1.5, le=5.0, description="Volume > this * 20-day average = spike"
    )
    VSA_SPREAD_COMPARISON_PERIOD: int = Field(
        default=20, ge=10, le=50, description="Bars for average spread comparison"
    )
    VSA_WICK_RATIO_THRESHOLD: float = Field(
        default=0.5, ge=0.3, le=0.8, description="Wick-to-body ratio for rejection signals"
    )

    # ── Price-Volume Divergence ────────────────────────────────────────────────────────

    DIVERGENCE_LOOKBACK: int = Field(default=20, ge=10, le=50, description="Lookback for divergence detection")
    DIVERGENCE_MIN_SWINGS: int = Field(default=2, ge=2, le=5, description="Minimum swing points for divergence")

    # ── Volume anomalies ──────────────────────────────────────────────────────────────

    ANOMALY_STDDEV_THRESHOLD: float = Field(
        default=2.0, ge=1.5, le=4.0, description="Volume > mean + N*sigma = anomaly"
    )
    ANOMALY_LOOKBACK: int = Field(default=20, ge=10, le=60, description="Lookback for volume mean/stddev computation")


class DepthAnalysisSettings(BaseSettings):
    """Order book depth analysis and VPIN (Volume-Synchronized Probability of Informed Trading).

    Depth levels: Zerodha provides 5, Dhan provides up to 200.

    VPIN: Uses BVC (Bulk Volume Classification) since Zerodha lacks tick-level trade direction.
    BVC achieves ~85-95% accuracy vs full tick data (Easley/Lopez de Prado/O'Hara 2012).
    Requires 1-min OHLCV bars (NOT 5-level depth — that is insufficient for VPIN).

    References:
    - Easley, Lopez de Prado, O'Hara (2012): VPIN methodology
    - Bhabra et al.: BVC (Bulk Volume Classification) for trade direction estimation
    """

    model_config = SettingsConfigDict(env_prefix="DEPTH_", env_file=".env", extra="ignore")

    # ── Depth analysis (Zerodha 5-level, Dhan 200-level) ──────────────────────────────

    DEPTH_LEVELS: int = Field(
        default=5, ge=1, le=200, description="Number of depth levels (5 for Zerodha, 200 for Dhan)"
    )
    IMBALANCE_THRESHOLD: float = Field(default=2.0, ge=1.5, le=5.0, description="Bid/ask ratio above this = imbalance")
    SPREAD_BPS_THRESHOLD: float = Field(
        default=5.0, ge=1.0, le=20.0, description="Spread > N basis points = wide spread alert"
    )

    # ── VPIN (Volume-Synchronized Probability of Informed Trading) ─────────────────────

    VPIN_ENABLED: bool = Field(default=True, description="Enable VPIN computation")
    VPIN_BUCKET_SIZE_METHOD: Literal["fixed", "daily_adv"] = Field(
        default="daily_adv", description="Bucket size method: fixed=N shares or daily_adv/50"
    )
    VPIN_FIXED_BUCKET_SIZE: int = Field(
        default=5000, ge=100, le=100000, description="Fixed bucket size if method=fixed"
    )
    VPIN_DAILY_ADV_LOOKBACK: int = Field(
        default=20, ge=5, le=60, description="Days for Average Daily Volume computation"
    )
    VPIN_NUM_BUCKETS: int = Field(
        default=50, ge=20, le=200, description="Number of volume buckets for VPIN rolling window"
    )
    VPIN_CDF_ELEVATED: float = Field(default=0.90, ge=0.75, le=0.95, description="VPIN CDF > this = elevated toxicity")
    VPIN_CDF_HIGH: float = Field(default=0.95, ge=0.85, le=0.99, description="VPIN CDF > this = high toxicity")
    VPIN_CDF_EXTREME: float = Field(default=0.99, ge=0.95, le=0.999, description="VPIN CDF > this = extreme toxicity")
    VPIN_USE_BVC: bool = Field(
        default=True,
        description="Use BVC (Bulk Volume Classification) — required since Zerodha lacks tick-level trade direction",
    )
    VPIN_MIN_1MIN_BARS: int = Field(
        default=50, ge=20, le=200, description="Minimum 1-min bars required for VPIN computation"
    )


# PHASE 4 ADDITIONS ──────────────────────────────────────────────────────────────────────
# Market Strength Engine Settings
# Reference: Dalton "Mind Over Markets" Ch.4-6, Weis Ch.2-3, Kaufman Ch.7, Chan Ch.2-3


class MarketStrengthSettings(BaseSettings):
    """Composite market strength scoring configuration — 9-feature weighted model.

    References:
    - Dalton Ch.6: Market structure (breadth, VIX, flow) > microstructure (OI, PCR)
    - Weis Ch.3: Volume confirmation > price-only signals
    - Kaufman Ch.7: Normalize all indicators to [0, 100]; weights must sum to 1.0
    - Chan Ch.2-3: Contrarian signals (PCR), VIX extreme recovery
    """

    model_config = SettingsConfigDict(env_prefix="MKTSTR_", env_file=".env", extra="ignore")

    # ── Regime boundaries (Plan.txt line 369-371) ──────────────────────────────────────

    WEAK_THRESHOLD: int = Field(default=30, ge=0, le=50, description="Score <= this = WEAK regime")
    STRONG_THRESHOLD: int = Field(default=60, ge=40, le=100, description="Score > this = STRONG regime")

    # ── Feature weights (MUST sum to 1.0) ──────────────────────────────────────────────
    # Dalton Ch.6: Market structure (breadth, VIX, flow) > microstructure (OI, PCR)

    WEIGHT_AD_RATIO: float = Field(default=0.10, ge=0.0, le=1.0, description="Advance/Decline ratio weight")
    WEIGHT_VWAP_DISTANCE: float = Field(default=0.08, ge=0.0, le=1.0, description="VWAP distance weight")
    WEIGHT_OI_CHANGE: float = Field(default=0.08, ge=0.0, le=1.0, description="Open Interest change weight")
    WEIGHT_PCR: float = Field(default=0.08, ge=0.0, le=1.0, description="Put/Call ratio weight")
    WEIGHT_VOLUME_PROFILE: float = Field(default=0.10, ge=0.0, le=1.0, description="Volume profile position weight")
    WEIGHT_MARKET_BREADTH: float = Field(
        default=0.15, ge=0.0, le=1.0, description="Market breadth weight (structural, Dalton Ch.6)"
    )
    WEIGHT_SECTOR_MOMENTUM: float = Field(default=0.10, ge=0.0, le=1.0, description="Sector momentum weight")
    WEIGHT_INDIA_VIX: float = Field(
        default=0.15, ge=0.0, le=1.0, description="India VIX weight (structural, Weis Ch.3)"
    )
    WEIGHT_FII_DII_FLOW: float = Field(
        default=0.16, ge=0.0, le=1.0, description="FII/DII flow weight (institutional, Dalton Ch.6)"
    )

    # ── Feature scoring ranges ─────────────────────────────────────────────────────────

    AD_RATIO_EXTREME_BULLISH: float = Field(default=3.0, ge=1.0, le=10.0, description="A/D ratio >= this = 100 score")
    AD_RATIO_EXTREME_BEARISH: float = Field(default=0.33, ge=0.1, le=1.0, description="A/D ratio <= this = 0 score")
    VWAP_DISTANCE_EXTREME: float = Field(
        default=2.0, ge=0.5, le=5.0, description="VWAP distance (in ATR units) >= this = extreme"
    )
    OI_CHANGE_SPIKE_THRESHOLD: float = Field(
        default=10.0, ge=1.0, le=50.0, description="OI change % >= this = significant participation"
    )
    OI_CHANGE_LOOKBACK_DAYS: int = Field(default=5, ge=1, le=20, description="Days for OI change baseline")
    PCR_EXTREME_BULLISH: float = Field(default=1.5, ge=0.5, le=3.0, description="PCR >= this = contrarian bullish")
    PCR_EXTREME_BEARISH: float = Field(default=0.4, ge=0.1, le=0.8, description="PCR <= this = contrarian bearish")
    PCR_NEUTRAL: float = Field(default=0.9, ge=0.5, le=1.5, description="PCR around this = neutral")
    BREADTH_EXTREME_BULLISH: float = Field(
        default=0.80, ge=0.5, le=1.0, description="% stocks above 20-EMA >= this = 100 score"
    )
    BREADTH_EXTREME_BEARISH: float = Field(
        default=0.20, ge=0.0, le=0.5, description="% stocks above 20-EMA <= this = 0 score"
    )
    SECTOR_MOMENTUM_LOOKBACK: int = Field(default=20, ge=5, le=60, description="Days for sector momentum calculation")
    SECTOR_MOMENTUM_EXTREME: float = Field(
        default=5.0, ge=1.0, le=15.0, description="Sector relative strength >= this % = extreme"
    )
    VIX_BULLISH_THRESHOLD: float = Field(
        default=15.0, ge=5.0, le=25.0, description="VIX < this = bullish (complacency)"
    )
    VIX_BEARISH_THRESHOLD: float = Field(default=25.0, ge=15.0, le=40.0, description="VIX > this = bearish (fear)")
    VIX_EXTREME_THRESHOLD: float = Field(
        default=35.0, ge=25.0, le=60.0, description="VIX > this = extreme (contrarian bullish possible)"
    )
    VIX_TREND_MODIFIER: float = Field(
        default=8.0, ge=0.0, le=20.0, description="Points to add/subtract for VIX trend direction"
    )
    FII_DII_FLOW_LOOKBACK: int = Field(default=5, ge=1, le=30, description="Days for FII/DII net flow aggregation")
    FII_DII_EXTREME_BUY: float = Field(
        default=5000.0, ge=100.0, le=50000.0, description="Net FII+DII buy >= this Cr = extreme bullish"
    )
    FII_DII_EXTREME_SELL: float = Field(
        default=-5000.0, ge=-50000.0, le=-100.0, description="Net FII+DII sell <= this Cr = extreme bearish"
    )

    # ── Sector indices for momentum ────────────────────────────────────────────────────

    SECTOR_INDICES: list[str] = Field(
        default=["NIFTY IT", "NIFTY BANK", "NIFTY PHARMA", "NIFTY FMCG", "NIFTY METAL"],
        description="NSE sector indices for relative strength computation",
    )

    # ── Data source configuration ──────────────────────────────────────────────────────

    AD_RATIO_SOURCE: Literal["jugaad_data", "manual"] = Field(default="jugaad_data")
    FII_DII_SOURCE: Literal["kite_historical", "jugaad_data", "manual"] = Field(default="kite_historical")
    SECTOR_DATA_SOURCE: Literal["jugaad_data", "manual"] = Field(default="jugaad_data")

    # ── Caching ────────────────────────────────────────────────────────────────────────

    FEATURE_CACHE_TTL_SECONDS: int = Field(
        default=300, ge=60, le=3600, description="Feature cache TTL in seconds (5 min default)"
    )

    @model_validator(mode="after")
    def validate_market_strength_settings(self) -> "MarketStrengthSettings":
        """Feature weights MUST sum to 1.0 (Kaufman Ch.7 normalization)."""
        total = (
            self.WEIGHT_AD_RATIO
            + self.WEIGHT_VWAP_DISTANCE
            + self.WEIGHT_OI_CHANGE
            + self.WEIGHT_PCR
            + self.WEIGHT_VOLUME_PROFILE
            + self.WEIGHT_MARKET_BREADTH
            + self.WEIGHT_SECTOR_MOMENTUM
            + self.WEIGHT_INDIA_VIX
            + self.WEIGHT_FII_DII_FLOW
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Feature weights must sum to 1.0, got {total:.4f}")
        if self.WEAK_THRESHOLD >= self.STRONG_THRESHOLD:
            raise ValueError(
                f"WEAK_THRESHOLD ({self.WEAK_THRESHOLD}) must be < STRONG_THRESHOLD ({self.STRONG_THRESHOLD})"
            )
        return self


# PHASE 5 ADDITIONS ──────────────────────────────────────────────────────────────────────
# Rule-Based Options Strategy Settings
# Reference: Kaufman Ch.9-12, Chan Ch.5-8


class StrategySettings(BaseSettings):
    """Options selling + buying strategy configuration.

    References:
    - Kaufman Ch.9-10: Position sizing (fixed-fractional, Kelly, optimal-f), strangle exits
    - Chan Ch.5-6: Mean-reversion (high IV selling) vs momentum (low IV buying)
    - Chan Ch.6: Minimum 2:1 R:R for directional options
    """

    model_config = SettingsConfigDict(env_prefix="STRAT_", env_file=".env", extra="ignore")

    # ── Signal evaluation interval ─────────────────────────────────────────────────────
    SIGNAL_EVAL_INTERVAL_SECONDS: int = Field(
        default=300, ge=60, le=3600, description="Seconds between signal evaluations (default 5 min)"
    )

    # ── NIFTY lot size (Correction #1) ─────────────────────────────────────────────────
    NIFTY_LOT_SIZE: int = Field(default=25, ge=1, description="NIFTY options lot size (25 since Nov 2021)")

    # ── Options Selling Strategy (mean-reversion) ──────────────────────────────────────
    SELLING_IV_RANK_MIN: float = Field(
        default=40.0, ge=0.0, le=100.0, description="Minimum IV rank for selling entry (Chan Ch.5)"
    )
    SELLING_ADX_MAX: float = Field(
        default=25.0, ge=10.0, le=50.0, description="Maximum ADX for selling entry (range-bound filter)"
    )
    SELLING_MKT_STRENGTH_MIN: float = Field(
        default=31.0, ge=0.0, le=100.0, description="Minimum market strength score for selling (NEUTRAL regime)"
    )
    SELLING_MKT_STRENGTH_MAX: float = Field(
        default=60.0, ge=0.0, le=100.0, description="Maximum market strength score for selling (NEUTRAL regime)"
    )
    SELLING_VIX_MIN: float = Field(default=15.0, ge=5.0, le=40.0, description="Minimum India VIX for selling entry")

    # ── Strike selection: Selling ──────────────────────────────────────────────────────
    SELLING_STRIKE_SD_MULTIPLIER: float = Field(
        default=2.0, ge=1.0, le=4.0, description="SD multiplier for selling strike selection (2SD default)"
    )
    SELLING_STRIKE_MIN_OI: int = Field(default=10000, ge=100, description="Minimum OI on selected strike")
    SELLING_STRIKE_MIN_VOLUME: int = Field(default=1000, ge=100, description="Minimum volume on selected strike")

    # ── Exit: Selling ──────────────────────────────────────────────────────────────────
    SELLING_PREMIUM_DECAY_EXIT_PCT: float = Field(
        default=0.50,
        ge=0.20,
        le=0.90,
        description="Exit when premium decays >= this fraction (50% default, Kaufman Ch.10)",
    )
    SELLING_PREMIUM_DECAY_SCOPE: Literal["combined", "either_leg"] = Field(
        default="combined", description="Decay exit: 'combined' = total premium, 'either_leg' = any single leg"
    )
    SELLING_SL_MULTIPLIER: float = Field(
        default=2.0, ge=1.0, le=5.0, description="Stop loss = SL_MULTIPLIER * combined premium received"
    )
    SELLING_DAYS_BEFORE_EXPIRY_EXIT: int = Field(
        default=2, ge=1, le=5, description="Exit N trading days before expiry (gamma risk)"
    )
    SELLING_REGIME_CHANGE_EXIT: bool = Field(default=True, description="Exit on regime change outside NEUTRAL")

    # ── Options Buying Strategy (momentum) ─────────────────────────────────────────────
    BUYING_IV_RANK_MAX: float = Field(
        default=30.0, ge=0.0, le=60.0, description="Maximum IV rank for buying entry (Chan Ch.6: low IV = underpriced)"
    )
    BUYING_ADX_MIN: float = Field(
        default=25.0, ge=10.0, le=50.0, description="Minimum ADX for buying entry (trending filter)"
    )
    BUYING_MKT_STRENGTH_BULLISH: float = Field(
        default=60.0, ge=0.0, le=100.0, description="Market strength > this = bullish entry"
    )
    BUYING_MKT_STRENGTH_BEARISH: float = Field(
        default=30.0, ge=0.0, le=50.0, description="Market strength < this = bearish entry"
    )
    BUYING_SENTIMENT_WEIGHT: float = Field(
        default=0.0, ge=0.0, le=0.5, description="Sentiment confirmation weight (0.0 = stubbed, Phase 8)"
    )

    # ── Strike selection: Buying ───────────────────────────────────────────────────────
    BUYING_DELTA_MIN: float = Field(default=0.50, ge=0.30, le=0.70, description="Minimum delta for buying strike")
    BUYING_DELTA_MAX: float = Field(default=0.60, ge=0.40, le=0.80, description="Maximum delta for buying strike")
    BUYING_DELTA_WIDEN_MIN: float = Field(
        default=0.45, ge=0.30, le=0.60, description="Widened delta range min if no strike in primary range"
    )
    BUYING_DELTA_WIDEN_MAX: float = Field(
        default=0.65, ge=0.50, le=0.80, description="Widened delta range max if no strike in primary range"
    )
    BUYING_STRIKE_MIN_OI: int = Field(default=10000, ge=100, description="Minimum OI on selected strike")
    BUYING_STRIKE_MIN_VOLUME: int = Field(default=1000, ge=100, description="Minimum volume on selected strike")

    # ── Exit: Buying ───────────────────────────────────────────────────────────────────
    BUYING_TRAILING_SL_ATR_MULT: float = Field(
        default=1.5, ge=0.5, le=4.0, description="Base trailing SL = ATR(14) * this multiplier"
    )
    BUYING_TARGET_RR_MIN: float = Field(
        default=2.0, ge=1.0, le=5.0, description="Minimum reward:risk ratio for entry (Chan Ch.6)"
    )
    BUYING_DAYS_BEFORE_EXPIRY_EXIT: int = Field(
        default=3, ge=1, le=7, description="Exit N trading days before expiry (time stop)"
    )

    # ── Adaptive trailing stop factors ─────────────────────────────────────────────────
    TRAIL_VIX_SCALE_FACTOR: float = Field(
        default=0.1, ge=0.0, le=0.5, description="VIX adjustment: trail * (1 + VIX/100 * this factor)"
    )
    TRAIL_STRENGTH_SCALE_FACTOR: float = Field(
        default=0.05, ge=0.0, le=0.3, description="Market strength adjustment: stronger = wider trail"
    )
    TRAIL_VOLUME_SPIKE_THRESHOLD: float = Field(
        default=2.0, ge=1.0, le=5.0, description="Volume > this * average = spike -> tighten trail"
    )
    TRAIL_VOLUME_SPIKE_TIGHTEN: float = Field(
        default=0.10, ge=0.0, le=0.3, description="Tightening fraction on volume spike"
    )

    # ── Position sizing (Kaufman Ch.9-10) ──────────────────────────────────────────────
    POSITION_SIZING_METHOD: Literal["fixed_fractional", "kelly", "optimal_f"] = Field(
        default="fixed_fractional", description="Position sizing method"
    )
    FIXED_FRACTIONAL_PCT: float = Field(
        default=0.02, ge=0.01, le=0.05, description="Fixed fractional risk per trade (1-3%, default 2%)"
    )
    KELLY_USE_HALF: bool = Field(default=True, description="Use half-Kelly for options (fat tails, Kaufman Ch.9)")
    OPTIMAL_F_LOOKBACK_TRADES: int = Field(
        default=100, ge=20, le=500, description="Number of historical trades for optimal-f calculation"
    )

    # ── Risk limits ────────────────────────────────────────────────────────────────────
    MAX_LOTS_PER_TRADE: int = Field(default=10, ge=1, le=50, description="Maximum lots per single trade signal")
    MAX_DAILY_SIGNALS: int = Field(default=6, ge=1, le=20, description="Maximum signals per day (avoid overtrading)")
    MAX_OPEN_POSITIONS: int = Field(default=4, ge=1, le=10, description="Maximum concurrent open positions")

    # ── SEBI compliance ────────────────────────────────────────────────────────────────
    SEBI_MAX_OPS: int = Field(
        default=3, ge=1, le=10, description="Self-imposed max orders per second (safety margin under 10 OPS)"
    )

    @model_validator(mode="after")
    def validate_strategy_settings(self) -> "StrategySettings":
        if self.SELLING_MKT_STRENGTH_MIN >= self.SELLING_MKT_STRENGTH_MAX:
            raise ValueError(
                f"SELLING_MKT_STRENGTH_MIN ({self.SELLING_MKT_STRENGTH_MIN}) must be < SELLING_MKT_STRENGTH_MAX ({self.SELLING_MKT_STRENGTH_MAX})"
            )
        if self.BUYING_MKT_STRENGTH_BEARISH >= self.BUYING_MKT_STRENGTH_BULLISH:
            raise ValueError(
                f"BUYING_MKT_STRENGTH_BEARISH ({self.BUYING_MKT_STRENGTH_BEARISH}) must be < BUYING_MKT_STRENGTH_BULLISH ({self.BUYING_MKT_STRENGTH_BULLISH})"
            )
        if self.BUYING_DELTA_MIN >= self.BUYING_DELTA_MAX:
            raise ValueError(
                f"BUYING_DELTA_MIN ({self.BUYING_DELTA_MIN}) must be < BUYING_DELTA_MAX ({self.BUYING_DELTA_MAX})"
            )
        if self.BUYING_DELTA_WIDEN_MIN >= self.BUYING_DELTA_WIDEN_MAX:
            raise ValueError(
                f"BUYING_DELTA_WIDEN_MIN ({self.BUYING_DELTA_WIDEN_MIN}) must be < BUYING_DELTA_WIDEN_MAX ({self.BUYING_DELTA_WIDEN_MAX})"
            )
        if self.BUYING_DELTA_WIDEN_MIN > self.BUYING_DELTA_MIN:
            raise ValueError(
                f"BUYING_DELTA_WIDEN_MIN ({self.BUYING_DELTA_WIDEN_MIN}) must be <= BUYING_DELTA_MIN ({self.BUYING_DELTA_MIN})"
            )
        if self.BUYING_DELTA_WIDEN_MAX < self.BUYING_DELTA_MAX:
            raise ValueError(
                f"BUYING_DELTA_WIDEN_MAX ({self.BUYING_DELTA_WIDEN_MAX}) must be >= BUYING_DELTA_MAX ({self.BUYING_DELTA_MAX})"
            )
        return self


# PHASE 7 ADDITIONS ──────────────────────────────────────────────────────────────────────
# Options Strike Auto-Selection + Adaptive Trailing Stop Loss Settings
# Reference: Natenberg Ch.4-8, Zerodha Varsity Options Module, Kaufman Ch.10


class StrikeSelectionSettings(BaseSettings):
    """Strike auto-selection engine configuration — delta-targeted buying + sigma-based selling.

    References:
    - Natenberg Ch.4: Delta-targeted strike selection (delta 0.50-0.60 for ATM/1-ITM)
    - Natenberg Ch.5: IV skew awareness (PE typically has higher IV than CE at same SD)
    - Natenberg Ch.5-6: Gamma risk scaling near expiry
    - Zerodha Varsity Module 6: Moneyness classification (ITM/ATM/OTM)
    - Kaufman Ch.7: 2SD ≈ 2*ATR(14) for normal distribution
    """

    model_config = SettingsConfigDict(env_prefix="STRIKE_", env_file=".env", extra="ignore")

    # ── NIFTY lot size ─────────────────────────────────────────────────────────────────
    NIFTY_LOT_SIZE: int = Field(default=25, ge=1, description="NIFTY options lot size (25 since Nov 2021)")

    # ── Strike interval ────────────────────────────────────────────────────────────────
    NIFTY_STRIKE_INTERVAL: int = Field(
        default=50, ge=5, description="NIFTY strike interval in rupees (multiples of 50)"
    )

    # ── Selling strike selection (2SD / ATR-based) ─────────────────────────────────────
    SELLING_STRIKE_SD_MULTIPLIER: float = Field(
        default=2.0, ge=1.0, le=4.0, description="SD multiplier for selling strike selection (2SD default)"
    )
    SELLING_STRIKE_MIN_OI: int = Field(default=10000, ge=100, description="Minimum OI on selected strike")
    SELLING_STRIKE_MIN_VOLUME: int = Field(default=1000, ge=100, description="Minimum volume on selected strike")
    SELLING_STRIKE_MAX_SEARCH_OFFSETS: int = Field(
        default=4, ge=1, le=10, description="Max +/- offset intervals to search if primary strike fails validation"
    )

    # ── Buying strike selection (delta-targeted) ───────────────────────────────────────
    BUYING_DELTA_MIN: float = Field(default=0.50, ge=0.30, le=0.70, description="Minimum delta for buying strike")
    BUYING_DELTA_MAX: float = Field(default=0.60, ge=0.40, le=0.80, description="Maximum delta for buying strike")
    BUYING_DELTA_TARGET: float = Field(
        default=0.55, ge=0.35, le=0.75, description="Target delta for strike ranking (midpoint preference)"
    )
    BUYING_DELTA_WIDEN_MIN: float = Field(
        default=0.45, ge=0.30, le=0.60, description="Widened delta range min if no strike in primary range"
    )
    BUYING_DELTA_WIDEN_MAX: float = Field(
        default=0.65, ge=0.50, le=0.80, description="Widened delta range max if no strike in primary range"
    )
    BUYING_STRIKE_MIN_OI: int = Field(default=10000, ge=100, description="Minimum OI on selected strike")
    BUYING_STRIKE_MIN_VOLUME: int = Field(default=1000, ge=100, description="Minimum volume on selected strike")

    # ── IV skew adjustment (Natenberg Ch.5) ────────────────────────────────────────────
    IV_SKEW_AWARENESS: bool = Field(default=True, description="Account for IV skew in strike selection")
    IV_SKEW_PE_ADJUSTMENT_PCT: float = Field(
        default=0.05,
        ge=0.0,
        le=0.20,
        description="PE strike distance adjustment: push PE slightly further OTM to account for higher IV",
    )

    # ── Gamma risk scaling near expiry (Natenberg Ch.5-6, Zerodha Varsity Module 14) ───
    GAMMA_RISK_DAYS_THRESHOLD: int = Field(
        default=5, ge=1, le=10, description="Days to expiry below which gamma risk scaling activates"
    )
    GAMMA_RISK_LOT_REDUCTION_PCT: float = Field(
        default=0.25, ge=0.0, le=0.50, description="Reduce lot size by this percentage when within gamma risk threshold"
    )
    GAMMA_RISK_SELLING_PUSH_OTM_STRIKES: int = Field(
        default=1, ge=0, le=3, description="Push selling strikes this many intervals further OTM near expiry"
    )

    # ── Strike ranking weights (Natenberg Ch.4, Ch.8) ──────────────────────────────────
    RANK_WEIGHT_DELTA_PROXIMITY: float = Field(
        default=0.30, ge=0.0, le=1.0, description="Weight: delta proximity to target in strike ranking"
    )
    RANK_WEIGHT_LIQUIDITY: float = Field(
        default=0.25, ge=0.0, le=1.0, description="Weight: OI + volume composite in strike ranking"
    )
    RANK_WEIGHT_IV_FAVORABILITY: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Weight: IV favorability (low IV for buying, high IV for selling) in strike ranking",
    )
    RANK_WEIGHT_BID_ASK_SPREAD: float = Field(
        default=0.20, ge=0.0, le=1.0, description="Weight: bid-ask spread tightness in strike ranking"
    )

    @model_validator(mode="after")
    def validate_strike_selection_settings(self) -> "StrikeSelectionSettings":
        if self.BUYING_DELTA_MIN >= self.BUYING_DELTA_MAX:
            raise ValueError(
                f"BUYING_DELTA_MIN ({self.BUYING_DELTA_MIN}) must be < BUYING_DELTA_MAX ({self.BUYING_DELTA_MAX})"
            )
        if self.BUYING_DELTA_WIDEN_MIN >= self.BUYING_DELTA_WIDEN_MAX:
            raise ValueError(
                f"BUYING_DELTA_WIDEN_MIN ({self.BUYING_DELTA_WIDEN_MIN}) must be < BUYING_DELTA_WIDEN_MAX ({self.BUYING_DELTA_WIDEN_MAX})"
            )
        if self.BUYING_DELTA_WIDEN_MIN > self.BUYING_DELTA_MIN:
            raise ValueError(
                f"BUYING_DELTA_WIDEN_MIN ({self.BUYING_DELTA_WIDEN_MIN}) must be <= BUYING_DELTA_MIN ({self.BUYING_DELTA_MIN})"
            )
        if self.BUYING_DELTA_WIDEN_MAX < self.BUYING_DELTA_MAX:
            raise ValueError(
                f"BUYING_DELTA_WIDEN_MAX ({self.BUYING_DELTA_WIDEN_MAX}) must be >= BUYING_DELTA_MAX ({self.BUYING_DELTA_MAX})"
            )
        total_weight = (
            self.RANK_WEIGHT_DELTA_PROXIMITY
            + self.RANK_WEIGHT_LIQUIDITY
            + self.RANK_WEIGHT_IV_FAVORABILITY
            + self.RANK_WEIGHT_BID_ASK_SPREAD
        )
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"Strike ranking weights must sum to 1.0, got {total_weight:.4f}")
        return self


class PositionSizingSettings(BaseSettings):
    """Position sizing engine configuration with cost deduction, margin checking, and gamma risk scaling.

    References:
    - Kaufman Ch.9-10: Three sizing methods (fixed-fractional, Kelly, optimal-f)
    - Natenberg Ch.5-6: Gamma risk lot reduction near expiry
    - Phase 6 cost model: Zerodha transaction cost rates
    """

    model_config = SettingsConfigDict(env_prefix="POSIZE_", env_file=".env", extra="ignore")

    # ── Lot size ───────────────────────────────────────────────────────────────────────
    NIFTY_LOT_SIZE: int = Field(default=25, ge=1, description="NIFTY options lot size (25 since Nov 2021)")

    # ── Position sizing method ─────────────────────────────────────────────────────────
    POSITION_SIZING_METHOD: Literal["fixed_fractional", "kelly", "optimal_f"] = Field(
        default="fixed_fractional", description="Position sizing method (Kaufman Ch.9)"
    )
    FIXED_FRACTIONAL_PCT: float = Field(
        default=0.02, ge=0.01, le=0.05, description="Fixed fractional risk per trade (1-3%, default 2%)"
    )
    KELLY_USE_HALF: bool = Field(default=True, description="Use half-Kelly for options (fat tails, Kaufman Ch.9)")
    OPTIMAL_F_LOOKBACK_TRADES: int = Field(
        default=100, ge=20, le=500, description="Number of historical trades for optimal-f calculation"
    )

    # ── Risk limits ────────────────────────────────────────────────────────────────────
    MAX_LOTS_PER_TRADE: int = Field(default=10, ge=1, le=50, description="Maximum lots per single trade signal")
    MAX_DAILY_NOTIONAL: float = Field(
        default=500000.0, ge=100000.0, description="Maximum daily notional exposure in INR (5 lakh)"
    )
    MAX_OPEN_POSITIONS: int = Field(default=4, ge=1, le=10, description="Maximum concurrent open positions")

    # ── Margin constraint ──────────────────────────────────────────────────────────────
    MARGIN_CHECK_ENABLED: bool = Field(default=True, description="Check available margin before computing lots")
    SPAN_MARGIN_PCT: float = Field(
        default=0.05, ge=0.02, le=0.15, description="SPAN margin ~5% of notional for NIFTY strangle"
    )
    MARGIN_SAFETY_BUFFER_PCT: float = Field(
        default=0.10, ge=0.0, le=0.30, description="Keep this percentage of available margin as buffer (never use 100%)"
    )

    # ── Cost deduction ─────────────────────────────────────────────────────────────────
    COST_DEDUCTION_ENABLED: bool = Field(
        default=True, description="Deduct estimated transaction costs from risk_per_trade before computing lots"
    )
    BROKERAGE_PER_ORDER: float = Field(default=20.0, ge=0.0, description="Zerodha brokerage Rs 20 per executed order")
    STT_SELL_PCT: float = Field(default=0.000625, ge=0.0, description="STT 0.0625% on premium value sell side options")
    STAMP_DUTY_BUY_PCT: float = Field(default=0.00003, ge=0.0, description="Stamp duty 0.003% buy side options")
    EXCHANGE_TRANSACTION_PCT: float = Field(
        default=0.00035, ge=0.0, description="NFO exchange transaction 0.035% of premium value both sides"
    )
    SEBI_TURNOVER_FEE_PER_CRORE: float = Field(
        default=10.0, ge=0.0, description="SEBI turnover fee Rs 10/crore both sides"
    )
    SEBI_CTCL_PER_LAKH: float = Field(default=1.50, ge=0.0, description="SEBI CTCL charge Rs 1.50/lakh sell side")
    GST_PCT: float = Field(default=0.18, ge=0.0, description="GST 18% on (brokerage + SEBI fees + exchange charges)")
    SLIPPAGE_PCT: float = Field(default=0.0005, ge=0.0, description="Default slippage 0.05% of option price")

    # ── Gamma risk lot reduction ───────────────────────────────────────────────────────
    GAMMA_RISK_DAYS_THRESHOLD: int = Field(
        default=5, ge=1, le=10, description="Days to expiry below which gamma risk lot reduction applies"
    )
    GAMMA_RISK_LOT_REDUCTION_PCT: float = Field(
        default=0.25, ge=0.0, le=0.50, description="Reduce lots by this percentage when within gamma risk days"
    )

    # ── SEBI compliance ────────────────────────────────────────────────────────────────
    SEBI_MAX_OPS: int = Field(
        default=3, ge=1, le=10, description="Self-imposed max orders per second (safety margin under 10 OPS)"
    )


class TrailingStopSettings(BaseSettings):
    """Adaptive trailing stop engine configuration — ATR-based + Chandelier Exit + blended methods.

    References:
    - Kaufman Ch.10: Adaptive trailing stops, Chandelier Exit
    - Natenberg Ch.5: IV rank adjustment (vega risk -> wider trail)
    - Phase 4 MarketRegime: Regime-based adjustment (STRONG wider, WEAK tighter)
    """

    model_config = SettingsConfigDict(env_prefix="TRAIL_", env_file=".env", extra="ignore")

    # ── Base trailing stop ─────────────────────────────────────────────────────────────
    BASE_ATR_MULTIPLIER: float = Field(
        default=1.5, ge=0.5, le=4.0, description="Base trailing SL = ATR(14) * this multiplier"
    )

    # ── Trailing stop method selection ─────────────────────────────────────────────────
    TRAILING_METHOD: Literal["atr_only", "chandelier", "blended"] = Field(
        default="blended", description="Trailing stop method: ATR-based, Chandelier Exit, or blended"
    )
    CHANDELIER_ATR_MULTIPLIER: float = Field(
        default=3.0,
        ge=1.0,
        le=5.0,
        description="Chandelier Exit: ATR * this multiplier subtracted from highest high (Kaufman Ch.10)",
    )
    BLENDED_ATR_WEIGHT: float = Field(
        default=0.60, ge=0.0, le=1.0, description="Weight for ATR-based trail in blended method"
    )
    BLENDED_CHANDELIER_WEIGHT: float = Field(
        default=0.40, ge=0.0, le=1.0, description="Weight for Chandelier trail in blended method"
    )

    # ── Adaptive factors ───────────────────────────────────────────────────────────────
    VIX_SCALE_FACTOR: float = Field(
        default=0.10, ge=0.0, le=0.50, description="VIX adjustment: trail * (1 + VIX/100 * this factor)"
    )
    STRENGTH_SCALE_FACTOR: float = Field(
        default=0.05, ge=0.0, le=0.30, description="Market strength adjustment: stronger = wider trail"
    )
    VOLUME_SPIKE_THRESHOLD: float = Field(
        default=2.0, ge=1.0, le=5.0, description="Volume > this * average = spike -> tighten trail"
    )
    VOLUME_SPIKE_TIGHTEN: float = Field(
        default=0.10, ge=0.0, le=0.30, description="Tightening fraction on volume spike"
    )

    # ── IV rank adjustment (Natenberg Ch.5) ────────────────────────────────────────────
    IV_RANK_SCALE_FACTOR: float = Field(
        default=0.05,
        ge=0.0,
        le=0.20,
        description="IV rank adjustment: trail * (1 + iv_rank/100 * this factor). High IV = wider trail (vega risk)",
    )
    IV_RANK_HIGH_THRESHOLD: float = Field(
        default=60.0, ge=30.0, le=80.0, description="IV rank above this = high IV regime -> extra trail widening"
    )
    IV_RANK_HIGH_EXTRA_WIDEN: float = Field(
        default=0.10, ge=0.0, le=0.30, description="Extra widening fraction when IV rank exceeds high threshold"
    )

    # ── Regime adjustment ──────────────────────────────────────────────────────────────
    REGIME_SCALE_FACTOR: float = Field(
        default=0.05,
        ge=0.0,
        le=0.20,
        description="Regime adjustment: STRONG -> wider, WEAK -> tighter, NEUTRAL -> no change",
    )
    REGIME_STRONG_FACTOR: float = Field(
        default=1.0, ge=0.0, le=2.0, description="Regime factor for STRONG (allows trend to breathe)"
    )
    REGIME_NEUTRAL_FACTOR: float = Field(
        default=0.0, ge=-1.0, le=1.0, description="Regime factor for NEUTRAL (baseline)"
    )
    REGIME_WEAK_FACTOR: float = Field(
        default=-0.5, ge=-2.0, le=0.0, description="Regime factor for WEAK (tighter trail, protect capital)"
    )

    # ── Monotonicity enforcement ──────────────────────────────────────────────────────
    MONOTONICITY_ENFORCED: bool = Field(
        default=True, description="Trailing stop can only move toward profit direction — hard invariant (Kaufman Ch.10)"
    )

    # ── SL-M order placement ───────────────────────────────────────────────────────────
    SL_ORDER_TYPE: Literal["SL-M", "SL-L"] = Field(
        default="SL-M",
        description="Stop-loss order type: SL-M (market) or SL-L (limit). Default SL-M per Zerodha bracket order workaround",
    )
    SL_LIMIT_BUFFER_PCT: float = Field(
        default=0.001,
        ge=0.0,
        le=0.01,
        description="If SL-L: limit price = trigger_price * (1 - this buffer). Prevents execution failure",
    )

    # ── Minimum trail floor ────────────────────────────────────────────────────────────
    MIN_TRAIL_FLOOR_ATR_MULT: float = Field(
        default=0.5,
        ge=0.1,
        le=1.0,
        description="Minimum trail = ATR * this multiplier. Trail never goes below this floor regardless of adaptive factors",
    )

    @model_validator(mode="after")
    def validate_trailing_stop_settings(self) -> "TrailingStopSettings":
        if self.TRAILING_METHOD == "blended":
            total = self.BLENDED_ATR_WEIGHT + self.BLENDED_CHANDELIER_WEIGHT
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"BLENDED weights must sum to 1.0, got {total:.4f}")
        if self.SL_ORDER_TYPE == "SL-L" and self.SL_LIMIT_BUFFER_PCT <= 0:
            raise ValueError("SL_LIMIT_BUFFER_PCT must be > 0 when using SL-L order type")
        return self


# PHASE 8 ADDITIONS ──────────────────────────────────────────────────────────────────────
# Sentiment Analysis Pipeline Settings
# Reference: Tunstall "NLP with Transformers" Ch.1-7, Natenberg Ch.7


class SentimentSettings(BaseSettings):
    """Sentiment analysis pipeline configuration — news scrapers, FinBERT + muRIL + VADER, ensemble combiner.

    CRITICAL FinBERT label mapping (Correction #2):
    - FinBERT config.json: {0: 'positive', 1: 'negative', 2: 'neutral'} — NOT alphabetical
    - Hardcoding wrong mapping inverts sentiment scores

    References:
    - Tunstall Ch.6: Pipeline API with top_k=3 for full probability distribution
    - Tunstall Ch.3: muRIL fine-tuning recipe (lr=2e-5, 4 epochs, warmup_ratio=0.1)
    - Tunstall Ch.7: Model versioning (pin exact revision), FP16 for production
    - Hutto & Gilbert 2014: VADER compound score (pre-filter for neutral text)
    """

    model_config = SettingsConfigDict(env_prefix="SENTIMENT_", env_file=".env", extra="ignore")

    # ── Scraping configuration ─────────────────────────────────────────────────────────
    SCRAPE_INTERVAL_NEWS_MINUTES: int = Field(
        default=30, ge=10, le=120, description="News scraping interval in minutes"
    )
    SCRAPE_INTERVAL_SOCIAL_MINUTES: int = Field(
        default=60, ge=15, le=240, description="Social media scraping interval in minutes"
    )
    SCRAPE_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=120, description="HTTP timeout per scrape request")
    SCRAPE_MAX_CONCURRENT: int = Field(default=5, ge=1, le=20, description="Max concurrent scraper tasks")
    SCRAPE_USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        description="User-Agent for HTTP requests",
    )

    # ── RSS Feed URLs (configurable) ───────────────────────────────────────────────────
    RSS_ECONOMIC_TIMES: str = Field(
        default="https://economictimes.indiatimes.com/rssfeedstopstories.cms", description="Economic Times RSS URL"
    )
    RSS_GOOGLE_NEWS_FINANCE: str = Field(
        default="https://news.google.com/rss/search?q=indian+stock+market+finance&hl=en-IN&gl=IN&ceid=IN:en",
        description="Google News India Finance RSS URL",
    )

    # ── Newspaper4k article sources ────────────────────────────────────────────────────
    ARTICLE_SOURCES: list[str] = Field(
        default=["moneycontrol", "livemint"], description="Sources for newspaper4k full-article scraping"
    )

    # ── Reddit configuration ───────────────────────────────────────────────────────────
    REDDIT_CLIENT_ID: str = Field(default="", description="Reddit OAuth client_id")
    REDDIT_CLIENT_SECRET: str = Field(default="", description="Reddit OAuth client_secret")
    REDDIT_USER_AGENT: str = Field(default="indian-trading-bot/1.0", description="Reddit API user_agent")
    REDDIT_SUBREDDITS: list[str] = Field(
        default=["IndiaInvestments", "IndianStreetBets", "DalalStreet"], description="Subreddits to scrape"
    )
    REDDIT_POST_LIMIT: int = Field(default=25, ge=5, le=100, description="Max posts per subreddit per scrape")

    # ── Model configuration ────────────────────────────────────────────────────────────
    FINBERT_MODEL_NAME: str = Field(default="ProsusAI/finbert", description="FinBERT HuggingFace model identifier")
    FINBERT_REVISION: str = Field(default="main", description="Pin model revision for reproducibility (Tunstall Ch.7)")
    MURIL_MODEL_NAME: str = Field(default="google/muril-base-cased", description="muRIL base model identifier")
    MURIL_FINETUNED_PATH: str = Field(
        default="data/models/muril-fin-sentiment", description="Local path to fine-tuned muRIL model"
    )
    DEVICE: int = Field(default=-1, description="Device: -1=CPU, 0=GPU-0, etc.")
    TORCH_DTYPE: str = Field(default="float32", description="Torch dtype: float32 or float16 (Tunstall Ch.7)")
    MODEL_CACHE_DIR: str = Field(
        default="data/models/huggingface_cache", description="HuggingFace model cache directory"
    )
    TRANSFORMERS_OFFLINE: bool = Field(default=False, description="Force offline mode (pre-downloaded models only)")

    # ── VADER pre-filter ───────────────────────────────────────────────────────────────
    VADER_NEUTRAL_THRESHOLD: float = Field(
        default=0.05, description="If |compound| < this, skip transformer (clearly neutral)"
    )
    VADER_ENABLED: bool = Field(default=True, description="Enable VADER pre-filter gate")

    # ── Language detection ─────────────────────────────────────────────────────────────
    LANGUAGE_DETECTION_ENABLED: bool = Field(default=True, description="Enable language detection for model routing")
    LANGUAGE_FALLBACK: str = Field(default="en", description="Fallback language if detection fails")

    # ── Symbol extraction ──────────────────────────────────────────────────────────────
    SYMBOL_KEYWORDS: dict[str, list[str]] = Field(
        default={
            "NIFTY": ["nifty", "nifty 50", "nifty50", "^NSEI", "nse index"],
            "BANKNIFTY": ["banknifty", "bank nifty", "nifty bank", "^NSEBANK"],
            "RELIANCE": ["reliance", "reliance industries", "ril"],
            "HDFCBANK": ["hdfc bank", "hdfcbank"],
            "ICICIBANK": ["icici bank", "icicibank"],
            "INFY": ["infosys", "infy"],
            "TCS": ["tcs", "tata consultancy"],
            "KOTAKBANK": ["kotak bank", "kotakbank"],
            "AXISBANK": ["axis bank", "axisbank"],
            "SBIN": ["sbi", "state bank", "sbin"],
            "ITC": ["itc limited", "itc ltd"],
            "BHARTIARTL": ["bharti airtel", "airtel", "bhartiartl"],
            "LT": ["larsen toubro", "l&t", "l&t finance"],
            "MARUTI": ["maruti suzuki", "maruti"],
        },
        description="Symbol -> keyword mapping for article symbol extraction",
    )
    SYMBOL_HEADLINE_WEIGHT: float = Field(
        default=2.0, ge=1.0, le=5.0, description="Weight multiplier for symbol mention in headline vs body"
    )

    # ── Ensemble weights ───────────────────────────────────────────────────────────────
    NEWS_WEIGHT: float = Field(default=0.70, ge=0.0, le=1.0, description="Weight for news sentiment in final ensemble")
    SOCIAL_WEIGHT: float = Field(
        default=0.30, ge=0.0, le=1.0, description="Weight for social sentiment in final ensemble"
    )

    # ── Source credibility ─────────────────────────────────────────────────────────────
    SOURCE_CREDIBILITY: dict[str, float] = Field(
        default={
            "economic_times": 0.85,
            "moneycontrol": 0.80,
            "livemint": 0.75,
            "google_news": 0.60,
            "reddit": 0.35,
        },
        description="Source credibility weights (Reuters/Bloomberg = 1.0 benchmark)",
    )

    # ── Recency weighting ──────────────────────────────────────────────────────────────
    HALF_LIFE_HOURS: float = Field(
        default=4.0, ge=0.5, le=168.0, description="Exponential decay half-life in hours (4h for intraday)"
    )
    RECENCY_ENABLED: bool = Field(default=True, description="Apply recency weighting to articles")

    # ── Confidence scoring ─────────────────────────────────────────────────────────────
    CROSS_MODEL_AGREEMENT_BONUS: float = Field(
        default=0.10, ge=0.0, le=0.3, description="Confidence bonus when FinBERT + muRIL agree"
    )
    CROSS_MODEL_DISAGREEMENT_PENALTY: float = Field(
        default=0.10, ge=0.0, le=0.3, description="Confidence penalty when models disagree"
    )
    MIN_CONFIDENCE_THRESHOLD: float = Field(
        default=0.30, ge=0.0, le=0.5, description="Below this confidence, sentiment score is dampened"
    )

    # ── Inference performance ──────────────────────────────────────────────────────────
    MAX_INFERENCE_QUEUE_SIZE: int = Field(
        default=100, ge=10, le=1000, description="Max queued inference requests before circuit break (Tunstall Ch.6)"
    )
    INFERENCE_TIMEOUT_SECONDS: float = Field(default=5.0, ge=1.0, le=30.0, description="Timeout per inference call")

    # ── Target symbols ─────────────────────────────────────────────────────────────────
    TARGET_SYMBOLS: list[str] = Field(
        default=[
            "NIFTY",
            "BANKNIFTY",
            "RELIANCE",
            "HDFCBANK",
            "ICICIBANK",
            "INFY",
            "TCS",
            "KOTAKBANK",
            "AXISBANK",
            "SBIN",
            "ITC",
            "BHARTIARTL",
        ],
        description="Symbols for daily sentiment computation",
    )

    @model_validator(mode="after")
    def validate_sentiment_settings(self) -> "SentimentSettings":
        if abs(self.NEWS_WEIGHT + self.SOCIAL_WEIGHT - 1.0) > 0.01:
            raise ValueError(f"NEWS_WEIGHT ({self.NEWS_WEIGHT}) + SOCIAL_WEIGHT ({self.SOCIAL_WEIGHT}) must sum to 1.0")
        for source, cred in self.SOURCE_CREDIBILITY.items():
            if not 0.0 <= cred <= 1.0:
                raise ValueError(f"SOURCE_CREDIBILITY[{source}] = {cred} must be in [0.0, 1.0]")
        if self.HALF_LIFE_HOURS <= 0:
            raise ValueError(f"HALF_LIFE_HOURS ({self.HALF_LIFE_HOURS}) must be > 0")
        return self


# PHASE 11 ADDITIONS ─────────────────────────────────────────────────────────────────────
# Signal Orchestration Settings
# Reference: Lopez de Prado Ch.8-9, Kleppmann Ch.7, Kaufman Ch.12


class OrchestrationSettings(BaseSettings):
    """Signal orchestration configuration — combines all signals into unified TradeDecision.

    Signal weights start EQUAL (0.20 each) per Lopez de Prado Ch.9 (avoid overfitting
    before Phase 6 walk-forward validation). Target weights applied after validation.

    References:
    - Lopez de Prado Ch.8-9: Ensemble methods, drop-one importance analysis
    - Kleppmann Ch.7: Circuit breaker pattern, timeouts, fallbacks
    - Kaufman Ch.12: System robustness, strategy combination
    """

    model_config = SettingsConfigDict(env_prefix="ORCH_", env_file=".env", extra="ignore")

    # ── Signal evaluation interval ─────────────────────────────────────────────────────
    SIGNAL_EVAL_INTERVAL_SECONDS: int = Field(
        default=300, ge=60, le=3600, description="Seconds between signal evaluations (default 5 min)"
    )

    # ── Signal weights (initially equal per Lopez de Prado Ch.9) ───────────────────────
    WEIGHT_TECHNICAL: float = Field(default=0.20, ge=0.0, le=1.0)
    WEIGHT_VOLUME: float = Field(default=0.20, ge=0.0, le=1.0)
    WEIGHT_SENTIMENT: float = Field(default=0.20, ge=0.0, le=1.0)
    WEIGHT_MARKET_STRENGTH: float = Field(default=0.20, ge=0.0, le=1.0)
    WEIGHT_RAG: float = Field(default=0.20, ge=0.0, le=1.0)

    # ── Target weights (after Phase 6 walk-forward validation) ─────────────────────────
    TARGET_WEIGHT_TECHNICAL: float = Field(default=0.35, ge=0.0, le=1.0)
    TARGET_WEIGHT_VOLUME: float = Field(default=0.20, ge=0.0, le=1.0)
    TARGET_WEIGHT_SENTIMENT: float = Field(default=0.20, ge=0.0, le=1.0)
    TARGET_WEIGHT_MARKET_STRENGTH: float = Field(default=0.15, ge=0.0, le=1.0)
    TARGET_WEIGHT_RAG: float = Field(default=0.10, ge=0.0, le=1.0)

    # ── Confidence threshold (uses abs(score) for bearish signals) ─────────────────────
    CONFIDENCE_THRESHOLD: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Minimum |combined_score| to trade. Uses abs() so bearish signals (negative score) can pass threshold.",
    )

    # ── Opposition gate ────────────────────────────────────────────────────────────────
    OPPOSITION_GATE_THRESHOLD: float = Field(
        default=0.40, ge=0.0, le=1.0, description="If any source opposes with |weight*score| > this, block trade"
    )

    # ── Data quality gate ──────────────────────────────────────────────────────────────
    MIN_SOURCES_REQUIRED: int = Field(default=3, ge=1, le=5, description="Minimum signal sources available to trade")

    # ── Circuit breaker (Kleppmann Ch.7) ───────────────────────────────────────────────
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=3, ge=1, le=10, description="Consecutive failures before opening circuit breaker"
    )
    CIRCUIT_BREAKER_OPEN_DURATION_SECONDS: float = Field(
        default=300.0, ge=30.0, le=3600.0, description="Duration circuit breaker stays open (default 5 min)"
    )
    CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS: int = Field(
        default=1, ge=1, le=5, description="Calls allowed in half-open state to test recovery"
    )

    # ── Trailing stop ──────────────────────────────────────────────────────────────────
    TRAILING_STOP_MIN_MOVE_PCT: float = Field(
        default=0.003, ge=0.001, le=0.01, description="Min price move (0.3% of entry) before ratchet advances"
    )

    # ── RAG qualitative-to-numeric mapping ─────────────────────────────────────────────
    RAG_BULLISH_SCORE: float = Field(default=0.60, ge=0.0, le=1.0)
    RAG_NEUTRAL_SCORE: float = Field(default=0.0, ge=-1.0, le=1.0)
    RAG_BEARISH_SCORE: float = Field(default=-0.60, ge=-1.0, le=0.0)

    # ── Per-symbol orchestrator ────────────────────────────────────────────────────────
    ENABLED_SYMBOLS: list[str] = Field(
        default=["NIFTY", "BANKNIFTY"], description="Symbols with independent orchestrator instances"
    )

    # ── Session lifecycle ──────────────────────────────────────────────────────────────
    PRE_OPEN_WARMUP_SECONDS: int = Field(
        default=60, ge=30, le=300, description="Seconds before market open to start warmup fetches"
    )
    POST_CLOSE_CLEANUP_SECONDS: int = Field(
        default=60, ge=30, le=300, description="Seconds after market close for P&L logging and cleanup"
    )

    # ── Audit ──────────────────────────────────────────────────────────────────────────
    LOG_ALL_SIGNALS: bool = Field(default=True, description="Log all signal payloads even if no trade decision made")

    @model_validator(mode="after")
    def validate_orchestration_settings(self) -> "OrchestrationSettings":
        """Signal weights MUST sum to 1.0; opposition gate must be < confidence threshold."""
        weight_sum = (
            self.WEIGHT_TECHNICAL
            + self.WEIGHT_VOLUME
            + self.WEIGHT_SENTIMENT
            + self.WEIGHT_MARKET_STRENGTH
            + self.WEIGHT_RAG
        )
        if abs(weight_sum - 1.0) > 0.001:
            raise ValueError(f"Signal weights must sum to 1.0, got {weight_sum:.4f}")
        target_sum = (
            self.TARGET_WEIGHT_TECHNICAL
            + self.TARGET_WEIGHT_VOLUME
            + self.TARGET_WEIGHT_SENTIMENT
            + self.TARGET_WEIGHT_MARKET_STRENGTH
            + self.TARGET_WEIGHT_RAG
        )
        if abs(target_sum - 1.0) > 0.001:
            raise ValueError(f"Target weights must sum to 1.0, got {target_sum:.4f}")
        if self.OPPOSITION_GATE_THRESHOLD >= self.CONFIDENCE_THRESHOLD:
            raise ValueError(
                f"OPPOSITION_GATE_THRESHOLD ({self.OPPOSITION_GATE_THRESHOLD}) must be < "
                f"CONFIDENCE_THRESHOLD ({self.CONFIDENCE_THRESHOLD})"
            )
        return self
