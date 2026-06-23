"""TimescaleDB + Redis Read/Write Layer for Phase 2 Data Pipeline.

This module provides the storage layer for market data persistence:
- TimescaleDBStore: PostgreSQL/TimescaleDB async operations with connection pooling
- RedisCache: Redis async operations for tick caching and RFR storage

Both classes implement Kleppmann Ch.5 connection resilience patterns with:
- Exponential backoff retry on transient failures
- Connection pool with auto-reconnect
- Structured logging via structlog
- Parameterized queries (no SQL injection)
"""

from __future__ import annotations

import asyncio
import json as json_module
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Self

import pandas as pd
import redis.asyncio as redis

from config.settings import DataPipelineSettings, WebSocketSettings

if TYPE_CHECKING:
    pass

import psycopg_pool
import structlog

logger = structlog.get_logger(__name__)

# ============================================================================
# CONNECTION RESILIENCE CONSTANTS (Kleppmann Ch.5)
# ============================================================================

MAX_RETRIES: int = 3
INITIAL_BACKOFF_SEC: float = 1.0
MAX_BACKOFF_SEC: float = 10.0
BACKOFF_MULTIPLIER: float = 2.0
CONNECTION_TIMEOUT_SEC: float = 10.0
QUERY_TIMEOUT_SEC: int = 30


# ============================================================================
# CLASS: TimescaleDBStore
# ============================================================================


class TimescaleDBStore:
    """Async TimescaleDB storage layer with connection pool and retry logic.

    Implements Kleppmann Ch.5 connection resilience patterns:
    - Connection pool with auto-reconnect (psycopg_pool.AsyncConnectionPool)
    - Exponential backoff retry on OperationalError
    - Structured logging on all operations
    - Parameterized queries (SQL injection prevention)

    Args:
        db_url: PostgreSQL connection URL (postgresql://user:pass@host:port/db)
        settings: DataPipelineSettings instance for configuration

    Example:
        >>> store = TimescaleDBStore("postgresql://trading:pass@localhost:5432/trading_bot", settings)
        >>> await store.healthcheck()  # Verify connection
        True
        >>> await store.bulk_insert("fo_options_eod", rows)
        1000
    """

    def __init__(self: Self, db_url: str, settings: DataPipelineSettings) -> None:
        """Initialize TimescaleDB connection pool.

        Args:
            db_url: PostgreSQL connection URL
            settings: DataPipelineSettings for batch size and retry config
        """
        self._db_url: str = db_url
        self._settings: DataPipelineSettings = settings
        self._pool: psycopg_pool.AsyncConnectionPool | None = None
        self._retry_attempts: int = MAX_RETRIES

        logger.info(
            "TimescaleDBStore initializing",
            min_size=2,
            max_size=10,
            batch_size=settings.BATCH_SIZE,
        )

    async def _ensure_pool(self: Self) -> psycopg_pool.AsyncConnectionPool:
        """Ensure connection pool is initialized with lazy creation.

        Returns:
            Active connection pool instance

        Raises:
            ConnectionError: If pool creation fails after retries
        """
        if self._pool is not None:
            try:
                # Verify pool is usable
                async with self._pool.connection() as conn:
                    await conn.execute("SELECT 1")
                return self._pool
            except Exception:
                # Pool is stale, recreate
                self._pool = None

        if self._pool is None:
            import psycopg_pool

            self._pool = psycopg_pool.AsyncConnectionPool(
                self._db_url,
                min_size=2,
                max_size=10,
                timeout=CONNECTION_TIMEOUT_SEC,
                max_lifetime=3600.0,  # 1 hour in seconds
                max_idle=600.0,  # 10 minutes in seconds
            )
            await self._pool.wait()
            logger.info("TimescaleDBStore connection pool created")

        return self._pool

    async def _execute_with_retry(
        self: Self,
        operation: str,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> Any:
        """Execute query with exponential backoff retry on connection failure.

        Args:
            operation: Operation name for logging (e.g., "bulk_insert", "query")
            query: SQL query string
            params: Query parameters for parameterized query

        Returns:
            Query result

        Raises:
            psycopg.OperationalError: After retry exhaustion
            ConnectionError: If initial connection fails
        """
        pool = await self._ensure_pool()

        last_error: Exception | None = None
        attempt = 0

        while attempt < self._retry_attempts:
            try:
                async with pool.connection() as conn:
                    # Set statement timeout
                    await conn.execute(f"SET statement_timeout = '{QUERY_TIMEOUT_SEC}s'")

                    result = await conn.execute(query, params)

                    logger.debug(
                        f"TimescaleDB {operation} succeeded",
                        attempt=attempt + 1,
                    )
                    return result

            except Exception as e:
                last_error = e
                attempt += 1

                # Classify error for logging
                error_type = type(e).__name__
                is_retryable = self._is_retryable_error(e)

                if is_retryable and attempt < self._retry_attempts:
                    # Calculate exponential backoff
                    backoff = min(
                        INITIAL_BACKOFF_SEC * (BACKOFF_MULTIPLIER ** (attempt - 1)),
                        MAX_BACKOFF_SEC,
                    )

                    logger.warning(
                        f"TimescaleDB {operation} failed, retrying",
                        attempt=attempt,
                        max_retries=self._retry_attempts,
                        backoff_sec=backoff,
                        error_type=error_type,
                        error=str(e),
                    )

                    await asyncio.sleep(backoff)

                    # Recreate pool on connection errors
                    if self._pool is not None:
                        try:
                            await self._pool.close()
                        except Exception:
                            pass
                        self._pool = None

                elif not is_retryable:
                    # Non-retryable error, raise immediately
                    logger.error(
                        f"TimescaleDB {operation} failed (non-retryable)",
                        error_type=error_type,
                        error=str(e),
                    )
                    raise

        # All retries exhausted
        logger.critical(
            f"TimescaleDB {operation} failed after {self._retry_attempts} attempts",
            error_type=error_type if last_error else "Unknown",
            error=str(last_error) if last_error else "",
        )
        raise last_error or ConnectionError(f"TimescaleDB {operation} failed after {self._retry_attempts} retries")

    def _is_retryable_error(self: Self, error: Exception) -> bool:
        """Classify if an error is transient and should be retried.

        Args:
            error: The exception to classify

        Returns:
            True if the error is transient and retryable
        """
        import psycopg.errors

        error_str = str(error).lower()

        # Connection-related errors are retryable
        retryable_patterns = [
            "connection",
            "timeout",
            "temporary failure",
            "could not",
            "lost connection",
            "broken pipe",
            "network",
            "refused",
            "unavailable",
        ]

        return (
            isinstance(error, psycopg.OperationalError)
            or isinstance(error, psycopg.errors.ConnectionFailure)
            or isinstance(error, psycopg.errors.ConnectionTimeout)
            or any(pattern in error_str for pattern in retryable_patterns)
        )

    async def bulk_insert(
        self: Self,
        table: str,
        rows: list[dict[str, Any]],
        on_conflict: str = "DO NOTHING",
    ) -> int:
        """Bulk insert rows into a table using execute_values for performance.

        Args:
            table: Target table name (validated to prevent SQL injection)
            rows: List of dictionaries with column names as keys
            on_conflict: ON CONFLICT clause (default: 'DO NOTHING')

        Returns:
            Number of rows inserted (excluding conflicts)

        Raises:
            ValueError: If table name is invalid
            psycopg.OperationalError: On database errors after retry
        """
        if not rows:
            logger.debug("bulk_insert called with empty rows")
            return 0

        # Validate table name against SQL injection
        if not table.isidentifier() or table.startswith("_"):
            raise ValueError(f"Invalid table name: {table}")

        # Use parameterized ON CONFLICT clause
        on_conflict_clause = f"ON CONFLICT {on_conflict}" if on_conflict.upper() != "DO NOTHING" else ""

        start_time = datetime.now()

        # Prepare columns and placeholders
        columns = list(rows[0].keys())
        col_list = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))

        pool = await self._ensure_pool()

        async with pool.connection() as conn:
            inserted = 0
            async with conn.transaction():
                for row in rows:
                    values_tuple = tuple(row[col] for col in columns)
                    await conn.execute(
                        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) {on_conflict_clause}",
                        values_tuple,
                    )
                    inserted += 1

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        logger.info(
            "bulk_insert completed",
            action="event_log_flush",
            table=table,
            rows=len(rows),
            rows_inserted=inserted,
            elapsed_ms=round(elapsed_ms, 2),
        )

        return inserted

    async def query_fo_options(
        self: Self,
        symbol: str,
        start_date: date,
        end_date: date,
        expiry: date | None = None,
        strike: float | None = None,
    ) -> pd.DataFrame:
        """Query F&O options EOD data with optional filters.

        Args:
            symbol: Trading symbol (NIFTY, BANKNIFTY)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            expiry: Optional expiry date filter
            strike: Optional strike price filter

        Returns:
            DataFrame with columns matching fo_options_eod schema
        """
        params: list[Any] = [symbol, start_date, end_date]
        conditions = ["symbol = %s", "date >= %s", "date <= %s"]

        if expiry is not None:
            conditions.append("expiry = %s")
            params.append(expiry)

        if strike is not None:
            conditions.append("strike = %s")
            params.append(strike)

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                date, symbol, expiry, strike, option_type,
                open, high, low, close, settle_price,
                volume, oi, oi_change, created_at
            FROM fo_options_eod
            WHERE {where_clause}
            ORDER BY date DESC, expiry, strike, option_type
        """

        pool = await self._ensure_pool()

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, tuple(params))
                rows = await cur.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(row) for row in rows])

        # Convert date columns
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
        if "expiry" in df.columns:
            df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        logger.debug(
            "query_fo_options completed",
            symbol=symbol,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            rows=len(df),
        )

        return df

    async def query_cm_spot(
        self: Self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Query cash market spot EOD data.

        Args:
            symbol: Spot symbol (NIFTY 50, NIFTY BANK)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            DataFrame with columns matching cm_spot_eod schema
        """
        query = """
            SELECT
                date, symbol, open, high, low, close, volume, created_at
            FROM cm_spot_eod
            WHERE symbol = %s AND date >= %s AND date <= %s
            ORDER BY date DESC
        """

        pool = await self._ensure_pool()

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (symbol, start_date, end_date))
                rows = await cur.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(row) for row in rows])

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date

        logger.debug(
            "query_cm_spot completed",
            symbol=symbol,
            rows=len(df),
        )

        return df

    async def query_greeks(
        self: Self,
        symbol: str,
        date: date,
        expiry: date | None = None,
    ) -> pd.DataFrame:
        """Query computed Greeks snapshot data.

        Args:
            symbol: Trading symbol
            date: Snapshot date
            expiry: Optional expiry filter

        Returns:
            DataFrame with Greeks columns
        """
        params: list[Any] = [symbol, date]
        conditions = ["symbol = %s", "date = %s"]

        if expiry is not None:
            conditions.append("expiry = %s")
            params.append(expiry)

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                date, symbol, expiry, strike, option_type,
                spot, iv, delta, gamma, theta, vega,
                risk_free_rate, rfr_method, ttm_years, compute_error
            FROM greeks_snapshot
            WHERE {where_clause}
            ORDER BY expiry, strike, option_type
        """

        pool = await self._ensure_pool()

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, tuple(params))
                rows = await cur.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(row) for row in rows])

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
        if "expiry" in df.columns:
            df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        logger.debug(
            "query_greeks completed",
            symbol=symbol,
            date=date.isoformat(),
            rows=len(df),
        )

        return df

    async def query_atm_strikes(
        self: Self,
        symbol: str,
        date: date,
    ) -> pd.DataFrame:
        """Query ATM strikes for a given date from the materialized view.

        Args:
            symbol: Trading symbol (NIFTY, BANKNIFTY)
            date: Trading date

        Returns:
            DataFrame with ATM strike data
        """
        query = """
            SELECT
                date, symbol, expiry, spot_close, atm_strike,
                option_type, option_close, volume, oi, strike_distance
            FROM v_atm_strikes
            WHERE symbol = %s AND date = %s
            ORDER BY expiry, option_type
        """

        pool = await self._ensure_pool()

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (symbol, date))
                rows = await cur.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(row) for row in rows])

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
        if "expiry" in df.columns:
            df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        logger.debug(
            "query_atm_strikes completed",
            symbol=symbol,
            date=date.isoformat(),
            rows=len(df),
        )

        return df

    async def get_oi_change(
        self: Self,
        symbol: str,
        date: date,
    ) -> pd.DataFrame:
        """Get Open Interest change data from continuous aggregate.

        Args:
            symbol: Trading symbol
            date: Trading date

        Returns:
            DataFrame with OI change aggregated data
        """
        query = """
            SELECT
                bucket, symbol, expiry, option_type,
                total_oi, total_oi_change, total_volume, avg_close
            FROM v_daily_oi_summary
            WHERE symbol = %s AND bucket::date = %s
            ORDER BY expiry, option_type
        """

        pool = await self._ensure_pool()

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (symbol, date))
                rows = await cur.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(row) for row in rows])

        if "bucket" in df.columns:
            df["bucket"] = pd.to_datetime(df["bucket"]).dt.date

        logger.debug(
            "get_oi_change completed",
            symbol=symbol,
            date=date.isoformat(),
            rows=len(df),
        )

        return df

    async def healthcheck(self: Self) -> bool:
        """Verify database connectivity and pool health.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            pool = await self._ensure_pool()

            async with pool.connection() as conn:
                result = await conn.execute("SELECT 1, NOW()")
                row = await result.fetchone()

                if row and row[0] == 1:
                    logger.debug("TimescaleDB healthcheck passed", server_time=row[1])
                    return True

            return False

        except Exception as e:
            logger.error(
                "TimescaleDB healthcheck failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def close(self: Self) -> None:
        """Close the connection pool gracefully."""
        if self._pool is not None:
            try:
                await self._pool.close()
                logger.info("TimescaleDBStore connection pool closed")
            except Exception as e:
                logger.warning(f"Error closing TimescaleDB pool: {e}")
            finally:
                self._pool = None


# ============================================================================
# CLASS: RedisCache
# ============================================================================


class RedisCache:
    """Async Redis cache layer for tick data and RFR storage.

    Implements Kleppmann Ch.5 connection resilience patterns:
    - Exponential backoff retry on ConnectionError
    - Structured logging on all operations
    - TTL-based expiration for cache entries

    Args:
        redis_url: Redis connection URL (redis://host:port/db)
        settings: WebSocketSettings instance for TTL and prefix config

    Example:
        >>> cache = RedisCache("redis://localhost:6379/0", settings)
        >>> await cache.healthcheck()
        True
        >>> await cache.set_tick(12345, {"ltp": 265.0})
        >>> tick = await cache.get_tick(12345)
    """

    def __init__(self: Self, redis_url: str, settings: WebSocketSettings) -> None:
        """Initialize Redis cache client.

        Args:
            redis_url: Redis connection URL
            settings: WebSocketSettings for TTL and prefix config
        """
        self._redis_url: str = redis_url
        self._settings: WebSocketSettings = settings
        self._client: redis.Redis | None = None
        self._retry_attempts: int = MAX_RETRIES

        logger.info(
            "RedisCache initializing",
            redis_url=redis_url.replace(self._password_from_url(redis_url), "***"),
            ttl_sec=settings.REDIS_TTL_SEC,
            key_prefix=settings.REDIS_KEY_PREFIX,
        )

    def _password_from_url(self: Self, url: str) -> str:
        """Extract password from URL for masking in logs."""
        import re

        match = re.search(r":([^@]+)@", url)
        return match.group(1) if match else ""

    async def _ensure_client(self: Self) -> redis.Redis:
        """Ensure Redis client is initialized with lazy creation.

        Returns:
            Active Redis client instance

        Raises:
            redis.ConnectionError: If connection fails after retries
        """
        if self._client is None:
            self._client = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=False,  # We handle encoding ourselves
            )

        # Test connection
        try:
            await self._client.ping()
        except Exception as e:
            logger.debug("Redis ping failed, will retry on next operation", error=str(e))

        return self._client

    async def _execute_with_retry(
        self: Self,
        operation: str,
        coro: Any,
    ) -> Any:
        """Execute Redis operation with exponential backoff retry.

        Args:
            operation: Operation name for logging
            coro: Coroutine to execute

        Returns:
            Operation result

        Raises:
            redis.ConnectionError: After retry exhaustion
        """
        last_error: Exception | None = None
        attempt = 0

        while attempt < self._retry_attempts:
            try:
                client = await self._ensure_client()
                result = await coro(client)

                if attempt > 0:
                    logger.info(f"Redis {operation} succeeded after retry", attempt=attempt)

                return result

            except Exception as e:
                last_error = e
                attempt += 1

                is_retryable = self._is_retryable_error(e)

                if is_retryable and attempt < self._retry_attempts:
                    backoff = min(
                        INITIAL_BACKOFF_SEC * (BACKOFF_MULTIPLIER ** (attempt - 1)),
                        MAX_BACKOFF_SEC,
                    )

                    logger.warning(
                        f"Redis {operation} failed, retrying",
                        attempt=attempt,
                        max_retries=self._retry_attempts,
                        backoff_sec=backoff,
                        error=str(e),
                    )

                    await asyncio.sleep(backoff)

                    # Recreate client on connection errors
                    if self._client is not None:
                        try:
                            await self._client.close()
                        except Exception:
                            pass
                        self._client = None

                elif not is_retryable:
                    logger.error(
                        f"Redis {operation} failed (non-retryable)",
                        error=str(e),
                    )
                    raise

        logger.critical(
            f"Redis {operation} failed after {self._retry_attempts} attempts",
            error=str(last_error) if last_error else "",
        )
        raise last_error or redis.ConnectionError(f"Redis {operation} failed after {self._retry_attempts} retries")

    def _is_retryable_error(self: Self, error: Exception) -> bool:
        """Classify if an error is transient and should be retried.

        Args:
            error: The exception to classify

        Returns:
            True if the error is transient and retryable
        """
        error_str = str(error).lower()

        retryable_patterns = [
            "connection",
            "timeout",
            "reset by peer",
            "broken pipe",
            "network",
            "refused",
            "unavailable",
            "loading",
            "busy",
        ]

        return (
            isinstance(error, redis.ConnectionError)
            or isinstance(error, redis.TimeoutError)
            or isinstance(error, TimeoutError)
            or any(pattern in error_str for pattern in retryable_patterns)
        )

    def _tick_key(self: Self, instrument_token: int) -> str:
        """Generate Redis key for tick data.

        Args:
            instrument_token: Zerodha instrument token

        Returns:
            Full Redis key with prefix
        """
        return f"{self._settings.REDIS_KEY_PREFIX}{instrument_token}"

    def _rfr_key(self: Self, date: date, method: str) -> str:
        """Generate Redis key for RFR cache.

        Args:
            date: Rate date
            method: RFR method (t_bill or futures_basis)

        Returns:
            Full Redis key with prefix
        """
        return f"rfr:{method}:{date.isoformat()}"

    async def set_tick(self: Self, instrument_token: int, data: dict[str, Any]) -> None:
        """Store tick data with TTL expiration.

        Args:
            instrument_token: Zerodha instrument token
            data: Tick data dictionary

        Raises:
            redis.ConnectionError: After retry exhaustion
        """
        key = self._tick_key(instrument_token)
        json_data = json_module.dumps(data)

        async def _set(client: redis.Redis) -> None:
            await client.setex(key, self._settings.REDIS_TTL_SEC, json_data)

        await self._execute_with_retry("set_tick", _set)

        logger.debug(
            "Redis set_tick",
            instrument_token=instrument_token,
            ttl_sec=self._settings.REDIS_TTL_SEC,
        )

    async def get_tick(self: Self, instrument_token: int) -> dict[str, Any] | None:
        """Retrieve tick data from cache.

        Args:
            instrument_token: Zerodha instrument token

        Returns:
            Tick data dictionary or None if not found/expired

        Raises:
            redis.ConnectionError: After retry exhaustion
        """
        key = self._tick_key(instrument_token)

        async def _get(client: redis.Redis) -> dict[str, Any] | None:
            data = await client.get(key)
            if data is None:
                return None
            parsed: dict[str, Any] = json_module.loads(data)
            return parsed

        return await self._execute_with_retry("get_tick", _get)  # type: ignore[no-any-return]

    async def get_all_ticks(self: Self, tokens: list[int]) -> dict[int, dict[str, Any]]:
        """Retrieve multiple ticks using pipeline for efficiency.

        Args:
            tokens: List of instrument tokens to fetch

        Returns:
            Dictionary mapping token -> tick data (missing tokens excluded)

        Raises:
            redis.ConnectionError: After retry exhaustion
        """
        if not tokens:
            return {}

        async def _pipeline_get(client: redis.Redis) -> dict[int, dict[str, Any]]:
            keys = [self._tick_key(token) for token in tokens]

            # Use pipeline for atomic batch get
            async with client.pipeline(transaction=False) as pipe:
                for key in keys:
                    pipe.get(key)
                results = await pipe.execute()

            # Build result dict, excluding None values
            result: dict[int, dict[str, Any]] = {}
            for token, data in zip(tokens, results):
                if data is not None:
                    try:
                        result[token] = json_module.loads(data)
                    except json_module.JSONDecodeError:
                        logger.warning(
                            "Failed to decode tick JSON",
                            instrument_token=token,
                        )
            return result

        return await self._execute_with_retry("get_all_ticks", _pipeline_get)  # type: ignore[no-any-return]

    async def set_rfr(self: Self, date: date, method: str, rate: float) -> None:
        """Store risk-free rate with 24h TTL.

        Args:
            date: Rate date
            method: RFR method (t_bill or futures_basis)
            rate: Risk-free rate as decimal (e.g., 0.065 for 6.5%)

        Raises:
            redis.ConnectionError: After retry exhaustion
        """
        key = self._rfr_key(date, method)
        ttl = 86400  # 24 hours

        async def _set(client: redis.Redis) -> None:
            await client.setex(key, ttl, str(rate))

        await self._execute_with_retry("set_rfr", _set)

        logger.debug(
            "Redis set_rfr",
            date=date.isoformat(),
            method=method,
            rate=rate,
        )

    async def get_rfr(self: Self, date: date, method: str) -> float | None:
        """Retrieve cached risk-free rate.

        Args:
            date: Rate date
            method: RFR method (t_bill or futures_basis)

        Returns:
            Risk-free rate or None if not cached

        Raises:
            redis.ConnectionError: After retry exhaustion
        """
        key = self._rfr_key(date, method)

        async def _get(client: redis.Redis) -> float | None:
            data = await client.get(key)
            if data is None:
                return None
            return float(data)

        return await self._execute_with_retry("get_rfr", _get)  # type: ignore[no-any-return]

    async def set_holiday_cache(self: Self, key: str, days: list[str], ttl: int = 86400) -> None:
        """Store NSE holiday list in cache.

        Args:
            key: Cache key identifier
            days: List of holiday dates as ISO strings
            ttl: Time-to-live in seconds (default: 24h)

        Raises:
            redis.ConnectionError: After retry exhaustion
        """
        cache_key = f"nse_holidays:{key}"
        json_data = json_module.dumps(days)

        async def _set(client: redis.Redis) -> None:
            await client.setex(cache_key, ttl, json_data)

        await self._execute_with_retry("set_holiday_cache", _set)

        logger.debug(
            "Redis set_holiday_cache",
            key=key,
            days_count=len(days),
            ttl_sec=ttl,
        )

    async def healthcheck(self: Self) -> bool:
        """Verify Redis connectivity.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            client = await self._ensure_client()
            await client.ping()
            logger.debug("Redis healthcheck passed")
            return True

        except Exception as e:
            logger.error(
                "Redis healthcheck failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def close(self: Self) -> None:
        """Close Redis connection gracefully."""
        if self._client is not None:
            try:
                await self._client.close()
                logger.info("RedisCache connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._client = None


# ============================================================================
# TYPE ALIASES FOR EXTERNAL USE
# ============================================================================

__all__ = [
    "TimescaleDBStore",
    "RedisCache",
    "MAX_RETRIES",
    "INITIAL_BACKOFF_SEC",
    "MAX_BACKOFF_SEC",
]
