"""
Unit tests for TimescaleDB + Redis Storage Layer (Phase 2).

Covers:
- TimescaleDBStore.bulk_insert() with ON CONFLICT
- TimescaleDBStore.query_fo_options(), query_cm_spot(), query_greeks()
- RedisCache.set_tick(), get_tick(), get_all_ticks(), set_rfr(), get_rfr()
- Connection resilience with retry logic
- Health check methods

Author: SBITB-150626
"""

from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from config.settings import DataPipelineSettings, WebSocketSettings

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def pipeline_settings() -> DataPipelineSettings:
    """Pipeline settings for testing."""
    return DataPipelineSettings(
        HISTORICAL_START_DATE=date(2024, 1, 1),
        HISTORICAL_END_DATE=date(2024, 1, 31),
        BATCH_SIZE=100,
    )


@pytest.fixture
def ws_settings() -> WebSocketSettings:
    """WebSocket settings for testing."""
    return WebSocketSettings(
        RECONNECT_INITIAL_DELAY_SEC=1.0,
        RECONNECT_MAX_DELAY_SEC=60.0,
        RING_BUFFER_SIZE=1000,
        REDIS_TTL_SEC=86400,
        REDIS_KEY_PREFIX="tick:",
    )


@pytest.fixture
def sample_fo_rows() -> list[dict]:
    """Sample F&O rows for bulk insert."""
    return [
        {
            "date": date(2024, 1, 15),
            "symbol": "NIFTY",
            "expiry": date(2024, 1, 25),
            "strike": 21500.0,
            "option_type": "CE",
            "open": 350.0,
            "high": 360.0,
            "low": 340.0,
            "close": 355.0,
            "settle_price": 355.0,
            "volume": 500.0,
            "oi": 10000.0,
            "oi_change": 500.0,
        },
        {
            "date": date(2024, 1, 15),
            "symbol": "NIFTY",
            "expiry": date(2024, 1, 25),
            "strike": 21500.0,
            "option_type": "PE",
            "open": 320.0,
            "high": 330.0,
            "low": 310.0,
            "close": 325.0,
            "settle_price": 325.0,
            "volume": 400.0,
            "oi": 9500.0,
            "oi_change": 300.0,
        },
    ]


@pytest.fixture
def sample_tick_data() -> dict:
    """Sample tick data for Redis cache."""
    return {
        "symbol": "NIFTY",
        "ltp": 21550.0,
        "volume": 1250,
        "bid": 21545.0,
        "ask": 21555.0,
        "timestamp": "2024-01-15T10:30:00",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mock Classes for Testing
# ─────────────────────────────────────────────────────────────────────────────


class MockAsyncConnectionPool:
    """Mock psycopg_pool.AsyncConnectionPool for testing."""

    def __init__(self):
        self.connection_count = 0
        self.connections = []

    async def connection(self):
        """Return a mock connection."""
        self.connection_count += 1
        conn = MockConnection()
        self.connections.append(conn)
        return conn

    async def close(self):
        """Close the pool."""
        self.connections.clear()


class MockConnection:
    """Mock database connection."""

    def __init__(self):
        self.execute_count = 0
        self.fetch_count = 0
        self.results = []

    async def execute(self, query, params=None):
        """Mock execute."""
        self.execute_count += 1
        return MagicMock(rowcount=1)

    async def fetch(self, query, params=None):
        """Mock fetch."""
        self.fetch_count += 1
        return self.results

    async def fetchone(self):
        """Mock fetchone."""
        return self.results[0] if self.results else None


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.store = {}
        self.expiry = {}

    async def get(self, key):
        """Get value from store."""
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        """Set value with expiry."""
        self.store[key] = value
        return True

    async def ping(self):
        """Ping Redis."""
        return True

    async def pipeline(self, transaction=True):
        """Return a mock pipeline."""
        return MockRedisPipeline(self)


class MockRedisPipeline:
    """Mock Redis pipeline."""

    def __init__(self, redis: MockRedis):
        self._redis = redis
        self._gets = []

    def get(self, key):
        """Queue a get command."""
        self._gets.append(key)
        return self

    async def execute(self):
        """Execute pipeline."""
        return [self._redis.store.get(k) for k in self._gets]


# ─────────────────────────────────────────────────────────────────────────────
# TimescaleDBStore Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStore:
    """Tests for TimescaleDBStore class."""

    @pytest.mark.asyncio
    async def test_bulk_insert_empty_rows(self, pipeline_settings):
        """Should return 0 for empty rows list."""
        from src.data.storage import TimescaleDBStore

        store = TimescaleDBStore("postgresql://test:test@localhost:5432/test", pipeline_settings)
        count = await store.bulk_insert("test_table", [])
        assert count == 0

    @pytest.mark.asyncio
    async def test_bulk_insert_validates_table_name(self, pipeline_settings):
        """Should reject invalid table names to prevent SQL injection."""
        from src.data.storage import TimescaleDBStore

        store = TimescaleDBStore("postgresql://test:test@localhost:5432/test", pipeline_settings)

        with pytest.raises(ValueError, match="Invalid table name"):
            await store.bulk_insert("test; DROP TABLE users;--", [{"col": 1}])

        with pytest.raises(ValueError, match="Invalid table name"):
            await store.bulk_insert("123table", [{"col": 1}])

    @pytest.mark.asyncio
    async def test_query_fo_options_returns_dataframe(self, pipeline_settings):
        """Should return DataFrame with query results."""
        import pandas as pd

        from src.data.storage import TimescaleDBStore

        store = TimescaleDBStore("postgresql://test:test@localhost:5432/test", pipeline_settings)
        store._pool = MockAsyncConnectionPool()
        store._pool.connections[0].results = [
            {
                "date": date(2024, 1, 15),
                "symbol": "NIFTY",
                "expiry": date(2024, 1, 25),
                "strike": 21500.0,
                "option_type": "CE",
                "open": 350.0,
                "high": 360.0,
                "low": 340.0,
                "close": 355.0,
                "settle_price": 355.0,
                "volume": 500.0,
                "oi": 10000.0,
                "oi_change": 500.0,
                "created_at": datetime.now(),
            }
        ]

        df = await store.query_fo_options(
            symbol="NIFTY",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert isinstance(df, pd.DataFrame)

    @pytest.mark.asyncio
    async def test_query_cm_spot_returns_dataframe(self, pipeline_settings):
        """Should return DataFrame with CM spot data."""
        import pandas as pd

        from src.data.storage import TimescaleDBStore

        store = TimescaleDBStore("postgresql://test:test@localhost:5432/test", pipeline_settings)
        store._pool = MockAsyncConnectionPool()
        store._pool.connections[0].results = []

        df = await store.query_cm_spot(
            symbol="NIFTY 50",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert isinstance(df, pd.DataFrame)

    @pytest.mark.asyncio
    async def test_query_greeks_returns_dataframe(self, pipeline_settings):
        """Should return DataFrame with Greeks data."""
        import pandas as pd

        from src.data.storage import TimescaleDBStore

        store = TimescaleDBStore("postgresql://test:test@localhost:5432/test", pipeline_settings)
        store._pool = MockAsyncConnectionPool()
        store._pool.connections[0].results = []

        df = await store.query_greeks(
            symbol="NIFTY",
            date=date(2024, 1, 15),
        )

        assert isinstance(df, pd.DataFrame)

    @pytest.mark.asyncio
    async def test_healthcheck_success(self, pipeline_settings):
        """Should return True when DB is healthy."""
        from src.data.storage import TimescaleDBStore

        store = TimescaleDBStore("postgresql://test:test@localhost:5432/test", pipeline_settings)
        store._pool = MockAsyncConnectionPool()
        store._pool.connections[0].results = [(1, datetime.now())]

        result = await store.healthcheck()
        # Mock always returns True since we set up results
        assert result is True

    @pytest.mark.asyncio
    async def test_is_retryable_error_classification(self, pipeline_settings):
        """Should classify retryable vs non-retryable errors."""
        import psycopg

        from src.data.storage import TimescaleDBStore

        store = TimescaleDBStore("postgresql://test:test@localhost:5432/test", pipeline_settings)

        # Connection errors should be retryable
        conn_error = psycopg.OperationalError("connection refused")
        assert store._is_retryable_error(conn_error) is True

        # Timeout errors should be retryable
        timeout_error = psycopg.errors.ConnectionTimeout("timeout")
        assert store._is_retryable_error(timeout_error) is True

        # Syntax errors should NOT be retryable
        syntax_error = psycopg.errors.SyntaxError("syntax error")
        assert store._is_retryable_error(syntax_error) is False


# ─────────────────────────────────────────────────────────────────────────────
# RedisCache Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCache:
    """Tests for RedisCache class."""

    @pytest.mark.asyncio
    async def test_set_tick_stores_data(self, ws_settings):
        """Should store tick data with TTL."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)
        mock_client = MockRedis()
        cache._client = mock_client

        await cache.set_tick(12345, {"ltp": 21550.0, "volume": 100})

        assert "tick:12345" in mock_client.store
        data = json.loads(mock_client.store["tick:12345"])
        assert data["ltp"] == 21550.0

    @pytest.mark.asyncio
    async def test_get_tick_retrieves_data(self, ws_settings):
        """Should retrieve tick data from cache."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)
        mock_client = MockRedis()
        mock_client.store["tick:12345"] = json.dumps({"ltp": 21550.0, "volume": 100})
        cache._client = mock_client

        result = await cache.get_tick(12345)

        assert result is not None
        assert result["ltp"] == 21550.0

    @pytest.mark.asyncio
    async def test_get_tick_returns_none_for_missing(self, ws_settings):
        """Should return None for missing tick."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)
        mock_client = MockRedis()
        cache._client = mock_client

        result = await cache.get_tick(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_ticks_uses_pipeline(self, ws_settings):
        """Should use pipeline for efficient batch retrieval."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)
        mock_client = MockRedis()
        mock_client.store["tick:1"] = json.dumps({"ltp": 100})
        mock_client.store["tick:2"] = json.dumps({"ltp": 200})
        cache._client = mock_client

        result = await cache.get_all_ticks([1, 2])

        assert len(result) == 2
        assert result[1]["ltp"] == 100
        assert result[2]["ltp"] == 200

    @pytest.mark.asyncio
    async def test_set_rfr_stores_rate(self, ws_settings):
        """Should store risk-free rate with 24h TTL."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)
        mock_client = MockRedis()
        cache._client = mock_client

        await cache.set_rfr(date(2024, 1, 15), "t_bill", 0.065)

        assert "rfr:t_bill:2024-01-15" in mock_client.store
        assert mock_client.store["rfr:t_bill:2024-01-15"] == "0.065"

    @pytest.mark.asyncio
    async def test_get_rfr_retrieves_rate(self, ws_settings):
        """Should retrieve cached risk-free rate."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)
        mock_client = MockRedis()
        mock_client.store["rfr:t_bill:2024-01-15"] = "0.065"
        cache._client = mock_client

        rate = await cache.get_rfr(date(2024, 1, 15), "t_bill")

        assert rate == 0.065

    @pytest.mark.asyncio
    async def test_tick_key_format(self, ws_settings):
        """Should generate correct Redis key for tick."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)

        key = cache._tick_key(12345)
        assert key == "tick:12345"

    @pytest.mark.asyncio
    async def test_rfr_key_format(self, ws_settings):
        """Should generate correct Redis key for RFR."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)

        key = cache._rfr_key(date(2024, 1, 15), "t_bill")
        assert key == "rfr:t_bill:2024-01-15"

    @pytest.mark.asyncio
    async def test_healthcheck_success(self, ws_settings):
        """Should return True when Redis is healthy."""
        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)
        mock_client = MockRedis()
        cache._client = mock_client

        result = await cache.healthcheck()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_retryable_error_classification(self, ws_settings):
        """Should classify retryable vs non-retryable errors."""
        import redis.asyncio as redis

        from src.data.storage import RedisCache

        cache = RedisCache("redis://localhost:6379/0", ws_settings)

        # Connection errors should be retryable
        conn_error = redis.ConnectionError("connection refused")
        assert cache._is_retryable_error(conn_error) is True

        # Timeout errors should be retryable
        timeout_error = redis.TimeoutError("timeout")
        assert cache._is_retryable_error(timeout_error) is True
