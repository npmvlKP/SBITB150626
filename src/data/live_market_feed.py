"""
Live Market Data Pipeline (Ph.2-7)

Production-grade WebSocket feed with:
- Exponential backoff reconnection
- Epoch-based fencing (Kleppmann Ch.4)
- Circular buffer with backpressure (Kleppmann Ch.4)
- Redis caching for low-latency access
- Event log append-only writes
- Daily 6:01 AM IST reauthentication
- ATM option strike auto-selection
- MCX commodity support
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Protocol

import redis
import structlog

from src.data.event_log import EventLogWriter, MarketEvent

if TYPE_CHECKING:
    from src.risk.audit import AuditLogger

logger = structlog.get_logger(__name__)

# Constants
RECONNECT_INITIAL_DELAY_SEC = 2.0
RECONNECT_BACKOFF_FACTOR = 2.0
RECONNECT_MAX_DELAY_SEC = 60.0
RECONNECT_MAX_ATTEMPTS = 10
PERSIST_INTERVAL_SEC = 1.0
HEARTBEAT_TIMEOUT_SEC = 30.0
REDIS_TTL_SEC = 10.0
NIFTY_STRIKE_INTERVAL = 50.0
BANKNIFTY_STRIKE_INTERVAL = 100.0
REAUTH_TIME_HOUR = 6
REAUTH_TIME_MINUTE = 1
REAUTH_TIME_SECOND = 0


class WSConnectionState(Enum):
    """WebSocket connection states."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    REAUTHENTICATING = auto()


@dataclass
class WebSocketSettings:
    """Settings for WebSocket connection."""

    max_buffer_size: int = 10000
    max_reconnect_attempts: int = RECONNECT_MAX_ATTEMPTS
    reconnect_delay_sec: float = RECONNECT_INITIAL_DELAY_SEC
    reconnect_max_delay_sec: float = RECONNECT_MAX_DELAY_SEC
    heartbeat_timeout_sec: float = HEARTBEAT_TIMEOUT_SEC
    persist_interval_sec: float = PERSIST_INTERVAL_SEC
    redis_ttl_sec: float = REDIS_TTL_SEC


class KiteBrokerProtocol(Protocol):
    """Protocol for Kite broker interface."""

    @property
    def access_token(self) -> str:
        """Get current access token."""
        ...

    async def authenticate(self) -> bool:
        """Refresh access token."""
        ...

    def get_instrument_token(self, exchange: str, symbol: str) -> int | None:
        """Get instrument token for exchange:symbol."""
        ...


class TickRingBuffer:
    """Fixed-capacity circular buffer with backpressure (Kleppmann Ch.4).

    Thread-safe circular buffer that automatically drops oldest ticks when full.
    Tracks dropped_count for Prometheus metrics.
    """

    def __init__(self, capacity: int) -> None:
        """Initialize ring buffer.

        Args:
            capacity: Maximum number of ticks in buffer
        """
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self.dropped_count: int = 0
        self._capacity = capacity

    def push(self, tick: dict[str, Any]) -> None:
        """Push tick to buffer, dropping oldest if full.

        Args:
            tick: Tick dictionary to push
        """
        with self._lock:
            if len(self._buffer) >= self._capacity:
                self.dropped_count += 1
                logger.warning(
                    "ring_buffer_full",
                    dropped_total=self.dropped_count,
                    capacity=self._capacity,
                )
            self._buffer.append(tick)

    def drain(self, max_items: int) -> list[dict[str, Any]]:
        """Atomically remove and return up to max_items.

        Args:
            max_items: Maximum number of items to drain

        Returns:
            List of drained ticks (may be empty)
        """
        with self._lock:
            if max_items >= len(self._buffer):
                items = list(self._buffer)
                self._buffer.clear()
            else:
                items = []
                for _ in range(max_items):
                    if self._buffer:
                        items.append(self._buffer.popleft())
            return items

    def __len__(self) -> int:
        """Return current buffer size."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Clear all ticks from buffer."""
        with self._lock:
            self._buffer.clear()


class LiveMarketFeed:
    """Live market data feed with Kite WebSocket integration.

    Features:
    - Automatic reconnection with exponential backoff
    - Epoch-based fencing for connection safety
    - Circular buffer with backpressure
    - Redis caching for low-latency access
    - Event log append-only writes
    - Daily 6:01 AM IST reauthentication
    - ATM option strike auto-selection
    - MCX commodity support

    Args:
        kite_api: KiteBroker interface
        settings: WebSocketSettings configuration
        event_writer: EventLogWriter for persisting events
        redis_client: Redis client for caching
        audit_logger: AuditLogger for compliance logging
    """

    def __init__(
        self,
        kite_api: KiteBrokerProtocol,
        settings: WebSocketSettings,
        event_writer: EventLogWriter,
        redis_client: redis.Redis[Any],
        audit_logger: AuditLogger,
    ) -> None:
        """Initialize LiveMarketFeed."""
        self._kite_api = kite_api
        self._settings = settings
        self._event_writer = event_writer
        self._redis = redis_client
        self._audit = audit_logger

        # State
        self._state: WSConnectionState = WSConnectionState.DISCONNECTED
        self._epoch: int = 0  # Fencing token, incremented on each reconnect
        self._kws: Any = None  # KiteTicker instance
        self._ring_buffer = TickRingBuffer(settings.max_buffer_size)
        self._reconnect_attempts: int = 0

        # Background tasks
        self._persist_task: asyncio.Task[Any] | None = None
        self._heartbeat_task: asyncio.Task[Any] | None = None
        self._reauth_task: asyncio.Task[Any] | None = None
        self._is_running: bool = False

        # Heartbeat tracking
        self._last_tick_time: datetime | None = None

        # Instrument subscriptions
        self._subscribed_tokens: set[int] = set()

        logger.info(
            "live_market_feed_initialized",
            max_buffer_size=settings.max_buffer_size,
            reconnect_max_attempts=settings.max_reconnect_attempts,
        )

    async def start(self) -> None:
        """Start the live market feed."""
        if self._is_running:
            logger.warning("live_market_feed_already_running")
            return

        self._is_running = True
        logger.info("starting_live_market_feed")

        # Initialize KiteTicker
        await self._initialize_kws()

        # Start background tasks
        self._persist_task = asyncio.create_task(self._persist_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        self._reauth_task = asyncio.create_task(self._reauth_scheduler())

        # Connect to WebSocket
        await self.connect()

        await self._audit.log_event(
            event_type="SESSION_START",
            source="live_market_feed",
            details={"feed": "kite_ws"},
        )

    async def stop(self) -> None:
        """Stop the live market feed gracefully."""
        if not self._is_running:
            return

        self._is_running = False
        logger.info("stopping_live_market_feed")

        # Cancel background tasks
        for task in [self._persist_task, self._heartbeat_task, self._reauth_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Flush remaining ticks
        await self._flush_ticks()

        # Close WebSocket
        if self._kws:
            self._kws.close()
            self._kws = None

        self._state = WSConnectionState.DISCONNECTED

        await self._audit.log_event(
            event_type="SESSION_END",
            source="live_market_feed",
            details={"final_epoch": self._epoch},
        )

    async def _initialize_kws(self) -> None:
        """Initialize KiteTicker instance."""
        try:
            # Import here to avoid dependency issues
            from kiteconnect import KiteTicker

            self._kws = KiteTicker(
                self._kite_api.api_key,  # type: ignore
                self._kite_api.access_token,
            )

            # Assign callbacks
            self._kws.on_ticks = self._on_ticks
            self._kws.on_connect = self._on_connect
            self._kws.on_close = self._on_close
            self._kws.on_error = self._on_error
            self._kws.on_reconnect = self._on_reconnect

            logger.info("kite_ticker_initialized")

        except ImportError as err:
            logger.error("kiteconnect_not_installed")
            raise RuntimeError("kiteconnect package not installed") from err
        except Exception as e:
            logger.error("kite_ticker_init_failed", error=str(e))
            raise

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if self._state == WSConnectionState.CONNECTED:
            return

        self._state = WSConnectionState.CONNECTING

        try:
            if self._kws:
                self._kws.connect(threaded=True)
                logger.info("websocket_connection_attempted")
            else:
                raise RuntimeError("KiteTicker not initialized")

        except Exception as e:
            logger.error("websocket_connect_failed", error=str(e))
            self._state = WSConnectionState.RECONNECTING
            await self._handle_reconnect()

    def _on_connect(self, ws: Any, response: dict[str, Any]) -> None:
        """WebSocket connect callback.

        Args:
            ws: WebSocket instance
            response: Connection response
        """
        # Increment epoch (fencing token)
        self._epoch += 1

        # Clear old ticks from buffer
        self._ring_buffer.clear()

        # Subscribe to instruments
        self._subscribe_instruments()

        self._state = WSConnectionState.CONNECTED
        self._reconnect_attempts = 0

        logger.info(
            "websocket_connected",
            epoch=self._epoch,
            instruments=len(self._subscribed_tokens),
        )

        # Log to audit
        asyncio.create_task(
            self._audit.log_event(
                event_type="WS_CONNECTED",
                source="live_market_feed",
                details={
                    "epoch": self._epoch,
                    "instruments": len(self._subscribed_tokens),
                },
            )
        )

    def _on_ticks(self, ws: Any, ticks: list[dict[str, Any]]) -> None:
        """WebSocket ticks callback.

        Args:
            ws: WebSocket instance
            ticks: List of tick dictionaries
        """
        self._last_tick_time = datetime.now(UTC)

        for tick in ticks:
            # Add epoch field
            tick["epoch"] = self._epoch

            # Push to ring buffer
            self._ring_buffer.push(tick)

            # Write to Redis (cache, not source of truth)
            self._write_to_redis(tick)

    def _on_close(self, ws: Any, code: int, reason: str) -> None:
        """WebSocket close callback.

        Args:
            ws: WebSocket instance
            code: Close code
            reason: Close reason
        """
        logger.warning(
            "websocket_closed",
            code=code,
            reason=reason,
            epoch=self._epoch,
        )

        self._state = WSConnectionState.RECONNECTING

        # Trigger reconnect
        asyncio.create_task(self._handle_reconnect())

    def _on_error(self, ws: Any, code: int, reason: str) -> None:
        """WebSocket error callback.

        Args:
            ws: WebSocket instance
            code: Error code
            reason: Error reason
        """
        logger.error(
            "websocket_error",
            code=code,
            reason=reason,
        )

        # Check for TokenException (403)
        if code == 403 or "token" in reason.lower():
            logger.warning("token_expired_initiating_reauth")
            self._state = WSConnectionState.REAUTHENTICATING
        else:
            # Network error - trigger reconnect
            asyncio.create_task(self._handle_reconnect())

    def _on_reconnect(self, ws: Any, response: dict[str, Any]) -> None:
        """WebSocket reconnect callback.

        Args:
            ws: WebSocket instance
            response: Reconnect response
        """
        logger.info("websocket_reconnected")

    def _subscribe_instruments(self) -> None:
        """Subscribe to NIFTY, BANKNIFTY options and MCX futures."""
        try:
            # Subscribe to NIFTY options
            self._subscribe_nifty_options()

            # Subscribe to BANKNIFTY options
            self._subscribe_banknifty_options()

            # Subscribe to MCX futures
            self._subscribe_mcx_futures()

        except Exception as e:
            logger.error("subscribe_instruments_failed", error=str(e))

    def _subscribe_nifty_options(self) -> None:
        """Subscribe to NIFTY spot and ATM options."""
        try:
            # Get NIFTY spot price
            spot_price = self._get_spot_price("NSE", "NIFTY 50")
            if spot_price is None:
                logger.warning("nifty_spot_price_unavailable")
                return

            # Compute ATM strikes
            strikes = compute_atm_subscriptions(
                spot_price=spot_price,
                strike_interval=NIFTY_STRIKE_INTERVAL,
                num_strikes=25,
            )

            # Get instrument tokens
            tokens: list[int] = []
            for strike in strikes:
                ce_token = self._kite_api.get_instrument_token("NFO", f"NIFTY{strike}CE")
                pe_token = self._kite_api.get_instrument_token("NFO", f"NIFTY{strike}PE")

                if ce_token:
                    tokens.append(ce_token)
                if pe_token:
                    tokens.append(pe_token)

            # Subscribe in FULL mode
            if tokens:
                self._kws.subscribe(tokens)
                self._kws.set_mode(tokens, self._kws.MODE_FULL)
                self._subscribed_tokens.update(tokens)

            logger.info("subscribed_nifty_options", tokens=len(tokens))

        except Exception as e:
            logger.error("subscribe_nifty_failed", error=str(e))

    def _subscribe_banknifty_options(self) -> None:
        """Subscribe to BANKNIFTY spot and ATM options."""
        try:
            # Get BANKNIFTY spot price
            spot_price = self._get_spot_price("NSE", "NIFTY BANK")
            if spot_price is None:
                logger.warning("banknifty_spot_price_unavailable")
                return

            # Compute ATM strikes
            strikes = compute_atm_subscriptions(
                spot_price=spot_price,
                strike_interval=BANKNIFTY_STRIKE_INTERVAL,
                num_strikes=25,
            )

            # Get instrument tokens
            tokens: list[int] = []
            for strike in strikes:
                ce_token = self._kite_api.get_instrument_token("NFO", f"BANKNIFTY{strike}CE")
                pe_token = self._kite_api.get_instrument_token("NFO", f"BANKNIFTY{strike}PE")

                if ce_token:
                    tokens.append(ce_token)
                if pe_token:
                    tokens.append(pe_token)

            # Subscribe in FULL mode
            if tokens:
                self._kws.subscribe(tokens)
                self._kws.set_mode(tokens, self._kws.MODE_FULL)
                self._subscribed_tokens.update(tokens)

            logger.info("subscribed_banknifty_options", tokens=len(tokens))

        except Exception as e:
            logger.error("subscribe_banknifty_failed", error=str(e))

    def _subscribe_mcx_futures(self) -> None:
        """Subscribe to MCX commodity futures (GOLD, SILVER, CRUDEOIL)."""
        try:
            instruments = ["GOLDM", "SILVERM", "CRUDEOILM"]
            tokens: list[int] = []

            for instr in instruments:
                token = self._kite_api.get_instrument_token("MCX", instr)
                if token:
                    tokens.append(token)

            # Subscribe in QUOTE mode
            if tokens:
                self._kws.subscribe(tokens)
                self._kws.set_mode(tokens, self._kws.MODE_QUOTE)
                self._subscribed_tokens.update(tokens)

            logger.info("subscribed_mcx_futures", tokens=len(tokens))

        except Exception as e:
            logger.error("subscribe_mcx_failed", error=str(e))

    def _get_spot_price(self, exchange: str, symbol: str) -> float | None:
        """Get spot price from Redis or EOD data.

        Args:
            exchange: Exchange name (NSE)
            symbol: Symbol name

        Returns:
            Spot price or None
        """
        try:
            # Try Redis first
            key = f"spot:{exchange}:{symbol}"
            value = self._redis.get(key)

            if value:
                return float(value)

            # TODO: Fall back to cm_spot_eod table
            logger.debug("spot_price_not_in_redis", exchange=exchange, symbol=symbol)
            return None

        except Exception as e:
            logger.error("get_spot_price_failed", error=str(e))
            return None

    def _write_to_redis(self, tick: dict[str, Any]) -> None:
        """Write tick to Redis cache.

        Args:
            tick: Tick dictionary
        """
        try:
            instrument_token = tick.get("instrument_token")
            if instrument_token:
                key = f"tick:{instrument_token}"
                value = json.dumps(tick, default=str)
                self._redis.setex(key, int(self._settings.redis_ttl_sec), value)
        except Exception as e:
            logger.warning("redis_write_failed", error=str(e))

    async def _handle_reconnect(self) -> None:
        """Handle reconnection with exponential backoff."""
        await self._reconnect_with_backoff()

    async def _reconnect_with_backoff(self) -> None:
        """Attempt reconnection with exponential backoff."""
        while self._is_running and self._reconnect_attempts < self._settings.max_reconnect_attempts:
            self._reconnect_attempts += 1

            # Calculate delay
            delay = min(
                self._settings.reconnect_delay_sec * (self._settings.reconnect_delay_sec**self._reconnect_attempts),
                self._settings.reconnect_max_delay_sec,
            )

            logger.info(
                "reconnect_attempt",
                attempt=self._reconnect_attempts,
                delay_sec=delay,
                max_attempts=self._settings.max_reconnect_attempts,
            )

            await asyncio.sleep(delay)

            # Try to reconnect
            try:
                if self._kws:
                    self._kws.reconnect()
                    return
            except Exception as e:
                logger.warning("reconnect_failed", error=str(e))

        # Max attempts reached - activate kill switch
        logger.critical("max_reconnect_attempts_reached")
        # TODO: Activate kill switch at PAUSE level

    async def _reauth_scheduler(self) -> None:
        """Schedule daily reauthentication at 6:01 AM IST."""
        while self._is_running:
            try:
                # Calculate seconds until next 6:01 AM IST
                now = datetime.now(UTC)
                target = now.replace(hour=0, minute=51, second=0, microsecond=0)

                # 6:01 AM IST = 00:31 UTC (IST = UTC+5:30)
                target = target.replace(hour=0, minute=31, second=0, microsecond=0)

                if now >= target:
                    # Already past, schedule for tomorrow
                    target += timedelta(days=1)

                wait_seconds = (target - now).total_seconds()

                logger.info("scheduled_reauth", wait_seconds=wait_seconds, target=target)

                await asyncio.sleep(wait_seconds)

                # Perform reauthentication
                await self._perform_reauth()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("reauth_scheduler_error", error=str(e))
                await asyncio.sleep(60)  # Wait before retrying

    async def _perform_reauth(self) -> None:
        """Perform reauthentication with Kite."""
        try:
            logger.info("initiating_reauth")

            # Authenticate with Kite
            success = await self._kite_api.authenticate()

            if not success:
                logger.critical("reauth_failed")
                # TODO: Activate kill switch at PAUSE level
                return

            # Stop old connection
            if self._kws:
                self._kws.close()

            # Reinitialize KiteTicker with new token
            await self._initialize_kws()

            # Reconnect
            await self.connect()

            logger.info("reauth_successful")

        except Exception as e:
            logger.critical("reauth_exception", error=str(e))
            # TODO: Activate kill switch at PAUSE level

    async def _persist_loop(self) -> None:
        """Periodically persist ticks to database."""
        while self._is_running:
            try:
                await asyncio.sleep(self._settings.persist_interval_sec)

                await self._persist_ticks()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("persist_loop_error", error=str(e))

    async def _persist_ticks(self) -> None:
        """Persist buffered ticks to event log and ws_ticks table."""
        try:
            # Drain ticks from ring buffer
            ticks = self._ring_buffer.drain(1000)

            if not ticks:
                return

            # Convert to MarketEvent list
            events = [
                MarketEvent(
                    event_id=uuid.uuid4(),
                    event_type="WS_TICK",
                    source="kite_ws",
                    payload=tick,
                    epoch=tick.get("epoch", self._epoch),
                )
                for tick in ticks
            ]

            # Write to event log
            for event in events:
                await self._event_writer.append(event)

            # Write to ws_ticks table
            await self._write_to_ws_ticks_table(ticks)

            logger.info(
                "ticks_persisted",
                count=len(ticks),
                epoch=self._epoch,
                lag_ms=self._calculate_lag_ms(),
            )

        except Exception as e:
            logger.error("persist_ticks_failed", error=str(e))

    async def _write_to_ws_ticks_table(self, ticks: list[dict[str, Any]]) -> None:
        """Write ticks to ws_ticks table using bulk insert.

        Args:
            ticks: List of tick dictionaries
        """
        try:
            # TODO: Implement bulk write to ws_ticks table
            # Use psycopg COPY or execute_values for performance
            pass

        except Exception as e:
            logger.error("write_ws_ticks_failed", error=str(e))

    async def _heartbeat_monitor(self) -> None:
        """Monitor for silent disconnects."""
        while self._is_running:
            try:
                await asyncio.sleep(self._settings.heartbeat_timeout_sec)

                # Check if any tick received recently
                if self._last_tick_time:
                    time_since_last_tick = (datetime.now(UTC) - self._last_tick_time).total_seconds()

                    if time_since_last_tick > self._settings.heartbeat_timeout_sec * 2:
                        if self._state == WSConnectionState.CONNECTED:
                            logger.warning(
                                "silent_disconnect_detected",
                                time_since_last_tick_sec=time_since_last_tick,
                            )
                            # Trigger reconnect
                            self._state = WSConnectionState.RECONNECTING
                            await self._handle_reconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("heartbeat_monitor_error", error=str(e))

    async def _flush_ticks(self) -> None:
        """Flush remaining ticks to database."""
        ticks = self._ring_buffer.drain(self._settings.max_buffer_size)
        if ticks:
            await self._persist_ticks()

    def _calculate_lag_ms(self) -> float:
        """Calculate processing lag in milliseconds."""
        if self._last_tick_time:
            return (datetime.now(UTC) - self._last_tick_time).total_seconds() * 1000
        return 0.0

    @property
    def state(self) -> WSConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def epoch(self) -> int:
        """Get current epoch (fencing token)."""
        return self._epoch

    @property
    def is_running(self) -> bool:
        """Check if feed is running."""
        return self._is_running


def generate_uuid() -> str:
    """Generate a new UUID string.

    Returns:
        UUID as string
    """
    return str(uuid.uuid4())


def compute_atm_subscriptions(spot_price: float, strike_interval: float, num_strikes: int) -> list[float]:
    """Compute ATM option strikes to subscribe.

    Returns list of strikes centered around spot price.

    Args:
        spot_price: Current spot price
        strike_interval: Strike interval (50 for NIFTY, 100 for BANKNIFTY)
        num_strikes: Number of strikes on each side of ATM

    Returns:
        List of strike prices to subscribe
    """
    # Find nearest ATM strike
    atm_strike = round(spot_price / strike_interval) * strike_interval

    # Generate strikes from ATM-N to ATM+N
    strikes = []
    for i in range(-num_strikes, num_strikes + 1):
        strike = atm_strike + (i * strike_interval)
        strikes.append(strike)

    return strikes
