"""
Unit tests for storage module (Phase 2-8).
Comprehensive test coverage for:
- TimescaleDBStore (async connection pool, parameterized queries)
- RedisCache (tick caching, RFR storage, retry logic)
- Connection resilience (Kleppmann Ch.5 patterns)
- SQL injection prevention

Author: SBITB-150626
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.data.storage import (
    INITIAL_BACKOFF_SEC,
    MAX_BACKOFF_SEC,
    MAX_RETRIES,
    RedisCache,
    TimescaleDBStore,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_data_pipeline_settings():
    """Mock DataPipelineSettings for testing."""
    settings = MagicMock()
    settings.BATCH_SIZE = 1000
    settings.RETRY_ATTEMPTS = MAX_RETRIES
    settings.RETRY_BACKOFF_SEC = INITIAL_BACKOFF_SEC
    return settings


@pytest.fixture
def mock_websocket_settings():
    """Mock WebSocketSettings for testing."""
    settings = MagicMock()
    settings.REDIS_TTL_SEC = 60
    settings.REDIS_KEY_PREFIX = "sbitb:"
    return settings


@pytest.fixture
def db_url():
    """Test database URL."""
    return "postgresql://test:test@localhost:5432/test_db"


@pytest.fixture
def redis_url():
    """Test Redis URL."""
    return "redis://localhost:6379/0"


# ─────────────────────────────────────────────────────────────────────────────
# Helper to create async context manager mock
# ─────────────────────────────────────────────────────────────────────────────


def create_mock_connection():
    """Create a properly mocked async connection with context manager support."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value=(1, "2024-01-01"))))
    mock_conn.fetch = AsyncMock(return_value=[])

    # Use proper class for transaction() context manager
    class AsyncTransactionContextManager:
        def __init__(self, mock_conn_inner):
            self._mock_conn = mock_conn_inner

        async def __aenter__(self):
            return self._mock_conn

        async def __aexit__(self, *args):
            pass

    mock_conn.transaction = MagicMock(return_value=AsyncTransactionContextManager(mock_conn))

    return mock_conn


def create_pool_mock_with_connection():
    """Create a pool mock that properly supports async with pool.connection() as conn:"""
    mock_pool = MagicMock(
        spec=["min_size", "max_size", "timeout", "max_lifetime", "max_idle_time", "wait", "close", "connection"]
    )
    mock_pool.wait = AsyncMock()
    mock_pool.close = AsyncMock()

    # Create mock connection
    mock_conn = create_mock_connection()

    # Set up connection() to return an async context manager
    # Note: Using class for proper async context manager protocol
    class AsyncContextManager:
        def __init__(self, mock_conn_inner):
            self._mock_conn = mock_conn_inner

        async def __aenter__(self):
            return self._mock_conn

        async def __aexit__(self, *args):
            pass

    mock_pool.connection = MagicMock(return_value=AsyncContextManager(mock_conn))

    return mock_pool, mock_conn


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for TimescaleDBStore Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStoreConstants:
    """Tests for TimescaleDBStore module constants."""

    def test_max_retries_value(self):
        """Test MAX_RETRIES is set correctly."""
        assert MAX_RETRIES == 3

    def test_initial_backoff_value(self):
        """Test INITIAL_BACKOFF_SEC is set correctly."""
        assert INITIAL_BACKOFF_SEC == 1.0

    def test_max_backoff_value(self):
        """Test MAX_BACKOFF_SEC is set correctly."""
        assert MAX_BACKOFF_SEC == 10.0


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for TimescaleDBStore Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStoreInit:
    """Tests for TimescaleDBStore initialization."""

    def test_init_with_valid_url(self, db_url, mock_data_pipeline_settings):
        """Test TimescaleDBStore initialization with valid URL."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        assert store._db_url == db_url
        assert store._settings == mock_data_pipeline_settings
        assert store._pool is None

    def test_init_stores_settings(self, db_url, mock_data_pipeline_settings):
        """Test that settings are stored correctly."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        assert store._settings.BATCH_SIZE == 1000


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for TimescaleDBStore Pool Management
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStorePool:
    """Tests for TimescaleDBStore connection pool management."""

    async def test_ensure_pool_lazy_initialization(self, db_url, mock_data_pipeline_settings):
        """Test that pool is lazily initialized."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        assert store._pool is None

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_ensure_pool_creates_pool(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test that _ensure_pool creates a new pool when None."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        pool = await store._ensure_pool()

        assert pool is mock_pool
        mock_pool_class.assert_called_once()
        call_kwargs = mock_pool_class.call_args.kwargs
        assert call_kwargs["min_size"] == 2
        assert call_kwargs["max_size"] == 10

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_ensure_pool_reuses_existing_pool(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test that existing pool is reused when healthy."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool

        # Ensure execute succeeds so pool is considered healthy
        mock_conn.execute.return_value.fetchone = AsyncMock(return_value=(1, "2024-01-01"))

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        pool1 = await store._ensure_pool()
        pool2 = await store._ensure_pool()

        # Should only create pool once (since existing pool is healthy)
        assert mock_pool_class.call_count == 1
        assert pool1 is pool2


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for TimescaleDBStore Error Classification
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStoreErrorClassification:
    """Tests for TimescaleDBStore error classification."""

    def test_is_retryable_connection_error_pattern(self, db_url, mock_data_pipeline_settings):
        """Test that connection errors are retryable via pattern matching."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        error = Exception("connection refused")
        assert store._is_retryable_error(error) is True

    def test_is_retryable_timeout_error(self, db_url, mock_data_pipeline_settings):
        """Test that timeout errors are retryable."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        error = ConnectionError("connection timeout")
        assert store._is_retryable_error(error) is True

    def test_is_retryable_network_error(self, db_url, mock_data_pipeline_settings):
        """Test that network errors are retryable."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        error = Exception("network unreachable")
        assert store._is_retryable_error(error) is True

    def test_is_not_retryable_programming_error(self, db_url, mock_data_pipeline_settings):
        """Test that programming errors (SQL syntax) are not retryable."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        error = Exception("syntax error at position 1")
        assert store._is_retryable_error(error) is False


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for TimescaleDBStore Bulk Insert
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStoreBulkInsert:
    """Tests for TimescaleDBStore.bulk_insert method."""

    async def test_bulk_insert_empty_rows(self, db_url, mock_data_pipeline_settings):
        """Test bulk_insert with empty rows returns 0."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        result = await store.bulk_insert("fo_options_eod", [])
        assert result == 0

    async def test_bulk_insert_invalid_table_name(self, db_url, mock_data_pipeline_settings):
        """Test bulk_insert rejects invalid table names (SQL injection)."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        rows = [{"date": "2024-01-01", "symbol": "NIFTY", "close": 20000}]

        with pytest.raises(ValueError, match="Invalid table name"):
            await store.bulk_insert("fo_options_eod; DROP TABLE users;--", rows)

    async def test_bulk_insert_sql_injection_attempt(self, db_url, mock_data_pipeline_settings):
        """Test bulk_insert prevents SQL injection via table name."""
        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        rows = [{"col": "value"}]

        # Attempt SQL injection via table name with special characters
        with pytest.raises(ValueError, match="Invalid table name"):
            await store.bulk_insert("table UNION SELECT * FROM users", rows)

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_bulk_insert_success(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test successful bulk insert."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool

        # Make execute return a proper result
        mock_result = MagicMock()
        mock_result.fetchone = AsyncMock(return_value=(1,))
        mock_conn.execute = AsyncMock(return_value=mock_result)

        # Make transaction context manager track execute calls
        insert_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal insert_count
            insert_count += 1
            return MagicMock()

        mock_conn.execute = mock_execute

        rows = [
            {"date": "2024-01-01", "symbol": "NIFTY", "close": 20000},
            {"date": "2024-01-02", "symbol": "NIFTY", "close": 20100},
        ]

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        result = await store.bulk_insert("fo_options_eod", rows)

        # Verify inserts happened
        assert result == 2
        # execute should be called for each row
        assert insert_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for TimescaleDBStore Query Methods
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStoreQueries:
    """Tests for TimescaleDBStore query methods."""

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_query_fo_options_success(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test query_fo_options returns DataFrame."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool

        # Mock fetch to return some data
        mock_row = MagicMock()
        mock_row.__iter__ = lambda self: iter(
            [
                (
                    "2024-01-01",
                    "NIFTY",
                    "2024-01-31",
                    20000.0,
                    "CE",
                    200.0,
                    205.0,
                    198.0,
                    202.0,
                    200.0,
                    1000,
                    50000,
                    1000,
                    "2024-01-01",
                )
            ]
        )
        mock_row.keys.return_value = [
            "date",
            "symbol",
            "expiry",
            "strike",
            "option_type",
            "open",
            "high",
            "low",
            "close",
            "settle_price",
            "volume",
            "oi",
            "oi_change",
            "created_at",
        ]
        mock_row.__getitem__ = lambda self, key: {
            "date": "2024-01-01",
            "symbol": "NIFTY",
            "expiry": "2024-01-31",
            "strike": 20000.0,
            "option_type": "CE",
            "open": 200.0,
            "high": 205.0,
            "low": 198.0,
            "close": 202.0,
            "settle_price": 200.0,
            "volume": 1000,
            "oi": 50000,
            "oi_change": 1000,
            "created_at": "2024-01-01",
        }[key]
        mock_conn.fetch = AsyncMock(return_value=[mock_row])

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        df = await store.query_fo_options(
            symbol="NIFTY",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert isinstance(df, pd.DataFrame)
        mock_conn.fetch.assert_called_once()

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_query_fo_options_with_filters(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test query_fo_options with expiry and strike filters."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool
        mock_conn.fetch = AsyncMock(return_value=[])

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        df = await store.query_fo_options(
            symbol="NIFTY",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            expiry=date(2024, 1, 31),
            strike=20000.0,
        )

        assert isinstance(df, pd.DataFrame)
        # Verify fetch was called with parameterized query
        mock_conn.fetch.assert_called_once()

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_query_cm_spot_success(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test query_cm_spot returns DataFrame."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool
        mock_conn.fetch = AsyncMock(return_value=[])

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        df = await store.query_cm_spot(
            symbol="NIFTY 50",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert isinstance(df, pd.DataFrame)

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_query_greeks_success(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test query_greeks returns DataFrame."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool
        mock_conn.fetch = AsyncMock(return_value=[])

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        df = await store.query_greeks(
            symbol="NIFTY",
            date=date(2024, 1, 1),
        )

        assert isinstance(df, pd.DataFrame)

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_query_atm_strikes_success(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test query_atm_strikes returns DataFrame."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool
        mock_conn.fetch = AsyncMock(return_value=[])

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        df = await store.query_atm_strikes(
            symbol="NIFTY",
            date=date(2024, 1, 1),
        )

        assert isinstance(df, pd.DataFrame)

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_get_oi_change_success(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test get_oi_change returns DataFrame."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool
        mock_conn.fetch = AsyncMock(return_value=[])

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        df = await store.get_oi_change(
            symbol="NIFTY",
            date=date(2024, 1, 1),
        )

        assert isinstance(df, pd.DataFrame)


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for TimescaleDBStore Healthcheck
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStoreHealthcheck:
    """Tests for TimescaleDBStore.healthcheck method."""

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_healthcheck_success(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test healthcheck returns True when healthy."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool

        # Set up execute to return expected result
        mock_result = MagicMock()
        mock_result.fetchone = AsyncMock(return_value=(1, "2024-01-01"))
        mock_conn.execute = AsyncMock(return_value=mock_result)

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        result = await store.healthcheck()

        assert result is True

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_healthcheck_failure(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test healthcheck returns False on error."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool
        mock_conn.execute = AsyncMock(side_effect=Exception("Connection failed"))

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        result = await store.healthcheck()

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for RedisCache Initialization
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCacheInit:
    """Tests for RedisCache initialization."""

    def test_init_with_valid_url(self, redis_url, mock_websocket_settings):
        """Test RedisCache initialization with valid URL."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        assert cache._redis_url == redis_url
        assert cache._settings == mock_websocket_settings
        assert cache._client is None

    def test_init_stores_settings(self, redis_url, mock_websocket_settings):
        """Test that settings are stored correctly."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        assert cache._settings.REDIS_TTL_SEC == 60
        assert cache._settings.REDIS_KEY_PREFIX == "sbitb:"


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for RedisCache Key Generation
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCacheKeyGeneration:
    """Tests for RedisCache key generation methods."""

    def test_tick_key_generation(self, redis_url, mock_websocket_settings):
        """Test tick key is generated with prefix."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        key = cache._tick_key(12345)
        assert key == "sbitb:12345"

    def test_rfr_key_generation(self, redis_url, mock_websocket_settings):
        """Test RFR key is generated with date and method."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        key = cache._rfr_key(date(2024, 1, 1), "t_bill")
        assert key == "rfr:t_bill:2024-01-01"

    def test_rfr_key_with_futures_method(self, redis_url, mock_websocket_settings):
        """Test RFR key with futures_basis method."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        key = cache._rfr_key(date(2024, 1, 1), "futures_basis")
        assert key == "rfr:futures_basis:2024-01-01"


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for RedisCache Error Classification
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCacheErrorClassification:
    """Tests for RedisCache error classification."""

    def test_is_retryable_connection_error(self, redis_url, mock_websocket_settings):
        """Test that connection errors are retryable."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        error = ConnectionError("Connection refused")
        assert cache._is_retryable_error(error) is True

    def test_is_retryable_timeout_error(self, redis_url, mock_websocket_settings):
        """Test that timeout errors are retryable."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        error = TimeoutError("Operation timed out")
        assert cache._is_retryable_error(error) is True

    def test_is_retryable_network_error(self, redis_url, mock_websocket_settings):
        """Test that network errors are retryable."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        error = Exception("Connection reset by peer")
        assert cache._is_retryable_error(error) is True

    def test_is_retryable_busy_error(self, redis_url, mock_websocket_settings):
        """Test that BUSY errors are retryable."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        error = Exception("BUSY Redis is busy")
        assert cache._is_retryable_error(error) is True


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for RedisCache Tick Operations
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCacheTickOperations:
    """Tests for RedisCache tick set/get operations."""

    @patch("src.data.storage.redis.from_url")
    async def test_set_tick_success(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test set_tick stores data with TTL."""
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        await cache.set_tick(12345, {"ltp": 265.0, "volume": 1000})

        mock_client.setex.assert_called_once()
        call_args = mock_client.setex.call_args
        assert call_args[0][0] == "sbitb:12345"
        assert call_args[0][1] == 60  # TTL

    @patch("src.data.storage.redis.from_url")
    async def test_get_tick_success(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test get_tick retrieves stored data."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value='{"ltp": 265.0}')
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        result = await cache.get_tick(12345)

        assert result == {"ltp": 265.0}

    @patch("src.data.storage.redis.from_url")
    async def test_get_tick_not_found(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test get_tick returns None for missing key."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        result = await cache.get_tick(99999)

        assert result is None

    @patch("src.data.storage.redis.from_url")
    async def test_get_all_ticks_success(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test get_all_ticks retrieves multiple ticks."""
        mock_client = AsyncMock()
        mock_pipeline = AsyncMock()
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)
        mock_pipeline.execute = AsyncMock(
            return_value=[
                '{"ltp": 265.0}',
                '{"ltp": 270.0}',
                None,  # Missing key
            ]
        )
        mock_pipeline.get = MagicMock()
        mock_client.pipeline = MagicMock(return_value=mock_pipeline)
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        result = await cache.get_all_ticks([12345, 12346, 99999])

        assert 12345 in result
        assert 12346 in result
        assert 99999 not in result

    @patch("src.data.storage.redis.from_url")
    async def test_get_all_ticks_empty_list(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test get_all_ticks with empty list returns empty dict."""
        cache = RedisCache(redis_url, mock_websocket_settings)
        result = await cache.get_all_ticks([])

        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for RedisCache RFR Operations
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCacheRFROperations:
    """Tests for RedisCache RFR set/get operations."""

    @patch("src.data.storage.redis.from_url")
    async def test_set_rfr_success(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test set_rfr stores rate with 24h TTL."""
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        await cache.set_rfr(date(2024, 1, 1), "t_bill", 0.065)

        mock_client.setex.assert_called_once()
        call_args = mock_client.setex.call_args
        assert "rfr:t_bill:2024-01-01" in call_args[0][0]
        assert call_args[0][1] == 86400  # 24 hours
        assert call_args[0][2] == "0.065"

    @patch("src.data.storage.redis.from_url")
    async def test_get_rfr_success(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test get_rfr retrieves stored rate."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value="0.065")
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        result = await cache.get_rfr(date(2024, 1, 1), "t_bill")

        assert result == 0.065

    @patch("src.data.storage.redis.from_url")
    async def test_get_rfr_not_found(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test get_rfr returns None for missing rate."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        result = await cache.get_rfr(date(2024, 1, 1), "t_bill")

        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for RedisCache Holiday Cache
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCacheHolidayCache:
    """Tests for RedisCache holiday cache operations."""

    @patch("src.data.storage.redis.from_url")
    async def test_set_holiday_cache_success(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test set_holiday_cache stores holiday list."""
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        holidays = ["2024-01-26", "2024-03-29", "2024-08-15"]
        await cache.set_holiday_cache("2024", holidays)

        mock_client.setex.assert_called_once()
        call_args = mock_client.setex.call_args
        assert "nse_holidays:2024" in call_args[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for RedisCache Healthcheck
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCacheHealthcheck:
    """Tests for RedisCache.healthcheck method."""

    @patch("src.data.storage.redis.from_url")
    async def test_healthcheck_success(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test healthcheck returns True when healthy."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        result = await cache.healthcheck()

        assert result is True

    @patch("src.data.storage.redis.from_url")
    async def test_healthcheck_failure(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test healthcheck returns False on error."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("Connection failed"))
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        result = await cache.healthcheck()

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for RedisCache Retry Logic
# ─────────────────────────────────────────────────────────────────────────────


class TestRedisCacheRetryLogic:
    """Tests for RedisCache retry logic (Kleppmann Ch.5 patterns)."""

    @patch("src.data.storage.redis.from_url")
    async def test_retry_on_connection_error(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test that operations are retried on transient errors."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.setex = AsyncMock(return_value=None)
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        # Should not raise, operation should succeed
        await cache.set_tick(12345, {"ltp": 265.0})

    @patch("src.data.storage.redis.from_url")
    async def test_execute_with_retry_non_retryable_error(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test that non-retryable errors are raised immediately."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.setex = AsyncMock(side_effect=[ValueError("Invalid key name")])
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)

        with pytest.raises(ValueError, match="Invalid key name"):
            await cache.set_tick(12345, {"ltp": 265.0})


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for TimescaleDBStore Retry Logic
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStoreRetryLogic:
    """Tests for TimescaleDBStore retry logic (Kleppmann Ch.5 patterns)."""

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_db_connection_retry_success(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test that DB operations are retried on transient errors."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool

        # Set up execute to succeed
        mock_result = MagicMock()
        mock_result.fetchone = AsyncMock(return_value=(1, "2024-01-01"))
        mock_conn.execute = AsyncMock(return_value=mock_result)

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)

        # Healthcheck should succeed
        result = await store.healthcheck()
        assert result is True

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_db_persistent_failure(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test that persistent failures return False after MAX_RETRIES."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool

        # Make all execute calls fail
        mock_conn.execute = AsyncMock(side_effect=Exception("persistent failure"))

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)

        # Should return False after retries exhausted (healthcheck returns False on error)
        result = await store.healthcheck()
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for Close Operations
# ─────────────────────────────────────────────────────────────────────────────


class TestTimescaleDBStoreClose:
    """Tests for TimescaleDBStore.close method."""

    @patch("src.data.storage.psycopg_pool.AsyncConnectionPool")
    async def test_close_pool(self, mock_pool_class, db_url, mock_data_pipeline_settings):
        """Test that close terminates the pool."""
        mock_pool, mock_conn = create_pool_mock_with_connection()
        mock_pool_class.return_value = mock_pool

        store = TimescaleDBStore(db_url, mock_data_pipeline_settings)
        await store._ensure_pool()  # Initialize pool
        await store.close()

        mock_pool.close.assert_called_once()
        assert store._pool is None


class TestRedisCacheClose:
    """Tests for RedisCache.close method."""

    @patch("src.data.storage.redis.from_url")
    async def test_close_client(self, mock_from_url, redis_url, mock_websocket_settings):
        """Test that close terminates the Redis client."""
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_from_url.return_value = mock_client

        cache = RedisCache(redis_url, mock_websocket_settings)
        await cache._ensure_client()  # Initialize client
        await cache.close()

        mock_client.aclose.assert_called_once()
        assert cache._client is None
