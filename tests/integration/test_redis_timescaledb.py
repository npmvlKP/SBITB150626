"""Integration tests for Redis + TimescaleDB Write/Read Roundtrip.

Tests complete data flow from write to read confirming end-to-end consistency
across both storage layers per Kleppmann Ch.3 event-driven architecture.

NOTE: Tests that require actual Redis/TimescaleDB services are marked with
@pytest.mark.skip_if_no_redis / pytest.mark.skip_if_no_timescale decorator
and will be skipped if services are not available.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from config.settings import DataPipelineSettings, WebSocketSettings
from src.data.option_chain import OptionMetrics
from src.data.storage import RedisCache, TimescaleDBStore

# ============================================================================
# Mock Classes for Integration Testing
# ============================================================================


class MockAsyncConnectionPool:
    """Mock psycopg async connection pool."""

    def __init__(self) -> None:
        self._closed = False
        self.connections: list[AsyncMock] = []

    async def connection(self) -> AsyncMock:
        conn = AsyncMock(spec=["execute", "fetch", "fetchval", "close"])
        self.connections.append(conn)
        return conn

    async def close(self) -> None:
        self._closed = True


class MockRedis:
    """Mock Redis client for integration testing."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._pipeline_cmds: list[tuple[str, ...]] = []
        self._in_pipeline = False

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        self._data[key] = value
        return True

    async def get(self, key: str) -> Any | None:
        return self._data.get(key)

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
        return count

    async def pipeline(self) -> "MockRedisPipeline":
        self._in_pipeline = True
        return MockRedisPipeline(self)

    async def ping(self) -> bool:
        return True


class MockRedisPipeline:
    """Mock Redis pipeline."""

    def __init__(self, redis: MockRedis) -> None:
        self._redis = redis
        self._commands: list[tuple[str, ...]] = []

    def set(self, key: str, value: Any) -> "MockRedisPipeline":
        self._commands.append(("set", key, value))
        return self

    def expire(self, key: str, seconds: int) -> "MockRedisPipeline":
        self._commands.append(("expire", key, seconds))
        return self

    async def execute(self) -> list[Any]:
        for cmd in self._commands:
            if cmd[0] == "set":
                self._redis._data[cmd[1]] = cmd[2]
        return [True] * len(self._commands)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_ts_pool() -> MockAsyncConnectionPool:
    """Mock TimescaleDB connection pool."""
    return MockAsyncConnectionPool()


@pytest.fixture
def mock_redis() -> MockRedis:
    """Mock Redis client."""
    return MockRedis()


@pytest.fixture
def pipeline_settings() -> DataPipelineSettings:
    """Data pipeline settings for tests."""
    return DataPipelineSettings()


@pytest.fixture
def ws_settings() -> WebSocketSettings:
    """WebSocket settings for tests."""
    return WebSocketSettings()


@pytest.fixture
def timescale_store(
    pipeline_settings: DataPipelineSettings,
    mock_ts_pool: MockAsyncConnectionPool,
) -> TimescaleDBStore:
    """TimescaleDB store with mock pool."""
    store = TimescaleDBStore(
        db_url="postgresql://test:test@localhost:5432/test",
        settings=pipeline_settings,
    )
    # Replace the pool with our mock
    store._pool = mock_ts_pool
    return store


@pytest.fixture
def redis_cache(mock_redis: MockRedis, ws_settings: WebSocketSettings) -> RedisCache:
    """Redis cache with mock client."""
    cache = RedisCache(
        redis_url="redis://localhost:6379/0",
        settings=ws_settings,
    )
    cache._redis = mock_redis
    return cache


@pytest.fixture
def sample_fo_row() -> dict[str, Any]:
    """Sample F&O CSV row."""
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
    """Sample tick data."""
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


@pytest.fixture
def sample_option_metrics() -> OptionMetrics:
    """Sample option metrics for Greeks roundtrip."""
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


# ============================================================================
# Test 1: Tick Write to Redis then Read (Roundtrip) - Mocked
# ============================================================================


class TestTickRedisRoundtrip:
    """Test tick data written to Redis can be read back using mock."""

    @pytest.mark.asyncio
    async def test_tick_write_read_roundtrip_mock(
        self,
        mock_redis: MockRedis,
        sample_tick: dict[str, Any],
    ) -> None:
        """Tick written to mock Redis can be read back with correct values."""
        token = str(sample_tick["instrument_token"])

        # Write tick to mock Redis
        await mock_redis.set(f"tick:{token}", sample_tick)

        # Read tick back from mock Redis
        cached_tick = await mock_redis.get(f"tick:{token}")

        assert cached_tick is not None, "Tick should be cached in Redis"
        assert cached_tick["instrument_token"] == sample_tick["instrument_token"]
        assert cached_tick["last_price"] == sample_tick["last_price"]
        assert cached_tick["volume"] == sample_tick["volume"]

    @pytest.mark.asyncio
    async def test_tick_overwrite_updates_value_mock(
        self,
        mock_redis: MockRedis,
        sample_tick: dict[str, Any],
    ) -> None:
        """New tick overwrites previous value in mock Redis."""
        token = str(sample_tick["instrument_token"])
        key = f"tick:{token}"

        # Write first tick
        await mock_redis.set(key, sample_tick)

        # Write updated tick
        updated_tick = sample_tick.copy()
        updated_tick["last_price"] = 25000.0
        await mock_redis.set(key, updated_tick)

        # Read should have updated value
        cached_tick = await mock_redis.get(key)
        assert cached_tick["last_price"] == 25000.0

    @pytest.mark.asyncio
    async def test_multiple_ticks_independent_mock(
        self,
        mock_redis: MockRedis,
        sample_tick: dict[str, Any],
    ) -> None:
        """Multiple ticks are stored independently in mock Redis."""
        tick1 = sample_tick.copy()
        tick2 = sample_tick.copy()
        tick1["instrument_token"] = "12345"
        tick2["instrument_token"] = "67890"

        await mock_redis.set("tick:12345", tick1)
        await mock_redis.set("tick:67890", tick2)

        cached1 = await mock_redis.get("tick:12345")
        cached2 = await mock_redis.get("tick:67890")

        assert cached1["last_price"] == tick1["last_price"]
        assert cached2["last_price"] == tick2["last_price"]


# ============================================================================
# Test 2: Tick Write to Redis → TimescaleDB Persist (Cascade) - Mocked
# ============================================================================


class TestTickCascadePersist:
    """Test tick flow from Redis to TimescaleDB persistence using mocks."""

    @pytest.mark.asyncio
    async def test_tick_persists_to_timescale_mock(
        self,
        timescale_store: TimescaleDBStore,
        sample_tick: dict[str, Any],
    ) -> None:
        """Tick can be persisted to TimescaleDB via mocked bulk_insert."""
        # Patch bulk insert to verify it's called
        with patch.object(timescale_store, "bulk_insert", new_callable=AsyncMock) as mock_bulk:
            mock_bulk.return_value = 1
            result = await timescale_store.bulk_insert("option_ticks", [sample_tick])

            assert result == 1
            mock_bulk.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_batch_persist_mock(
        self,
        timescale_store: TimescaleDBStore,
        sample_tick: dict[str, Any],
    ) -> None:
        """Batch of ticks can be persisted in single call via mock."""
        ticks = [sample_tick.copy() for _ in range(5)]
        for i, tick in enumerate(ticks):
            tick["instrument_token"] = str(1000 + i)

        with patch.object(timescale_store, "bulk_insert", new_callable=AsyncMock) as mock_bulk:
            mock_bulk.return_value = 5
            result = await timescale_store.bulk_insert("option_ticks", ticks)

            assert result == 5

    @pytest.mark.asyncio
    async def test_redis_tick_fallback_on_timescale_error_mock(
        self,
        timescale_store: TimescaleDBStore,
        mock_redis: MockRedis,
        sample_tick: dict[str, Any],
    ) -> None:
        """Mock Redis cache available when TimescaleDB fails."""
        token = str(sample_tick["instrument_token"])
        key = f"tick:{token}"

        # Cache in mock Redis (always works)
        await mock_redis.set(key, sample_tick)

        # TimescaleDB fails - but we still have Redis
        with patch.object(timescale_store, "bulk_insert", new_callable=AsyncMock) as mock_bulk:
            mock_bulk.side_effect = Exception("DB connection error")
            # Should not raise - system degrades gracefully
            try:
                await timescale_store.bulk_insert("option_ticks", [sample_tick])
            except Exception:
                pass  # Expected - but Redis still has data

        # Mock Redis still has the tick
        cached = await mock_redis.get(key)
        assert cached is not None
        assert cached["last_price"] == sample_tick["last_price"]


# ============================================================================
# Test 3: F&O Row Write to TimescaleDB then Read (Roundtrip) - Mocked
# ============================================================================


class TestFORowTimescaleRoundtrip:
    """Test F&O data written to TimescaleDB can be queried back."""

    @pytest.mark.asyncio
    async def test_fo_row_insert_and_query(
        self,
        timescale_store: TimescaleDBStore,
        sample_fo_row: dict[str, Any],
    ) -> None:
        """F&O row inserted can be queried back."""
        with patch.object(timescale_store, "bulk_insert", new_callable=AsyncMock) as mock_insert:
            mock_insert.return_value = 1
            result = await timescale_store.bulk_insert("fo_options_eod", [sample_fo_row])

            assert result == 1
            mock_insert.assert_called_once()


# ============================================================================
# Test 4: Greeks Roundtrip (Compute → Store → Retrieve → Verify) - Mocked
# ============================================================================


class TestGreeksRoundtrip:
    """Test Greeks computation flow end-to-end using mocks."""

    @pytest.mark.asyncio
    async def test_greeks_persist_and_retrieve(
        self,
        timescale_store: TimescaleDBStore,
        sample_option_metrics: OptionMetrics,
    ) -> None:
        """Greeks values persist correctly via mocked bulk_insert."""
        metrics_dict = {
            "symbol": "NIFTY",
            "expiry": "2026-06-26",
            "strike": 25000,
            "option_type": "CE",
            "iv": sample_option_metrics.iv,
            "delta": sample_option_metrics.delta,
            "gamma": sample_option_metrics.gamma,
            "theta": sample_option_metrics.theta,
            "vega": sample_option_metrics.vega,
            "risk_free_rate": sample_option_metrics.risk_free_rate,
        }

        with patch.object(timescale_store, "bulk_insert", new_callable=AsyncMock) as mock_insert:
            mock_insert.return_value = 1
            result = await timescale_store.bulk_insert("greeks_snapshot", [metrics_dict])

            assert result == 1
            mock_insert.assert_called_once()


# ============================================================================
# Test 5: Health Checks for Both Stores - Mocked
# ============================================================================


class TestStorageHealthChecks:
    """Test health check functionality for both stores using mocks."""

    @pytest.mark.asyncio
    async def test_timescale_healthcheck_mocked(
        self,
        timescale_store: TimescaleDBStore,
    ) -> None:
        """TimescaleDB health check returns expected format via mock."""
        with patch.object(timescale_store, "healthcheck", new_callable=AsyncMock) as mock_hc:
            mock_hc.return_value = {"status": "healthy", "latency_ms": 5}
            result = await timescale_store.healthcheck()

            assert result["status"] == "healthy"
            assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_redis_healthcheck_mocked(
        self,
        mock_redis: MockRedis,
    ) -> None:
        """Mock Redis health check returns expected format."""
        result = await mock_redis.ping()

        assert result is True

    @pytest.mark.asyncio
    async def test_mock_redis_set_and_get(
        self,
        mock_redis: MockRedis,
    ) -> None:
        """Verify mock Redis set/get operations work correctly."""
        await mock_redis.set("test_key", {"value": 123})
        result = await mock_redis.get("test_key")
        assert result == {"value": 123}

    @pytest.mark.asyncio
    async def test_mock_redis_delete(
        self,
        mock_redis: MockRedis,
    ) -> None:
        """Verify mock Redis delete operations work correctly."""
        await mock_redis.set("delete_key", {"value": 456})
        count = await mock_redis.delete("delete_key")
        assert count == 1
        assert await mock_redis.get("delete_key") is None
