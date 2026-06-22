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
