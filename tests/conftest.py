"""Shared pytest fixtures for all tests."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import numpy as np
import pytest

from config.settings import (
    AuditSettings,
    ComplianceSettings,
    DataPipelineSettings,
    DepthAnalysisSettings,
    GreeksSettings,
    KillSwitchSettings,
    RiskSettings,
    TechnicalIndicatorSettings,
    VolumeProfileSettings,
    WebSocketSettings,
)
from src.analysis import AnalysisEngine
from src.analysis.depth import DepthData, DepthLevel
from src.data.option_chain import OptionMetrics, OptionMetricsComputer, RiskFreeRateProvider
from src.risk.audit import AuditLogger
from src.risk.kill_switch import KillSwitch
from src.risk.manager import RiskManager

# Enable asyncio for module-level fixtures
pytest_plugins = ("pytest_asyncio",)


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
def sample_order() -> dict[str, Any]:
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


# =============================================================================
# Phase 2: Data Pipeline Fixtures
# =============================================================================


@pytest.fixture
def pipeline_settings() -> DataPipelineSettings:
    """Data pipeline settings with test-safe values."""
    return DataPipelineSettings(
        bhavcopy_base_url="https://example.com/bhavcopy",
        batch_size=100,
        max_retries=3,
        retry_delay=1.0,
    )


@pytest.fixture
def greeks_settings() -> GreeksSettings:
    """Greeks computation settings with test-safe values."""
    return GreeksSettings(
        RFR_METHOD="t_bill",
        RFR_T_BILL_DEFAULT=0.065,
        MIN_TTM_DAYS=1,
        MIN_OPTION_PRICE=0.05,
        IV_UPPER_BOUND=5.0,
        IV_LOWER_BOUND=0.001,
    )


@pytest.fixture
def ws_settings() -> WebSocketSettings:
    """WebSocket settings with test-safe values."""
    return WebSocketSettings(
        RECONNECT_MAX_DELAY_SEC=60.0,
        RECONNECT_MAX_ATTEMPTS=3,
        RING_BUFFER_SIZE=10000,
        REDIS_TTL_SEC=86400,
    )


@pytest.fixture
def sample_fo_row() -> dict[str, Any]:
    """Sample F&O CSV row for testing."""
    return {
        "instrument_token": "12345",
        "symbol": "NIFTY",
        "expiry": "2026-06-26",
        "strike": "25000",
        "option_type": "CE",
        "open": "24800.00",
        "high": "24950.00",
        "low": "24700.00",
        "close": "24900.00",
        "volume": "150000",
        "value": "3735000000.00",
        "open_interest": "2500000",
    }


@pytest.fixture
def sample_tick() -> dict[str, Any]:
    """Sample tick data for testing."""
    return {
        "instrument_token": "12345",
        "last_price": 24900.0,
        "last_quantity": 50,
        "average_price": 24850.0,
        "volume": 150000,
        "buy_quantity": 120000,
        "sell_quantity": 130000,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# Phase 2: Mocks for external services (Redis, TimescaleDB)
# =============================================================================


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        self._data[key] = value
        return True

    async def get(self, key: str) -> Any | None:
        return self._data.get(key)

    async def delete(self, *keys: str) -> int:
        count = sum(1 for k in keys if k in self._data)
        for k in keys:
            self._data.pop(k, None)
        return count

    async def pipeline(self):
        return MockPipeline(self)

    async def ping(self) -> bool:
        return True


class MockPipeline:
    """Mock Redis pipeline."""

    def __init__(self, redis: MockRedisClient) -> None:
        self._redis = redis
        self._commands: list[tuple[str, ...]] = []

    def set(self, key: str, value: Any) -> "MockPipeline":
        self._commands.append(("set", key, value))
        return self

    def expire(self, key: str, seconds: int) -> "MockPipeline":
        self._commands.append(("expire", key, seconds))
        return self

    async def execute(self) -> list[Any]:
        for cmd in self._commands:
            if cmd[0] == "set":
                self._redis._data[cmd[1]] = cmd[2]
        return [True] * len(self._commands)


class MockConnectionPool:
    """Mock psycopg connection pool for testing."""

    def __init__(self) -> None:
        self._closed = False

    async def connection(self) -> AsyncMock:
        return AsyncMock()

    async def close(self) -> None:
        self._closed = True


@pytest.fixture
def mock_redis() -> MockRedisClient:
    """Mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def mock_pool() -> MockConnectionPool:
    """Mock connection pool."""
    return MockConnectionPool()


@pytest.fixture
def rfr_provider(greeks_settings: GreeksSettings) -> RiskFreeRateProvider:
    """Risk-free rate provider for Greeks computation."""
    return RiskFreeRateProvider(settings=greeks_settings, db_url="postgresql://test:test@localhost:5432/test")


@pytest.fixture
def greeks_computer(
    greeks_settings: GreeksSettings,
    rfr_provider: RiskFreeRateProvider,
) -> OptionMetricsComputer:
    """Option Greeks computer instance."""
    return OptionMetricsComputer(settings=greeks_settings, rfr_provider=rfr_provider)


@pytest.fixture
def sample_option_metrics() -> OptionMetrics:
    """Sample option metrics for testing."""
    return OptionMetrics(
        iv=0.185,
        delta=0.52,
        gamma=0.032,
        theta=-45.20,
        vega=0.182,
        risk_free_rate=0.065,
        rfr_method="t_bill",
        ttm_years=0.05,
        compute_error=None,
    )


@pytest.fixture
def event_writer() -> AsyncMock:
    """Mock event writer for testing."""
    writer = AsyncMock()
    writer.write = AsyncMock(return_value=True)
    writer.flush = AsyncMock(return_value=True)
    writer.close = AsyncMock(return_value=True)
    return writer


# =============================================================================
# Phase 3: TA/VA Engine Fixtures
# =============================================================================


@pytest.fixture
def ta_settings() -> TechnicalIndicatorSettings:
    """Default TechnicalIndicatorSettings for testing."""
    return TechnicalIndicatorSettings()


@pytest.fixture
def vol_settings() -> VolumeProfileSettings:
    """Default VolumeProfileSettings for testing."""
    return VolumeProfileSettings()


@pytest.fixture
def depth_settings() -> DepthAnalysisSettings:
    """Default DepthAnalysisSettings for testing."""
    return DepthAnalysisSettings()


@pytest.fixture
def analysis_engine(
    ta_settings: TechnicalIndicatorSettings,
    vol_settings: VolumeProfileSettings,
    depth_settings: DepthAnalysisSettings,
) -> AnalysisEngine:
    """AnalysisEngine instance wired with Phase 3 settings."""
    return AnalysisEngine(ta_settings, vol_settings, depth_settings)


@pytest.fixture
def sample_ohlcv_500() -> np.ndarray:
    """Generate 500 bars of realistic OHLCV data for testing."""
    np.random.seed(42)
    n = 500
    close = 22000 + np.cumsum(np.random.randn(n) * 50)
    close = np.maximum(close, 100)  # Ensure positive prices
    high = close + np.abs(np.random.randn(n) * 30)
    low = close - np.abs(np.random.randn(n) * 30)
    open_ = close + np.random.randn(n) * 10
    open_ = np.maximum(open_, low)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    volume = np.random.randint(100000, 10000000, n).astype(np.float64)
    return np.column_stack([open_, high, low, close, volume]).astype(np.float64)


@pytest.fixture
def sample_ohlcv_100() -> np.ndarray:
    """Generate 100 bars of OHLCV data."""
    np.random.seed(123)
    n = 100
    close = 45000 + np.cumsum(np.random.randn(n) * 100)
    close = np.maximum(close, 100)
    high = close + np.abs(np.random.randn(n) * 50)
    low = close - np.abs(np.random.randn(n) * 50)
    open_ = close + np.random.randn(n) * 20
    open_ = np.maximum(open_, low)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    volume = np.random.randint(500000, 50000000, n).astype(np.float64)
    return np.column_stack([open_, high, low, close, volume]).astype(np.float64)


@pytest.fixture
def sample_depth() -> DepthData:
    """Sample DepthData for testing."""
    return DepthData(
        bid_levels=[DepthLevel(price=22000.0, quantity=1000) for _ in range(5)],
        ask_levels=[DepthLevel(price=22001.0, quantity=800) for _ in range(5)],
    )


@pytest.fixture
def sample_1min_bars() -> np.ndarray:
    """Generate 375 1-min bars (1 trading day) for VPIN testing."""
    np.random.seed(99)
    n = 375
    close = 22000 + np.cumsum(np.random.randn(n) * 5)
    close = np.maximum(close, 100)
    high = close + np.abs(np.random.randn(n) * 3)
    low = close - np.abs(np.random.randn(n) * 3)
    open_ = close + np.random.randn(n) * 2
    open_ = np.maximum(open_, low)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    volume = np.random.randint(10000, 500000, n).astype(np.float64)
    return np.column_stack([open_, high, low, close, volume]).astype(np.float64)
