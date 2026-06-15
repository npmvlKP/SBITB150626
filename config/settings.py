"""Application settings with Pydantic BaseSettings — SEBI compliance constants and risk limits."""

from datetime import time
from decimal import Decimal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class ComplianceSettings(BaseSettings):
    """SEBI compliance enforcement constants — verified against NSE/INVG/67858, SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013."""

    model_config = {"env_file": ".env", "extra": "ignore"}

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

    @field_validator("MAX_ORDERS_PER_SECOND")
    @classmethod
    def validate_max_orders_per_second(cls, v: int) -> int:
        if v > 10:
            raise ValueError("MAX_ORDERS_PER_SECOND cannot exceed 10 per SEBI NSE/INVG/67858")
        return v


class RiskSettings(BaseSettings):
    """Client-side risk limits — self-imposed per CIR/MRD/DP/09/2012."""

    model_config = {"env_file": ".env", "extra": "ignore"}

    MAX_ORDER_VALUE_PER_TRADE: Decimal = Field(default=Decimal("200000"))
    MAX_POSITION_NOTIONAL_PER_SYMBOL: Decimal = Field(default=Decimal("500000"))
    MAX_TOTAL_EXPOSURE: Decimal = Field(default=Decimal("2000000"))
    MARGIN_UTILIZATION_THRESHOLD: Decimal = Field(default=Decimal("0.80"))
    MARGIN_UTILIZATION_KILL: Decimal = Field(default=Decimal("0.95"))
    DAILY_LOSS_LIMIT: Decimal = Field(default=Decimal("50000"))
    ORDER_REJECTION_THRESHOLD: int = Field(default=10, ge=1)
    CIRCUIT_LIMIT_PCT: Decimal = Field(default=Decimal("0.05"))


class KillSwitchSettings(BaseSettings):
    """Kill switch configuration — per MiFID II Art. 17, NIST RS.RP-1, ISO A.8.26."""

    model_config = {"env_file": ".env", "extra": "ignore"}

    THROTTLE_RATE_PCT: Decimal = Field(default=Decimal("0.10"))
    REQUIRE_MANUAL_RE_ENABLE: bool = True
    ACTIVATION_PATHS: list[str] = ["keyboard", "telegram", "rest_api"]


class AuditSettings(BaseSettings):
    """Audit trail configuration — 7-year retention per SEBI requirement (5+)."""

    model_config = {"env_file": ".env", "extra": "ignore"}

    RETENTION_YEARS: int = Field(default=7, ge=5)
    CHECKSUM_ALGORITHM: str = "sha256"
    NTP_SERVER: str = "in.pool.ntp.org"
    MAX_NTP_OFFSET_MS: int = Field(default=500, ge=100)


class BrokerSettings(BaseSettings):
    """Per-broker configurations — Zerodha primary, Angel One fallback."""

    model_config = {"env_file": ".env", "extra": "ignore"}

    ZERODHA_API_KEY: str = ""
    ZERODHA_API_SECRET: str = ""
    ZERODHA_ACCESS_TOKEN: str = ""
    ZERODHA_TOTP_SECRET: str = ""
    ZERODHA_API_RATE_QUOTES: int = 1
    ZERODHA_API_RATE_HISTORICAL: int = 3
    ZERODHA_API_RATE_ORDERS: int = 10
    ZERODHA_WS_MAX_CONNECTIONS: int = 3
    ZERODHA_WS_MAX_INSTRUMENTS: int = 9000
    ZERODHA_SESSION_EXPIRY_IST: time = time(6, 0)
    ZERODHA_MARKET_PROTECTION: Decimal = Decimal("-1")
    ZERODHA_MONTHLY_FEE: int = 500
    ZERODHA_TAG_MAX_LENGTH: int = 20
    ZERODHA_NO_SANDBOX: bool = True
    ANGEL_ONE_API_KEY: str = ""
    ANGEL_ONE_API_SECRET: str = ""
    ANGEL_ONE_CLIENT_CODE: str = ""
    ANGEL_ONE_PASSWORD: str = ""
    ANGEL_ONE_TOTP_SECRET: str = ""
    DHAN_CLIENT_ID: str = ""
    DHAN_ACCESS_TOKEN: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
