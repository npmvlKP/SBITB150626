"""
WebSocket Client Module for Real-Time Market Data

This module provides a robust WebSocket client implementation for handling
real-time market data streams from various brokers and data providers.
"""

import asyncio
import json
import logging
import ssl
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Protocol

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)

# =============================================================================
# Type Definitions
# =============================================================================


class WebSocketMessageType(Enum):
    """Types of WebSocket messages."""

    TEXT = auto()
    BINARY = auto()
    PING = auto()
    PONG = auto()
    CLOSE = auto()


@dataclass
class WebSocketMessage:
    """Represents a WebSocket message."""

    message_type: WebSocketMessageType
    raw_data: str | bytes
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class WebSocketError(Exception):
    """Custom exception for WebSocket errors."""

    def __init__(self, message: str, error_code: int | None = None, recoverable: bool = True):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.recoverable = recoverable
        self.timestamp = datetime.utcnow()


class WebSocketState(Enum):
    """WebSocket connection states."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    CLOSING = auto()
    CLOSED = auto()
    ERROR = auto()


# =============================================================================
# Event Types
# =============================================================================


class WebSocketEventType(Enum):
    """Types of WebSocket events."""

    CONNECTED = auto()
    DISCONNECTED = auto()
    MESSAGE_RECEIVED = auto()
    ERROR = auto()
    RECONNECT_ATTEMPT = auto()
    RECONNECT_SUCCESS = auto()
    RECONNECT_FAILED = auto()
    SUBSCRIPTION_SUCCESS = auto()
    SUBSCRIPTION_FAILED = auto()
    HEARTBEAT = auto()


@dataclass
class WebSocketEvent:
    """Represents a WebSocket event."""

    event_type: WebSocketEventType
    data: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: WebSocketError | None = None


# =============================================================================
# Statistics Tracking
# =============================================================================


@dataclass
class WebSocketStats:
    """Statistics for WebSocket connections."""

    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    errors: int = 0
    reconnect_attempts: int = 0
    successful_reconnects: int = 0
    connection_duration: timedelta = timedelta()
    last_message_time: datetime | None = None
    last_error_time: datetime | None = None
    last_error: str | None = None
    last_reconnect_time: datetime | None = None
    connection_start_time: datetime | None = None

    def reset(self) -> None:
        """Reset all statistics."""
        self.messages_sent = 0
        self.messages_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.errors = 0
        self.reconnect_attempts = 0
        self.successful_reconnects = 0
        self.connection_duration = timedelta()
        self.last_message_time = None
        self.last_error_time = None
        self.last_error = None
        self.last_reconnect_time = None
        self.connection_start_time = None


# =============================================================================
# Handler Interface
# =============================================================================


class WebSocketHandler(Protocol):
    """Protocol for WebSocket message handlers."""

    async def on_connect(self, client: "WebSocketClient") -> None:
        """Called when WebSocket connects."""
        ...

    async def on_disconnect(self, client: "WebSocketClient", reason: str | None = None) -> None:
        """Called when WebSocket disconnects."""
        ...

    async def on_message(self, message: WebSocketMessage) -> None:
        """Called when a message is received."""
        ...

    async def on_error(self, error: WebSocketError) -> None:
        """Called when an error occurs."""
        ...

    async def on_reconnect(self, attempt: int, client: "WebSocketClient") -> None:
        """Called when a reconnection attempt is made."""
        ...

    async def on_reconnect_success(self, client: "WebSocketClient") -> None:
        """Called when reconnection succeeds."""
        ...

    async def on_reconnect_failed(self, error: WebSocketError) -> None:
        """Called when reconnection fails."""
        ...


# =============================================================================
# WebSocket Client
# =============================================================================


class WebSocketClient:
    """
    Robust WebSocket client with automatic reconnection and error handling.

    Features:
    - Automatic reconnection with exponential backoff
    - Message queue for handling message bursts
    - Connection state management
    - Comprehensive statistics tracking
    - SSL/TLS support
    - Heartbeat/ping-pong mechanism
    """

    def __init__(
        self,
        url: str,
        handler: WebSocketHandler | None = None,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
        max_reconnect_attempts: int = 10,
        ping_interval: float = 30.0,
        message_queue_size: int = 1000,
        ssl_context: ssl.SSLContext | None = None,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        write_timeout: float = 10.0,
        auto_reconnect: bool = True,
    ):
        """
        Initialize the WebSocket client.

        Args:
            url: WebSocket server URL
            handler: Optional message handler
            reconnect_delay: Initial delay between reconnection attempts (seconds)
            max_reconnect_delay: Maximum delay between reconnection attempts (seconds)
            max_reconnect_attempts: Maximum number of reconnection attempts (0 = infinite)
            ping_interval: Interval for sending ping messages (seconds)
            message_queue_size: Maximum size of the message queue
            ssl_context: SSL context for secure connections
            connect_timeout: Connection timeout (seconds)
            read_timeout: Read timeout (seconds)
            write_timeout: Write timeout (seconds)
            auto_reconnect: Whether to automatically reconnect on disconnection
        """
        self._url = url
        self._handler = handler
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts
        self._ping_interval = ping_interval
        self._message_queue_size = message_queue_size
        self._ssl_context = ssl_context
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._auto_reconnect = auto_reconnect

        self._ws: Any | None = None
        self._state: WebSocketState = WebSocketState.DISCONNECTED
        self._stats: WebSocketStats = WebSocketStats()
        self._reconnect_task: asyncio.Task[Any] | None = None
        self._ping_task: asyncio.Task[Any] | None = None
        self._message_queue: asyncio.Queue[WebSocketMessage] = asyncio.Queue(maxsize=message_queue_size)
        self._queue_processing_task: asyncio.Task[Any] | None = None
        self._current_reconnect_delay: float = reconnect_delay
        self._reconnect_attempts: int = 0
        self._is_closing: bool = False

        # Event callbacks
        self._event_callbacks: dict[
            WebSocketEventType, list[Callable[[WebSocketEvent], Coroutine[Any, Any, None]]]
        ] = {}

        logger.info(
            f"WebSocketClient initialized for {url} with "
            f"auto_reconnect={auto_reconnect}, "
            f"reconnect_delay={reconnect_delay}s"
        )

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def connect(self) -> bool:
        """Establish WebSocket connection."""
        if self._state == WebSocketState.CONNECTED:
            logger.warning("Already connected")
            return True

        if self._state == WebSocketState.CONNECTING:
            logger.warning("Connection already in progress")
            return True

        self._state = WebSocketState.CONNECTING
        self._stats.connection_start_time = datetime.utcnow()
        self._reconnect_attempts = 0
        self._current_reconnect_delay = self._reconnect_delay

        try:
            # Create SSL context if not provided
            ssl_context = self._ssl_context
            if ssl_context is None and self._url.startswith("wss://"):
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED

            # Connect with timeout
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self._url,
                    ssl=ssl_context,
                    ping_interval=self._ping_interval,
                    ping_timeout=self._read_timeout,
                    close_timeout=self._write_timeout,
                ),
                timeout=self._connect_timeout,
            )

            self._state = WebSocketState.CONNECTED
            self._stats.connection_start_time = datetime.utcnow()
            self._reconnect_attempts = 0
            self._current_reconnect_delay = self._reconnect_delay

            # Start background tasks
            await self._start_ping_task()
            await self._start_queue_processing()

            # Notify handler
            if self._handler:
                try:
                    await self._handler.on_connect(self)
                except Exception as e:
                    logger.error(f"Handler on_connect error: {e}")

            # Emit connected event
            await self._emit_event(WebSocketEventType.CONNECTED, {"url": self._url})

            logger.info(f"WebSocket connected to {self._url}")
            return True

        except TimeoutError as e:
            self._state = WebSocketState.ERROR
            error = WebSocketError(f"Connection timeout after {self._connect_timeout}s", recoverable=True)
            if self._handler:
                try:
                    await self._handler.on_error(error)
                except Exception as handler_error:
                    logger.error(f"Handler on_error error: {handler_error}")
            await self._emit_event(WebSocketEventType.ERROR, {"error": str(e)}, error)
            logger.error(f"Connection timeout: {e}")
            return False

        except (ConnectionClosed, WebSocketException) as e:
            self._state = WebSocketState.ERROR
            error = WebSocketError(f"Connection failed: {e}", error_code=getattr(e, "code", None), recoverable=True)
            if self._handler:
                try:
                    await self._handler.on_error(error)
                except Exception as handler_error:
                    logger.error(f"Handler on_error error: {handler_error}")
            await self._emit_event(WebSocketEventType.ERROR, {"error": str(e)}, error)
            logger.error(f"Connection failed: {e}")
            return False

        except Exception as e:
            self._state = WebSocketState.ERROR
            error = WebSocketError(f"Unexpected connection error: {e}", recoverable=True)
            if self._handler:
                try:
                    await self._handler.on_error(error)
                except Exception as handler_error:
                    logger.error(f"Handler on_error error: {handler_error}")
            await self._emit_event(WebSocketEventType.ERROR, {"error": str(e)}, error)
            logger.error(f"Unexpected connection error: {e}")
            return False

    async def disconnect(self, reason: str | None = None) -> bool:
        """Disconnect from WebSocket."""
        if self._state in (WebSocketState.DISCONNECTED, WebSocketState.CLOSED):
            return True

        self._is_closing = True
        self._state = WebSocketState.CLOSING

        # Cancel reconnection task
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        # Cancel ping task
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None

        # Cancel queue processing task
        if self._queue_processing_task:
            self._queue_processing_task.cancel()
            try:
                await self._queue_processing_task
            except asyncio.CancelledError:
                pass
            self._queue_processing_task = None

        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close(
                    code=1000,  # Normal closure
                    reason=reason or "Client disconnect",
                )
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
            finally:
                self._ws = None

        self._state = WebSocketState.CLOSED
        self._is_closing = False

        # Update connection duration
        if self._stats.connection_start_time:
            self._stats.connection_duration = datetime.utcnow() - self._stats.connection_start_time

        # Notify handler
        if self._handler:
            try:
                await self._handler.on_disconnect(self, reason)
            except Exception as e:
                logger.error(f"Handler on_disconnect error: {e}")

        # Emit disconnected event
        await self._emit_event(WebSocketEventType.DISCONNECTED, {"reason": reason})

        logger.info(f"WebSocket disconnected: {reason or 'No reason'}")
        return True

    async def reconnect(self) -> bool:
        """Manually trigger reconnection."""
        if self._state == WebSocketState.CONNECTED:
            logger.warning("Already connected, no need to reconnect")
            return True

        if self._state == WebSocketState.CONNECTING:
            logger.warning("Connection already in progress")
            return True

        if self._state == WebSocketState.CLOSING:
            logger.warning("Currently closing, wait for disconnect before reconnecting")
            return False

        logger.info("Initiating reconnection...")

        # Disconnect first if needed
        if self._state not in (WebSocketState.DISCONNECTED, WebSocketState.CLOSED, WebSocketState.ERROR):
            await self.disconnect("Reconnecting")

        # Start reconnection process
        if self._auto_reconnect:
            await self._start_reconnect_task()

        return True

    # =========================================================================
    # Automatic Reconnection
    # =========================================================================

    async def _start_reconnect_task(self) -> None:
        """Start the automatic reconnection task."""
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Reconnection loop with exponential backoff."""
        while not self._is_closing:
            if self._state == WebSocketState.CONNECTED:
                break

            if self._max_reconnect_attempts > 0 and self._reconnect_attempts >= self._max_reconnect_attempts:
                logger.warning(f"Max reconnection attempts ({self._max_reconnect_attempts}) reached")
                self._state = WebSocketState.ERROR

                error = WebSocketError(
                    f"Max reconnection attempts ({self._max_reconnect_attempts}) exceeded", recoverable=False
                )

                if self._handler:
                    try:
                        await self._handler.on_reconnect_failed(error)
                    except Exception as e:
                        logger.error(f"Handler on_reconnect_failed error: {e}")

                await self._emit_event(
                    WebSocketEventType.RECONNECT_FAILED,
                    {"attempts": self._reconnect_attempts, "last_delay": self._current_reconnect_delay},
                    error,
                )
                break

            self._reconnect_attempts += 1
            self._stats.reconnect_attempts += 1

            # Notify handler about reconnect attempt
            if self._handler:
                try:
                    await self._handler.on_reconnect(self._reconnect_attempts, self)
                except Exception as e:
                    logger.error(f"Handler on_reconnect error: {e}")

            await self._emit_event(
                WebSocketEventType.RECONNECT_ATTEMPT,
                {"attempt": self._reconnect_attempts, "delay": self._current_reconnect_delay, "url": self._url},
            )

            logger.info(
                f"Reconnection attempt {self._reconnect_attempts}/{self._max_reconnect_attempts or '∞'} "
                f"in {self._current_reconnect_delay:.1f}s for {self._url}"
            )

            # Wait before reconnecting
            try:
                await asyncio.sleep(self._current_reconnect_delay)
            except asyncio.CancelledError:
                break

            # Try to connect
            if await self.connect():
                self._stats.successful_reconnects += 1
                self._stats.last_reconnect_time = datetime.utcnow()

                # Reset reconnect delay on success
                self._current_reconnect_delay = self._reconnect_delay

                # Notify handler
                if self._handler:
                    try:
                        await self._handler.on_reconnect_success(self)
                    except Exception as e:
                        logger.error(f"Handler on_reconnect_success error: {e}")

                await self._emit_event(
                    WebSocketEventType.RECONNECT_SUCCESS, {"attempts": self._reconnect_attempts, "url": self._url}
                )

                logger.info(f"Reconnection successful after {self._reconnect_attempts} attempts")
                break
            else:
                # Increase delay with exponential backoff
                self._current_reconnect_delay = min(self._current_reconnect_delay * 2, self._max_reconnect_delay)

                logger.warning(f"Reconnection failed, next attempt in {self._current_reconnect_delay:.1f}s")

        self._reconnect_task = None

    # =========================================================================
    # Message Handling
    # =========================================================================

    async def send(self, message: str | bytes | dict[str, Any]) -> bool:
        """
        Send a message through the WebSocket.

        Args:
            message: Message to send (string, bytes, or dict)

        Returns:
            True if message was sent successfully, False otherwise
        """
        if self._state != WebSocketState.CONNECTED:
            logger.warning(f"Cannot send message: not connected (state={self._state})")
            return False

        if not self._ws:
            logger.warning("Cannot send message: WebSocket not initialized")
            return False

        try:
            if isinstance(message, dict):
                message_str = json.dumps(message)
                await self._ws.send(message_str)
                self._stats.bytes_sent += len(message_str)
            elif isinstance(message, str):
                await self._ws.send(message)
                self._stats.bytes_sent += len(message)
            else:
                await self._ws.send(message)
                self._stats.bytes_sent += len(message)

            self._stats.messages_sent += 1
            return True

        except ConnectionClosed as e:
            logger.error(f"Connection closed while sending: {e}")

            # Trigger reconnection
            if self._auto_reconnect:
                self._state = WebSocketState.RECONNECTING
                await self._start_reconnect_task()

            return False

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self._stats.errors += 1
            self._stats.last_error = str(e)
            self._stats.last_error_time = datetime.utcnow()

            if self._handler:
                try:
                    await self._handler.on_error(WebSocketError(f"Send error: {e}"))
                except Exception as handler_error:
                    logger.error(f"Handler on_error error: {handler_error}")

            return False

    async def send_raw(self, message: str | bytes) -> bool:
        """
        Send a raw message without any processing.

        Args:
            message: Raw message to send

        Returns:
            True if message was sent successfully, False otherwise
        """
        if self._state != WebSocketState.CONNECTED:
            return False

        if not self._ws:
            return False

        try:
            if isinstance(message, str):
                await self._ws.send(message)
                self._stats.bytes_sent += len(message)
            else:
                await self._ws.send(message)
                self._stats.bytes_sent += len(message)

            self._stats.messages_sent += 1
            return True

        except Exception as e:
            logger.error(f"Failed to send raw message: {e}")
            return False

    async def receive(self) -> WebSocketMessage | None:
        """Receive a message from the WebSocket.

        Returns:
            WebSocketMessage or None if no message received
        """
        if self._state != WebSocketState.CONNECTED:
            return None

        if not self._ws:
            return None

        try:
            message = await self._ws.recv()
            self._stats.messages_received += 1
            self._stats.bytes_received += len(message) if isinstance(message, str) else len(message)
            self._stats.last_message_time = datetime.utcnow()

            # Process message
            ws_message = await self._process_received_message(message)

            # Notify handler
            if self._handler:
                try:
                    await self._handler.on_message(ws_message)
                except Exception as e:
                    logger.error(f"Handler on_message error: {e}")

            # Emit message received event
            await self._emit_event(
                WebSocketEventType.MESSAGE_RECEIVED,
                {"message_type": ws_message.message_type.name, "data": ws_message.data},
            )

            return ws_message

        except ConnectionClosed as e:
            logger.warning(f"Connection closed while receiving: {e}")

            # Trigger reconnection
            if self._auto_reconnect and self._state.value != WebSocketState.CLOSING.value:
                self._state = WebSocketState.RECONNECTING
                await self._start_reconnect_task()

            return None

        except TimeoutError:
            # This is normal for read operations with timeout
            return None

        except Exception as e:
            logger.error(f"Failed to receive message: {e}")
            self._stats.errors += 1
            self._stats.last_error = str(e)
            self._stats.last_error_time = datetime.utcnow()

            if self._handler:
                try:
                    await self._handler.on_error(WebSocketError(f"Receive error: {e}"))
                except Exception as handler_error:
                    logger.error(f"Handler on_error error: {handler_error}")

            # Trigger reconnection for recoverable errors
            if self._auto_reconnect and self._state.value != WebSocketState.CLOSING.value:
                self._state = WebSocketState.RECONNECTING
                await self._start_reconnect_task()

            return None

    async def _process_received_message(self, message: str | bytes) -> WebSocketMessage:
        """Process a received WebSocket message.

        Args:
            message: Raw message from WebSocket

        Returns:
            Processed WebSocketMessage
        """
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("Received non-UTF-8 message, using raw bytes")
                return WebSocketMessage(
                    message_type=WebSocketMessageType.BINARY,
                    raw_data=message,
                    data={},
                )

        # Try to parse as JSON
        try:
            data = json.loads(message)
            return WebSocketMessage(
                message_type=WebSocketMessageType.TEXT,
                raw_data=message,
                data=data,
            )
        except json.JSONDecodeError:
            # If not JSON, treat as plain text
            return WebSocketMessage(
                message_type=WebSocketMessageType.TEXT,
                raw_data=message,
                data={"message": message},
            )

    # =========================================================================
    # Background Tasks
    # =========================================================================

    async def _start_ping_task(self) -> None:
        """Start the ping task for heartbeat."""
        if self._ping_task:
            self._ping_task.cancel()

        self._ping_task = asyncio.create_task(self._ping_loop())

    async def _ping_loop(self) -> None:
        """Ping loop for heartbeat."""
        while self._state == WebSocketState.CONNECTED:
            try:
                if self._ws:
                    await self._ws.ping()
                    await self._emit_event(WebSocketEventType.HEARTBEAT, {"type": "ping"})
                await asyncio.sleep(self._ping_interval)
            except ConnectionClosed:
                # Connection was closed
                if self._auto_reconnect and self._state.value != WebSocketState.CLOSING.value:
                    self._state = WebSocketState.RECONNECTING
                    await self._start_reconnect_task()
                break
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
                await asyncio.sleep(self._ping_interval)

    async def _start_queue_processing(self) -> None:
        """Start processing messages from the queue."""
        if self._queue_processing_task:
            self._queue_processing_task.cancel()

        self._queue_processing_task = asyncio.create_task(self._queue_processing_loop())

    async def _queue_processing_loop(self) -> None:
        """Process messages from the queue."""
        while self._state == WebSocketState.CONNECTED:
            try:
                # Receive message directly instead of using queue
                message = await self.receive()
                if message is None:
                    await asyncio.sleep(0.1)
                    continue

            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
                await asyncio.sleep(1.0)

    # =========================================================================
    # Event System
    # =========================================================================

    def on(
        self, event_type: WebSocketEventType, callback: Callable[[WebSocketEvent], Coroutine[Any, Any, None]]
    ) -> None:
        """Register an event callback."""
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        self._event_callbacks[event_type].append(callback)

    def off(
        self, event_type: WebSocketEventType, callback: Callable[[WebSocketEvent], Coroutine[Any, Any, None]]
    ) -> None:
        """Unregister an event callback."""
        if event_type in self._event_callbacks:
            try:
                self._event_callbacks[event_type].remove(callback)
            except ValueError:
                pass

    async def _emit_event(
        self, event_type: WebSocketEventType, data: dict[str, Any] | None = None, error: WebSocketError | None = None
    ) -> None:
        """Emit an event to all registered callbacks."""
        event = WebSocketEvent(event_type=event_type, data=data, error=error)

        if event_type in self._event_callbacks:
            for callback in self._event_callbacks[event_type]:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(f"Event callback error for {event_type}: {e}")

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._state == WebSocketState.CONNECTED

    @property
    def state(self) -> WebSocketState:
        """Get current connection state."""
        return self._state

    @property
    def stats(self) -> WebSocketStats:
        """Get connection statistics."""
        return self._stats

    @property
    def url(self) -> str:
        """Get the WebSocket URL."""
        return self._url

    @property
    def handler(self) -> WebSocketHandler | None:
        """Get the message handler."""
        return self._handler

    @handler.setter
    def handler(self, handler: WebSocketHandler | None) -> None:
        """Set the message handler."""
        self._handler = handler

    def reset_stats(self) -> None:
        """Reset connection statistics."""
        self._stats.reset()

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    async def __aenter__(self) -> "WebSocketClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()


# =============================================================================
# Base Handler Implementation
# =============================================================================


class BaseWebSocketHandler:
    """Base implementation of WebSocketHandler with default behavior."""

    async def on_connect(self, client: WebSocketClient) -> None:
        """Called when WebSocket connects."""
        logger.info(f"WebSocket connected to {client.url}")

    async def on_disconnect(self, client: WebSocketClient, reason: str | None = None) -> None:
        """Called when WebSocket disconnects."""
        logger.info(f"WebSocket disconnected: {reason or 'No reason'}")

    async def on_message(self, message: WebSocketMessage) -> None:
        """Called when a message is received."""
        logger.debug(f"Received message: {message.data}")

    async def on_error(self, error: WebSocketError) -> None:
        """Called when an error occurs."""
        logger.error(f"WebSocket error: {error.message}")

    async def on_reconnect(self, attempt: int, client: WebSocketClient) -> None:
        """Called when a reconnection attempt is made."""
        logger.info(f"Reconnection attempt {attempt} for {client.url}")

    async def on_reconnect_success(self, client: WebSocketClient) -> None:
        """Called when reconnection succeeds."""
        logger.info(f"Reconnection successful for {client.url}")

    async def on_reconnect_failed(self, error: WebSocketError) -> None:
        """Called when reconnection fails."""
        logger.error(f"Reconnection failed: {error.message}")


# =============================================================================
# Kite Ticker Handler
# =============================================================================


class KiteTickerHandler(BaseWebSocketHandler):
    """Handler for Zerodha Kite ticker WebSocket messages."""

    def __init__(self, api_key: str, access_token: str):
        """
        Initialize the Kite ticker handler.

        Args:
            api_key: Kite API key
            access_token: Kite access token
        """
        self._api_key = api_key
        self._access_token = access_token
        self._subscriptions: dict[int, dict[str, Any]] = {}
        self._last_tick_time: datetime | None = None
        self._ticks_received: int = 0

    async def on_connect(self, client: WebSocketClient) -> None:
        """Called when WebSocket connects."""
        logger.info(f"Kite ticker connected to {client.url}")

        # Authenticate and resubscribe
        await self._authenticate(client)

    async def _authenticate(self, client: WebSocketClient) -> bool:
        """Authenticate with Kite ticker."""
        try:
            auth_message = {"a": self._api_key, "v": "1.0"}

            # Set access token in headers (Kite uses this for authentication)
            if client._ws:
                client._ws.request_headers["Authorization"] = f"token {self._api_key}:{self._access_token}"

            # Send authentication message
            await client.send(json.dumps(auth_message))
            logger.info("Kite ticker authentication message sent")
            return True

        except Exception as e:
            logger.error(f"Kite ticker authentication failed: {e}")
            return False

    async def on_message(self, message: WebSocketMessage) -> None:
        """Process Kite ticker messages."""
        self._ticks_received += 1
        self._last_tick_time = datetime.utcnow()

        try:
            data = message.data

            # Handle different message types
            if isinstance(data, dict):
                if "type" in data:
                    message_type = data["type"]

                    if message_type == "order":
                        await self._handle_order(data)
                    elif message_type == "trade":
                        await self._handle_trade(data)
                    elif message_type == "ticks":
                        await self._handle_ticks(data)
                    elif message_type == "mode":
                        await self._handle_mode(data)
                    elif message_type == "full":
                        await self._handle_full(data)
                    else:
                        logger.debug(f"Unknown Kite message type: {message_type}")

                elif "a" in data and data.get("a") == "auth":
                    # Authentication response
                    logger.info(f"Kite authentication response: {data}")
                else:
                    logger.debug(f"Kite ticker data: {data}")

        except Exception as e:
            logger.error(f"Error processing Kite ticker message: {e}")

    async def _handle_ticks(self, data: dict[str, Any]) -> None:
        """Handle tick data."""
        try:
            ticks = data.get("ticks", [])
            for tick in ticks:
                instrument_token = tick.get("instrument_token")
                ltp = tick.get("last_price")
                volume = tick.get("volume")

                if instrument_token and ltp:
                    logger.debug(f"Tick: {instrument_token} | LTP: {ltp} | Volume: {volume}")
                    # Here you would typically update your data store
                    # or trigger trading logic

        except Exception as e:
            logger.error(f"Error handling ticks: {e}")

    async def _handle_order(self, data: dict[str, Any]) -> None:
        """Handle order updates."""
        logger.info(f"Order update: {data}")

    async def _handle_trade(self, data: dict[str, Any]) -> None:
        """Handle trade updates."""
        logger.info(f"Trade update: {data}")

    async def _handle_mode(self, data: dict[str, Any]) -> None:
        """Handle mode changes."""
        current_mode = data.get("current_mode")
        logger.info(f"Mode changed to: {current_mode}")

    async def _handle_full(self, data: dict[str, Any]) -> None:
        """Handle full market data."""
        instruments = data.get("instruments", [])
        logger.info(f"Full data for {len(instruments)} instruments")

    async def on_error(self, error: WebSocketError) -> None:
        """Called when an error occurs."""
        logger.error(f"Kite ticker error: {error.message}")

        # If error is recoverable, the client will handle reconnection
        if error.recoverable:
            logger.info("Waiting for automatic reconnection...")
        else:
            logger.error("Non-recoverable error, manual intervention required")

    async def on_reconnect(self, attempt: int, client: WebSocketClient) -> None:
        """Called when a reconnection attempt is made."""
        logger.info(f"Kite ticker reconnection attempt {attempt}")

    async def on_reconnect_success(self, client: WebSocketClient) -> None:
        """Called when reconnection succeeds."""
        logger.info("Kite ticker reconnection successful")

        # Re-authenticate after reconnection
        await self._authenticate(client)

        # Resubscribe to all previous subscriptions
        await self._resubscribe(client)

    async def _resubscribe(self, client: WebSocketClient) -> None:
        """Resubscribe to all instruments after reconnection."""
        if not self._subscriptions:
            return

        try:
            instruments = list(self._subscriptions.keys())
            subscribe_message = {"a": self._api_key, "v": "1.0", "t": "c", "i": instruments}

            await client.send(json.dumps(subscribe_message))
            logger.info(f"Resubscribed to {len(instruments)} instruments")

        except Exception as e:
            logger.error(f"Failed to resubscribe: {e}")

    async def subscribe(self, client: WebSocketClient, instrument_tokens: list[int]) -> bool:
        """Subscribe to specific instruments."""
        try:
            for token in instrument_tokens:
                self._subscriptions[token] = {"token": token, "subscribed_at": datetime.utcnow()}

            subscribe_message = {"a": self._api_key, "v": "1.0", "t": "s", "i": instrument_tokens}

            await client.send(json.dumps(subscribe_message))
            logger.info(f"Subscribed to {len(instrument_tokens)} instruments")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            return False

    async def unsubscribe(self, client: WebSocketClient, instrument_tokens: list[int]) -> bool:
        """Unsubscribe from specific instruments."""
        try:
            for token in instrument_tokens:
                if token in self._subscriptions:
                    del self._subscriptions[token]

            unsubscribe_message = {"a": self._api_key, "v": "1.0", "t": "u", "i": instrument_tokens}

            await client.send(json.dumps(unsubscribe_message))
            logger.info(f"Unsubscribed from {len(instrument_tokens)} instruments")
            return True

        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")
            return False

    @property
    def subscriptions(self) -> dict[int, dict[str, Any]]:
        """Get current subscriptions."""
        return self._subscriptions

    @property
    def stats(self) -> dict[str, Any]:
        """Get handler statistics."""
        return {
            "ticks_received": self._ticks_received,
            "last_tick_time": self._last_tick_time,
            "subscribed_instruments": len(self._subscriptions),
        }
