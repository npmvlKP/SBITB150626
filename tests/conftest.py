"""Shared pytest fixtures for all tests."""

from decimal import Decimal

import pytest

from config.settings import AuditSettings, ComplianceSettings, KillSwitchSettings, RiskSettings
from src.risk.audit import AuditLogger
from src.risk.kill_switch import KillSwitch
from src.risk.manager import RiskManager


@pytest.fixture
def compliance_settings() -> ComplianceSettings:
    """Compliance settings with test-safe values."""
    return ComplianceSettings(
        MAX_ORDERS_PER_SECOND=3,
        MAX_ORDERS_PER_MINUTE=60,
        MAX_ORDERS_PER_DAY=500,
        SEBI_OPS_REGISTRATION_THRESHOLD=10,
    )


@pytest.fixture
def risk_settings() -> RiskSettings:
    """Risk settings with test-safe values."""
    return RiskSettings(
        MAX_ORDER_VALUE_PER_TRADE=Decimal("200000"),
        MAX_POSITION_NOTIONAL_PER_SYMBOL=Decimal("500000"),
        MAX_TOTAL_EXPOSURE=Decimal("2000000"),
        MARGIN_UTILIZATION_THRESHOLD=Decimal("0.80"),
        MARGIN_UTILIZATION_KILL=Decimal("0.95"),
        DAILY_LOSS_LIMIT=Decimal("50000"),
        ORDER_REJECTION_THRESHOLD=10,
        CIRCUIT_LIMIT_PCT=Decimal("0.05"),
    )


@pytest.fixture
def kill_switch_settings() -> KillSwitchSettings:
    """Kill switch settings with test-safe values."""
    return KillSwitchSettings(
        THROTTLE_RATE_PCT=Decimal("0.10"),
        REQUIRE_MANUAL_RE_ENABLE=True,
        ACTIVATION_PATHS=["keyboard", "telegram", "rest_api"],
    )


@pytest.fixture
def audit_settings() -> AuditSettings:
    """Audit settings with test-safe values."""
    return AuditSettings(
        RETENTION_YEARS=7,
        CHECKSUM_ALGORITHM="sha256",
        NTP_SERVER="in.pool.ntp.org",
        MAX_NTP_OFFSET_MS=500,
    )


@pytest.fixture
def audit_logger(audit_settings: AuditSettings) -> AuditLogger:
    """Audit logger with test settings."""
    return AuditLogger(audit_settings)


@pytest.fixture
def kill_switch(
    kill_switch_settings: KillSwitchSettings,
    audit_logger: AuditLogger,
) -> KillSwitch:
    """Kill switch instance."""
    return KillSwitch(kill_switch_settings, audit_logger)


@pytest.fixture
def risk_manager(
    compliance_settings: ComplianceSettings,
    risk_settings: RiskSettings,
    kill_switch: KillSwitch,
) -> RiskManager:
    """Risk manager instance."""
    return RiskManager(compliance_settings, risk_settings, kill_switch)


@pytest.fixture
def sample_order() -> dict:
    """Valid NIFTY option order for testing."""
    return {
        "order_id": "test_order_001",
        "symbol": "NIFTY",
        "segment": "NSE",
        "exchange": "NSE",
        "quantity": 50,
        "price": Decimal("25000"),
        "ltp": Decimal("25000"),
        "order_type": "LIMIT",
    }
