"""
Unit tests for WebSocket Market Data Client module.
Comprehensive test coverage for:
- WebSocketClient base class
- NSEWebSocketClient
- MarketDataTick dataclass
- WebSocketMessage dataclass
- WebSocketStats dataclass
- Error handling
- Message parsing
- State management
Author: SBITB-150626
"""

from __future__ import annotations

import json
import unittest
import uuid
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from src.data.websocket import (
    DEFAULT_RECONNECT_DELAY,
    DEFAULT_WS_TIMEOUT,
    MAX_MESSAGE_SIZE,
    MAX_RECONNECT_ATTEMPTS,
    NSE_FNO_WS_URL,
    # Constants
    NSE_WS_URL,
    NSE_WS_V2_URL,
    PING_INTERVAL,
    PONG_TIMEOUT,
    AuthenticationError,
    ConnectionError,
    # Default Handler
    DefaultMarketDataHandler,
    # Abstract Base Classes
    MarketDataTick,
    MarketDataType,
    MessageParseError,
    NSEWebSocketClient,
    SubscriptionError,
    WebSocketClient,
    # Exceptions
    WebSocketError,
    # Manager
    WebSocketManager,
    # Dataclasses
    WebSocketMessage,
    # Type Definitions
    WebSocketMessageType,
    # Enums
    WebSocketState,
    WebSocketStats,
)

# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for Enums
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSocketState(unittest.TestCase):
    """Tests for WebSocketState enum."""

    def test_web_socket_state_values(self):
        """Test WebSocketState enum values."""
        self.assertEqual(WebSocketState.DISCONNECTED.value, "disconnected")
        self.assertEqual(WebSocketState.CONNECTING.value, "connecting")
        self.assertEqual(WebSocketState.CONNECTED.value, "connected")
        self.assertEqual(WebSocketState.RECONNECTING.value, "reconnecting")
        self.assertEqual(WebSocketState.ERROR.value, "error")
        self.assertEqual(WebSocketState.CLOSED.value, "closed")

    def test_web_socket_state_is_str_enum(self):
        """Test that WebSocketState is a StrEnum."""
        self.assertIsInstance(WebSocketState.DISCONNECTED, str)


class TestWebSocketMessageType(unittest.TestCase):
    """Tests for WebSocketMessageType enum."""

    def test_message_type_values(self):
        """Test WebSocketMessageType enum values."""
        self.assertEqual(WebSocketMessageType.TEXT.value, "text")
        self.assertEqual(WebSocketMessageType.BINARY.value, "binary")
        self.assertEqual(WebSocketMessageType.PING.value, "ping")
        self.assertEqual(WebSocketMessageType.PONG.value, "pong")
        self.assertEqual(WebSocketMessageType.CLOSE.value, "close")
        self.assertEqual(WebSocketMessageType.ERROR.value, "error")


class TestMarketDataType(unittest.TestCase):
    """Tests for MarketDataType enum."""

    def test_market_data_type_values(self):
        """Test MarketDataType enum values."""
        self.assertEqual(MarketDataType.TICK.value, "tick")
        self.assertEqual(MarketDataType.DEPTH.value, "depth")
        self.assertEqual(MarketDataType.INDEX.value, "index")
        self.assertEqual(MarketDataType.OPTION_CHAIN.value, "option_chain")
        self.assertEqual(MarketDataType.ORDER_BOOK.value, "order_book")
        self.assertEqual(MarketDataType.TRADE.value, "trade")
        self.assertEqual(MarketDataType.HEARTBEAT.value, "heartbeat")
        self.assertEqual(MarketDataType.SUBSCRIPTION_ACK.value, "subscription_ack")
        self.assertEqual(MarketDataType.SUBSCRIPTION_ERROR.value, "subscription_error")


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSocketError(unittest.TestCase):
    """Tests for WebSocketError exception."""

    def test_web_socket_error_creation(self):
        """Test WebSocketError creation."""
        error = WebSocketError("Test error")
        self.assertEqual(error.message, "Test error")
        self.assertIsNone(error.code)
        self.assertEqual(error.details, {})
        self.assertIsInstance(error.timestamp, datetime)

    def test_web_socket_error_with_code(self):
        """Test WebSocketError with code."""
        error = WebSocketError("Test error", code=1000)
        self.assertEqual(error.message, "Test error")
        self.assertEqual(error.code, 1000)

    def test_web_socket_error_with_details(self):
        """Test WebSocketError with details."""
        error = WebSocketError("Test error", code=1000, details={"key": "value"})
        self.assertEqual(error.details, {"key": "value"})

    def test_web_socket_error_to_dict(self):
        """Test WebSocketError to_dict method."""
        error = WebSocketError("Test error", code=1000, details={"key": "value"})
        result = error.to_dict()
        self.assertEqual(result["error"], "Test error")
        self.assertEqual(result["code"], 1000)
        self.assertEqual(result["details"], {"key": "value"})
        self.assertIn("timestamp", result)


class TestConnectionError(unittest.TestCase):
    """Tests for ConnectionError exception."""

    def test_connection_error_is_web_socket_error(self):
        """Test that ConnectionError is a WebSocketError."""
        error = ConnectionError("Connection failed")
        self.assertIsInstance(error, WebSocketError)
        self.assertIsInstance(error, Exception)


class TestAuthenticationError(unittest.TestCase):
    """Tests for AuthenticationError exception."""

    def test_authentication_error_is_web_socket_error(self):
        """Test that AuthenticationError is a WebSocketError."""
        error = AuthenticationError("Auth failed")
        self.assertIsInstance(error, WebSocketError)


class TestSubscriptionError(unittest.TestCase):
    """Tests for SubscriptionError exception."""

    def test_subscription_error_is_web_socket_error(self):
        """Test that SubscriptionError is a WebSocketError."""
        error = SubscriptionError("Subscription failed")
        self.assertIsInstance(error, WebSocketError)


class TestMessageParseError(unittest.TestCase):
    """Tests for MessageParseError exception."""

    def test_message_parse_error_is_web_socket_error(self):
        """Test that MessageParseError is a WebSocketError."""
        error = MessageParseError("Parse failed")
        self.assertIsInstance(error, WebSocketError)


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for Dataclasses
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSocketMessage(unittest.TestCase):
    """Tests for WebSocketMessage dataclass."""

    def test_default_creation(self):
        """Test default WebSocketMessage creation."""
        message = WebSocketMessage()
        self.assertIsInstance(message.message_id, uuid.UUID)
        self.assertEqual(message.message_type, WebSocketMessageType.TEXT)
        self.assertEqual(message.data, {})
        self.assertIsNone(message.raw_data)
        self.assertIsInstance(message.timestamp, datetime)
        self.assertEqual(message.source, "websocket")
        self.assertEqual(message.sequence_number, 0)

    def test_custom_creation(self):
        """Test WebSocketMessage with custom values."""
        message_id = uuid.uuid4()
        message = WebSocketMessage(
            message_id=message_id,
            message_type=WebSocketMessageType.BINARY,
            data={"key": "value"},
            raw_data=b"raw data",
            source="test",
            sequence_number=1,
        )
        self.assertEqual(message.message_id, message_id)
        self.assertEqual(message.message_type, WebSocketMessageType.BINARY)
        self.assertEqual(message.data, {"key": "value"})
        self.assertEqual(message.raw_data, b"raw data")
        self.assertEqual(message.source, "test")
        self.assertEqual(message.sequence_number, 1)

    def test_to_dict(self):
        """Test WebSocketMessage to_dict method."""
        message = WebSocketMessage(
            message_id=uuid.uuid4(),
            message_type=WebSocketMessageType.TEXT,
            data={"key": "value"},
            source="test",
            sequence_number=1,
        )
        result = message.to_dict()
        self.assertIn("message_id", result)
        self.assertEqual(result["message_type"], "text")
        self.assertEqual(result["data"], {"key": "value"})
        self.assertEqual(result["source"], "test")
        self.assertEqual(result["sequence_number"], 1)
        self.assertIn("timestamp", result)

    def test_from_json_valid(self):
        """Test WebSocketMessage from_json with valid JSON."""
        json_str = json.dumps(
            {
                "message_id": str(uuid.uuid4()),
                "message_type": "text",
                "data": {"key": "value"},
            }
        )
        message = WebSocketMessage.from_json(json_str)
        self.assertIsInstance(message, WebSocketMessage)
        self.assertEqual(message.message_type, WebSocketMessageType.TEXT)
        self.assertEqual(message.data, {"key": "value"})

    def test_from_json_invalid(self):
        """Test WebSocketMessage from_json with invalid JSON."""
        with self.assertRaises(MessageParseError):
            WebSocketMessage.from_json("invalid json")

    def test_from_json_with_missing_fields(self):
        """Test WebSocketMessage from_json with missing fields."""
        json_str = json.dumps({"data": {"key": "value"}})
        message = WebSocketMessage.from_json(json_str)
        self.assertIsInstance(message, WebSocketMessage)
        self.assertEqual(message.data, {"key": "value"})


class TestMarketDataTick(unittest.TestCase):
    """Tests for MarketDataTick dataclass."""

    def test_default_creation(self):
        """Test default MarketDataTick creation."""
        tick = MarketDataTick(symbol="TEST", ltp=100.0)
        self.assertEqual(tick.symbol, "TEST")
        self.assertEqual(tick.ltp, 100.0)
        self.assertEqual(tick.volume, 0.0)
        self.assertIsNone(tick.open)
        self.assertIsNone(tick.high)
        self.assertIsNone(tick.low)
        self.assertIsNone(tick.close)
        self.assertIsNone(tick.bid)
        self.assertIsNone(tick.ask)
        self.assertIsNone(tick.bid_qty)
        self.assertIsNone(tick.ask_qty)
        self.assertIsInstance(tick.timestamp, datetime)
        self.assertEqual(tick.exchange, "NSE")
        self.assertIsNone(tick.option_type)
        self.assertIsNone(tick.strike)
        self.assertIsNone(tick.expiry)
        self.assertIsNone(tick.iv)
        self.assertIsNone(tick.oi)
        self.assertIsNone(tick.change)
        self.assertIsNone(tick.pchange)

    def test_full_creation(self):
        """Test MarketDataTick with all fields."""
        timestamp = datetime(2024, 1, 1, 10, 0, 0)
        tick = MarketDataTick(
            symbol="NIFTY",
            ltp=20000.0,
            volume=1000.0,
            open=19900.0,
            high=20100.0,
            low=19800.0,
            close=19950.0,
            bid=19999.0,
            ask=20001.0,
            bid_qty=100.0,
            ask_qty=150.0,
            timestamp=timestamp,
            exchange="NSE",
            option_type="CE",
            strike=20000.0,
            expiry="2024-01-31",
            iv=0.25,
            oi=10000.0,
            change=100.0,
            pchange=0.5,
        )
        self.assertEqual(tick.symbol, "NIFTY")
        self.assertEqual(tick.ltp, 20000.0)
        self.assertEqual(tick.volume, 1000.0)
        self.assertEqual(tick.open, 19900.0)
        self.assertEqual(tick.high, 20100.0)
        self.assertEqual(tick.low, 19800.0)
        self.assertEqual(tick.close, 19950.0)
        self.assertEqual(tick.bid, 19999.0)
        self.assertEqual(tick.ask, 20001.0)
        self.assertEqual(tick.bid_qty, 100.0)
        self.assertEqual(tick.ask_qty, 150.0)
        self.assertEqual(tick.timestamp, timestamp)
        self.assertEqual(tick.exchange, "NSE")
        self.assertEqual(tick.option_type, "CE")
        self.assertEqual(tick.strike, 20000.0)
        self.assertEqual(tick.expiry, "2024-01-31")
        self.assertEqual(tick.iv, 0.25)
        self.assertEqual(tick.oi, 10000.0)
        self.assertEqual(tick.change, 100.0)
        self.assertEqual(tick.pchange, 0.5)

    def test_to_dict_minimal(self):
        """Test MarketDataTick to_dict with minimal fields."""
        tick = MarketDataTick(symbol="TEST", ltp=100.0)
        result = tick.to_dict()
        self.assertEqual(result["symbol"], "TEST")
        self.assertEqual(result["ltp"], 100.0)
        self.assertEqual(result["volume"], 0.0)
        self.assertEqual(result["exchange"], "NSE")
        self.assertIn("timestamp", result)
        self.assertNotIn("open", result)

    def test_to_dict_full(self):
        """Test MarketDataTick to_dict with all fields."""
        timestamp = datetime(2024, 1, 1, 10, 0, 0)
        tick = MarketDataTick(
            symbol="NIFTY",
            ltp=20000.0,
            volume=1000.0,
            open=19900.0,
            high=20100.0,
            low=19800.0,
            close=19950.0,
            bid=19999.0,
            ask=20001.0,
            bid_qty=100.0,
            ask_qty=150.0,
            timestamp=timestamp,
            exchange="NSE",
            option_type="CE",
            strike=20000.0,
            expiry="2024-01-31",
            iv=0.25,
            oi=10000.0,
            change=100.0,
            pchange=0.5,
        )
        result = tick.to_dict()
        self.assertEqual(result["symbol"], "NIFTY")
        self.assertEqual(result["ltp"], 20000.0)
        self.assertEqual(result["volume"], 1000.0)
        self.assertEqual(result["open"], 19900.0)
        self.assertEqual(result["high"], 20100.0)
        self.assertEqual(result["low"], 19800.0)
        self.assertEqual(result["close"], 19950.0)
        self.assertEqual(result["bid"], 19999.0)
        self.assertEqual(result["ask"], 20001.0)
        self.assertEqual(result["option_type"], "CE")
        self.assertEqual(result["strike"], 20000.0)
        self.assertEqual(result["iv"], 0.25)

    def test_from_dict(self):
        """Test MarketDataTick from_dict method."""
        data = {
            "symbol": "NIFTY",
            "ltp": 20000.0,
            "volume": 1000.0,
            "open": 19900.0,
            "high": 20100.0,
            "low": 19800.0,
            "close": 19950.0,
            "bid": 19999.0,
            "ask": 20001.0,
            "bid_qty": 100.0,
            "ask_qty": 150.0,
            "timestamp": "2024-01-01T10:00:00",
            "exchange": "NSE",
            "option_type": "CE",
            "strike": 20000.0,
            "expiry": "2024-01-31",
            "iv": 0.25,
            "oi": 10000.0,
            "change": 100.0,
            "pchange": 0.5,
        }
        tick = MarketDataTick.from_dict(data)
        self.assertEqual(tick.symbol, "NIFTY")
        self.assertEqual(tick.ltp, 20000.0)
        self.assertEqual(tick.volume, 1000.0)
        self.assertEqual(tick.open, 19900.0)
        self.assertEqual(tick.exchange, "NSE")
        self.assertEqual(tick.option_type, "CE")

    def test_from_websocket_message(self):
        """Test MarketDataTick from_websocket_message method."""
        data = {"symbol": "NIFTY", "ltp": 20000.0, "volume": 1000.0}
        message = WebSocketMessage(data=data)
        tick = MarketDataTick.from_websocket_message(message)
        self.assertEqual(tick.symbol, "NIFTY")
        self.assertEqual(tick.ltp, 20000.0)
        self.assertEqual(tick.volume, 1000.0)


class TestWebSocketStats(unittest.TestCase):
    """Tests for WebSocketStats dataclass."""

    def test_default_creation(self):
        """Test default WebSocketStats creation."""
        stats = WebSocketStats()
        self.assertEqual(stats.messages_received, 0)
        self.assertEqual(stats.messages_sent, 0)
        self.assertEqual(stats.bytes_received, 0)
        self.assertEqual(stats.bytes_sent, 0)
        self.assertEqual(stats.connection_attempts, 0)
        self.assertEqual(stats.successful_connections, 0)
        self.assertEqual(stats.errors, 0)
        self.assertEqual(stats.reconnects, 0)
        self.assertIsNone(stats.last_message_time)
        self.assertIsNone(stats.last_error_time)
        self.assertIsNone(stats.last_error)

    def test_custom_creation(self):
        """Test WebSocketStats with custom values."""
        last_message = datetime(2024, 1, 1, 10, 0, 0)
        last_error = datetime(2024, 1, 1, 11, 0, 0)
        stats = WebSocketStats(
            messages_received=100,
            messages_sent=50,
            bytes_received=1000,
            bytes_sent=500,
            connection_attempts=10,
            successful_connections=8,
            errors=2,
            reconnects=1,
            last_message_time=last_message,
            last_error_time=last_error,
            last_error="Test error",
        )
        self.assertEqual(stats.messages_received, 100)
        self.assertEqual(stats.messages_sent, 50)
        self.assertEqual(stats.bytes_received, 1000)
        self.assertEqual(stats.bytes_sent, 500)
        self.assertEqual(stats.connection_attempts, 10)
        self.assertEqual(stats.successful_connections, 8)
        self.assertEqual(stats.errors, 2)
        self.assertEqual(stats.reconnects, 1)
        self.assertEqual(stats.last_message_time, last_message)
        self.assertEqual(stats.last_error_time, last_error)
        self.assertEqual(stats.last_error, "Test error")

    def test_to_dict(self):
        """Test WebSocketStats to_dict method."""
        last_message = datetime(2024, 1, 1, 10, 0, 0)
        stats = WebSocketStats(
            messages_received=100,
            messages_sent=50,
            last_message_time=last_message,
            last_error="Test error",
        )
        result = stats.to_dict()
        self.assertEqual(result["messages_received"], 100)
        self.assertEqual(result["messages_sent"], 50)
        self.assertEqual(result["last_message_time"], "2024-01-01T10:00:00")
        self.assertEqual(result["last_error"], "Test error")
        self.assertIsNone(result["last_error_time"])


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants(unittest.TestCase):
    """Tests for module constants."""

    def test_timeout_constants(self):
        """Test timeout-related constants."""
        self.assertEqual(DEFAULT_WS_TIMEOUT, 30.0)
        self.assertEqual(DEFAULT_RECONNECT_DELAY, 5.0)
        self.assertEqual(MAX_RECONNECT_ATTEMPTS, 10)
        self.assertEqual(MAX_MESSAGE_SIZE, 2**22)
        self.assertEqual(PING_INTERVAL, 20.0)
        self.assertEqual(PONG_TIMEOUT, 10.0)

    def test_nse_urls(self):
        """Test NSE WebSocket URLs."""
        self.assertEqual(NSE_WS_URL, "wss://nsetoolsapi.vercel.app/ws")
        self.assertEqual(NSE_WS_V2_URL, "wss://nse-live-data.onrender.com/ws")
        self.assertEqual(NSE_FNO_WS_URL, "wss://nse-fno-data.onrender.com/ws")


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for WebSocketClient (Async)
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSocketClient(IsolatedAsyncioTestCase):
    """Tests for WebSocketClient class."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.mock_ws = MagicMock()
        self.mock_ws.send = AsyncMock()
        self.mock_ws.recv = AsyncMock()
        self.mock_ws.ping = AsyncMock()
        self.mock_ws.close = AsyncMock()
        self.mock_ws.ping_interval = PING_INTERVAL
        self.mock_ws.ping_timeout = PONG_TIMEOUT

    async def test_initialization(self):
        """Test WebSocketClient initialization."""
        client = WebSocketClient(url="wss://test.com")
        self.assertEqual(client.url, "wss://test.com")
        self.assertEqual(client.state, WebSocketState.DISCONNECTED)
        self.assertFalse(client.is_connected)
        self.assertIsNotNone(client.stats)

    async def test_initialization_with_handler(self):
        """Test WebSocketClient initialization with handler."""
        handler = DefaultMarketDataHandler()
        client = WebSocketClient(url="wss://test.com", handler=handler)
        self.assertIs(client._handler, handler)

    async def test_state_property(self):
        """Test state property."""
        client = WebSocketClient(url="wss://test.com")
        self.assertEqual(client.state, WebSocketState.DISCONNECTED)

    async def test_is_connected_property(self):
        """Test is_connected property."""
        client = WebSocketClient(url="wss://test.com")
        self.assertFalse(client.is_connected)

    async def test_stats_property(self):
        """Test stats property."""
        client = WebSocketClient(url="wss://test.com")
        self.assertIsInstance(client.stats, WebSocketStats)

    async def test_callback_registration(self):
        """Test callback registration methods."""
        client = WebSocketClient(url="wss://test.com")
        callback_connect = AsyncMock()
        callback_disconnect = AsyncMock()
        callback_message = AsyncMock()
        client.on_connect(callback_connect)
        client.on_disconnect(callback_disconnect)
        client.on_message(callback_message)
        self.assertIn(callback_connect, client._on_connect_callbacks)
        self.assertIn(callback_disconnect, client._on_disconnect_callbacks)
        self.assertIn(callback_message, client._on_message_callbacks)

    @patch("src.data.websocket.websockets")
    @patch("src.data.websocket.ssl")
    async def test_connect_success(self, mock_ssl, mock_websockets):
        """Test successful connection."""
        mock_ssl.create_default_context.return_value = MagicMock()
        mock_ws = AsyncMock()
        mock_ws.ping = AsyncMock()
        mock_websockets.connect = AsyncMock(return_value=mock_ws)
        client = WebSocketClient(url="wss://test.com")
        result = await client.connect()
        self.assertTrue(result)
        self.assertEqual(client.state, WebSocketState.CONNECTED)
        self.assertTrue(client.is_connected)
        mock_websockets.connect.assert_called_once()

    @patch("src.data.websocket.websockets")
    @patch("src.data.websocket.ssl")
    async def test_connect_timeout(self, mock_ssl, mock_websockets):
        """Test connection timeout."""
        mock_ssl.create_default_context.return_value = MagicMock()
        mock_websockets.connect = AsyncMock(side_effect=TimeoutError())
        client = WebSocketClient(url="wss://test.com", timeout=1.0)
        with patch("src.data.websocket.asyncio.wait_for", side_effect=TimeoutError()):
            result = await client.connect()
        self.assertFalse(result)
        self.assertEqual(client.state, WebSocketState.ERROR)

    @patch("src.data.websocket.websockets")
    @patch("src.data.websocket.ssl")
    async def test_connect_exception(self, mock_ssl, mock_websockets):
        """Test connection exception."""
        mock_ssl.create_default_context.return_value = MagicMock()
        mock_websockets.connect = AsyncMock(side_effect=Exception("Connection failed"))
        client = WebSocketClient(url="wss://test.com")
        with patch("src.data.websocket.websocket.asyncio.wait_for", side_effect=Exception("Connection failed")):
            result = await client.connect()
        self.assertFalse(result)
        self.assertEqual(client.state, WebSocketState.ERROR)

    @patch("src.data.websocket.websockets")
    @patch("src.data.websocket.ssl")
    async def test_disconnect_success(self, mock_ssl, mock_websockets):
        """Test successful disconnection."""
        mock_ssl.create_default_context.return_value = MagicMock()
        mock_ws = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_websockets.connect = AsyncMock(return_value=mock_ws)
        client = WebSocketClient(url="wss://test.com")
        await client.connect()
        result = await client.disconnect()
        self.assertTrue(result)
        self.assertEqual(client.state, WebSocketState.CLOSED)

    @patch("src.data.websocket.websockets")
    @patch("src.data.websocket.ssl")
    async def test_disconnect_not_connected(self, mock_ssl, mock_websockets):
        """Test disconnection when not connected."""
        client = WebSocketClient(url="wss://test.com")
        result = await client.disconnect()
        self.assertTrue(result)

    async def test_send_message_connected(self):
        """Test sending message when connected."""
        client = WebSocketClient(url="wss://test.com")
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()
        client._ws.send = AsyncMock()
        result = await client.send("test message")
        self.assertTrue(result)
        client._ws.send.assert_called_once_with("test message")

    async def test_send_message_dict(self):
        """Test sending dict message."""
        client = WebSocketClient(url="wss://test.com")
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()
        client._ws.send = AsyncMock()
        result = await client.send({"key": "value"})
        self.assertTrue(result)
        client._ws.send.assert_called_once()
        # Check that dict was converted to JSON
        args, _ = client._ws.send.call_args
        self.assertIsInstance(args[0], str)

    async def test_send_message_not_connected(self):
        """Test sending message when not connected."""
        client = WebSocketClient(url="wss://test.com")
        result = await client.send("test message")
        self.assertFalse(result)

    async def test_send_raw_success(self):
        """Test sending raw message."""
        client = WebSocketClient(url="wss://test.com")
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()
        client._ws.send = AsyncMock()
        result = await client.send_raw("raw message")
        self.assertTrue(result)

    async def test_send_raw_not_connected(self):
        """Test sending raw message when not connected."""
        client = WebSocketClient(url="wss://test.com")
        result = await client.send_raw("raw message")
        self.assertFalse(result)

    @patch("src.data.websocket.websockets")
    @patch("src.data.websocket.ssl")
    async def test_subscribe(self, mock_ssl, mock_websockets):
        """Test subscribe method."""
        mock_ssl.create_default_context.return_value = MagicMock()
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_websockets.connect = AsyncMock(return_value=mock_ws)
        client = WebSocketClient(url="wss://test.com")
        await client.connect()
        result = await client.subscribe(["NIFTY", "BANKNIFTY"], ["tick", "depth"])
        self.assertTrue(result)

    async def test_unsubscribe(self):
        """Test unsubscribe method."""
        client = WebSocketClient(url="wss://test.com")
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()
        client._ws.send = AsyncMock()
        result = await client.unsubscribe(["NIFTY", "BANKNIFTY"], ["tick", "depth"])
        self.assertTrue(result)

    async def test_process_received_message_text(self):
        """Test processing received text message."""
        client = WebSocketClient(url="wss://test.com")
        message = await client._process_received_message('{"key": "value"}')
        self.assertIsInstance(message, WebSocketMessage)
        self.assertEqual(message.message_type, WebSocketMessageType.TEXT)
        self.assertEqual(message.data, {"key": "value"})

    async def test_process_received_message_binary(self):
        """Test processing received binary message."""
        client = WebSocketClient(url="wss://test.com")
        message = await client._process_received_message(b"binary data")
        self.assertIsInstance(message, WebSocketMessage)
        self.assertEqual(message.message_type, WebSocketMessageType.BINARY)
        self.assertEqual(message.raw_data, b"binary data")

    async def test_process_received_message_plain_text(self):
        """Test processing received plain text message."""
        client = WebSocketClient(url="wss://test.com")
        message = await client._process_received_message("plain text")
        self.assertIsInstance(message, WebSocketMessage)
        self.assertEqual(message.message_type, WebSocketMessageType.TEXT)
        self.assertEqual(message.data, {"message": "plain text"})

    async def test_reconnect_success(self):
        """Test successful reconnection."""
        client = WebSocketClient(url="wss://test.com")
        client._state = WebSocketState.CONNECTED
        client._reconnect_attempts = 0
        with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            result = await client.reconnect()
        self.assertTrue(result)
        self.assertEqual(client._reconnect_attempts, 1)

    async def test_reconnect_max_attempts(self):
        """Test reconnection with max attempts reached."""
        client = WebSocketClient(url="wss://test.com", max_reconnect_attempts=3)
        client._reconnect_attempts = 3
        result = await client.reconnect()
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for NSEWebSocketClient
# ─────────────────────────────────────────────────────────────────────────────


class TestNSEWebSocketClient(IsolatedAsyncioTestCase):
    """Tests for NSEWebSocketClient class."""

    async def test_initialization(self):
        """Test NSEWebSocketClient initialization."""
        client = NSEWebSocketClient()
        self.assertEqual(client.url, NSE_WS_URL)
        self.assertEqual(client.subscribed_symbols, set())
        self.assertEqual(client.subscribed_data_types, set())

    async def test_initialization_with_custom_url(self):
        """Test NSEWebSocketClient with custom URL."""
        client = NSEWebSocketClient(url="wss://custom.com")
        self.assertEqual(client.url, "wss://custom.com")

    async def test_index_symbols(self):
        """Test NSE index symbol mappings."""
        client = NSEWebSocketClient()
        self.assertEqual(client.INDEX_SYMBOLS["NIFTY 50"], "NIFTY")
        self.assertEqual(client.INDEX_SYMBOLS["NIFTY BANK"], "BANKNIFTY")
        self.assertEqual(client.INDEX_SYMBOLS["NIFTY IT"], "NIFTYIT")

    async def test_default_symbols(self):
        """Test default NSE symbols."""
        client = NSEWebSocketClient()
        self.assertIn("NIFTY 50", client.DEFAULT_SYMBOLS)
        self.assertIn("NIFTY BANK", client.DEFAULT_SYMBOLS)
        self.assertIn("RELIANCE", client.DEFAULT_SYMBOLS)

    async def test_subscribe_nse_symbols(self):
        """Test subscribing to NSE symbols."""
        client = NSEWebSocketClient()
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()
        client._ws.send = AsyncMock()
        result = await client.subscribe_nse_symbols(["NIFTY 50", "RELIANCE"])
        self.assertTrue(result)
        self.assertIn("NIFTY", client.subscribed_symbols)
        self.assertIn("RELIANCE", client.subscribed_symbols)

    async def test_unsubscribe_nse_symbols(self):
        """Test unsubscribing from NSE symbols."""
        client = NSEWebSocketClient()
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()
        client._ws.send = AsyncMock()
        client._subscribed_symbols = {"NIFTY", "RELIANCE"}
        result = await client.unsubscribe_nse_symbols(["NIFTY 50"])
        self.assertTrue(result)
        self.assertNotIn("NIFTY", client.subscribed_symbols)

    async def test_subscribe_to_default_symbols(self):
        """Test subscribing to default symbols."""
        client = NSEWebSocketClient()
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()
        client._ws.send = AsyncMock()
        result = await client.subscribe_to_default_symbols()
        self.assertTrue(result)

    async def test_subscribe_to_option_chain(self):
        """Test subscribing to option chain."""
        client = NSEWebSocketClient()
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()
        client._ws.send = AsyncMock()
        result = await client.subscribe_to_option_chain("NIFTY")
        self.assertTrue(result)
        self.assertIn("NIFTY", client.subscribed_symbols)
        self.assertIn("option_chain", client.subscribed_data_types)

    async def test_process_nse_tick(self):
        """Test processing NSE tick message."""
        client = NSEWebSocketClient()
        handler = DefaultMarketDataHandler()
        client._handler = handler
        data = {
            "symbol": "NIFTY",
            "ltp": 20000.0,
            "volume": 1000.0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        message = WebSocketMessage(data=data)
        await client._process_message_with_handler(message)

    async def test_process_nse_depth(self):
        """Test processing NSE depth message."""
        client = NSEWebSocketClient()
        handler = DefaultMarketDataHandler()
        client._handler = handler
        data = {
            "symbol": "NIFTY",
            "bids": [[19999.0, 100.0]],
            "asks": [[20001.0, 150.0]],
        }
        message = WebSocketMessage(data=data)
        await client._process_message_with_handler(message)

    async def test_process_nse_index(self):
        """Test processing NSE index message."""
        client = NSEWebSocketClient()
        handler = DefaultMarketDataHandler()
        client._handler = handler
        data = {
            "symbol": "NIFTY",
            "value": 20000.0,
            "change": 100.0,
            "pchange": 0.5,
        }
        message = WebSocketMessage(data=data)
        await client._process_message_with_handler(message)

    async def test_process_nse_option_chain(self):
        """Test processing NSE option chain message."""
        client = NSEWebSocketClient()
        handler = DefaultMarketDataHandler()
        client._handler = handler
        data = {
            "symbol": "NIFTY",
            "expiry": "2024-01-31",
            "strikes": {"20000": {"CE": 100.0, "PE": 50.0}},
        }
        message = WebSocketMessage(data=data)
        await client._process_message_with_handler(message)


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for DefaultMarketDataHandler
# ─────────────────────────────────────────────────────────────────────────────


class TestDefaultMarketDataHandler(IsolatedAsyncioTestCase):
    """Tests for DefaultMarketDataHandler class."""

    async def test_initialization(self):
        """Test DefaultMarketDataHandler initialization."""
        handler = DefaultMarketDataHandler()
        self.assertIsNotNone(handler._tick_callbacks)
        self.assertIsNotNone(handler._depth_callbacks)
        self.assertIsNotNone(handler._index_callbacks)
        self.assertIsNotNone(handler._option_chain_callbacks)
        self.assertIsNotNone(handler._error_callbacks)
        self.assertIsNotNone(handler._state_callbacks)

    async def test_on_tick(self):
        """Test on_tick method."""
        handler = DefaultMarketDataHandler()
        tick = MarketDataTick(symbol="NIFTY", ltp=20000.0)
        await handler.on_tick(tick)

    async def test_on_depth(self):
        """Test on_depth method."""
        handler = DefaultMarketDataHandler()
        await handler.on_depth("NIFTY", [[19999.0, 100.0]], [[20001.0, 150.0]])

    async def test_on_index(self):
        """Test on_index method."""
        handler = DefaultMarketDataHandler()
        await handler.on_index("NIFTY", 20000.0, 100.0, 0.5)

    async def test_on_option_chain(self):
        """Test on_option_chain method."""
        handler = DefaultMarketDataHandler()
        await handler.on_option_chain("NIFTY", "2024-01-31", {"20000": {"CE": 100.0}})

    async def test_on_error(self):
        """Test on_error method."""
        handler = DefaultMarketDataHandler()
        error = WebSocketError("Test error")
        await handler.on_error(error)

    async def test_on_connection_state_change(self):
        """Test on_connection_state_change method."""
        handler = DefaultMarketDataHandler()
        await handler.on_connection_state_change(WebSocketState.CONNECTED)

    async def test_callback_registration(self):
        """Test callback registration."""
        handler = DefaultMarketDataHandler()
        callback_tick = AsyncMock()
        callback_depth = AsyncMock()
        callback_index = AsyncMock()
        callback_option_chain = AsyncMock()
        callback_error = AsyncMock()
        callback_state = AsyncMock()
        handler.on_tick(callback_tick)
        handler.on_depth(callback_depth)
        handler.on_index(callback_index)
        handler.on_option_chain(callback_option_chain)
        handler.on_error(callback_error)
        handler.on_connection_state_change(callback_state)
        self.assertIn(callback_tick, handler._tick_callbacks)
        self.assertIn(callback_depth, handler._depth_callbacks)
        self.assertIn(callback_index, handler._index_callbacks)
        self.assertIn(callback_option_chain, handler._option_chain_callbacks)
        self.assertIn(callback_error, handler._error_callbacks)
        self.assertIn(callback_state, handler._state_callbacks)


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases for WebSocketManager
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSocketManager(IsolatedAsyncioTestCase):
    """Tests for WebSocketManager class."""

    async def test_singleton(self):
        """Test WebSocketManager singleton pattern."""
        manager1 = await WebSocketManager.get_instance()
        manager2 = await WebSocketManager.get_instance()
        self.assertIs(manager1, manager2)

    async def test_start_stop(self):
        """Test start and stop methods."""
        manager = await WebSocketManager.get_instance()
        await manager.start()
        self.assertTrue(manager.is_running)
        await manager.stop()
        self.assertFalse(manager.is_running)

    async def test_add_client(self):
        """Test add_client method."""
        manager = await WebSocketManager.get_instance()
        client = WebSocketClient(url="wss://test.com")
        result = await manager.add_client("test", client)
        self.assertTrue(result)
        self.assertIn("test", manager.clients)

    async def test_add_client_duplicate(self):
        """Test adding duplicate client."""
        manager = await WebSocketManager.get_instance()
        client = WebSocketClient(url="wss://test.com")
        await manager.add_client("test", client)
        result = await manager.add_client("test", client)
        self.assertFalse(result)

    async def test_remove_client(self):
        """Test remove_client method."""
        manager = await WebSocketManager.get_instance()
        client = WebSocketClient(url="wss://test.com")
        await manager.add_client("test", client)
        result = await manager.remove_client("test")
        self.assertTrue(result)
        self.assertNotIn("test", manager.clients)

    async def test_remove_client_nonexistent(self):
        """Test removing nonexistent client."""
        manager = await WebSocketManager.get_instance()
        result = await manager.remove_client("nonexistent")
        self.assertFalse(result)

    async def test_get_client(self):
        """Test get_client method."""
        manager = await WebSocketManager.get_instance()
        client = WebSocketClient(url="wss://test.com")
        await manager.add_client("test", client)
        retrieved = await manager.get_client("test")
        self.assertIs(retrieved, client)

    async def test_get_client_nonexistent(self):
        """Test getting nonexistent client."""
        manager = await WebSocketManager.get_instance()
        result = await manager.get_client("nonexistent")
        self.assertIsNone(result)

    async def test_clients_property(self):
        """Test clients property."""
        manager = await WebSocketManager.get_instance()
        client = WebSocketClient(url="wss://test.com")
        await manager.add_client("test", client)
        clients = manager.clients
        self.assertIn("test", clients)


# ─────────────────────────────────────────────────────────────────────────────
# Module Level Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleExports(unittest.TestCase):
    """Tests for module exports."""

    def test_all_exports(self):
        """Test that all expected classes are exported."""
        from src.data import websocket

        expected_exports = [
            # Enums
            "WebSocketState",
            "WebSocketMessageType",
            "MarketDataType",
            # Exceptions
            "WebSocketError",
            "ConnectionError",
            "AuthenticationError",
            "SubscriptionError",
            "MessageParseError",
            # Dataclasses
            "WebSocketMessage",
            "MarketDataTick",
            "WebSocketStats",
            # Type Definitions
            "WebSocketMessageData",
            "SubscriptionRequest",
            # Abstract Base Classes
            "MarketDataHandler",
            "SubscriptionManager",
            # Client Classes
            "WebSocketClient",
            "NSEWebSocketClient",
            # Default Handler
            "DefaultMarketDataHandler",
            # Manager
            "WebSocketManager",
            # Constants
            "NSE_WS_URL",
            "NSE_WS_V2_URL",
            "NSE_FNO_WS_URL",
            "DEFAULT_WS_TIMEOUT",
            "DEFAULT_RECONNECT_DELAY",
            "MAX_RECONNECT_ATTEMPTS",
            "MAX_MESSAGE_SIZE",
            "PING_INTERVAL",
            "PONG_TIMEOUT",
        ]
        for export in expected_exports:
            self.assertTrue(hasattr(websocket, export), f"Missing export: {export}")


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestWebSocketIntegration(IsolatedAsyncioTestCase):
    """Integration tests for WebSocket functionality."""

    async def test_message_flow(self):
        """Test complete message flow from receive to handler."""
        client = WebSocketClient(url="wss://test.com")
        handler = DefaultMarketDataHandler()
        client._handler = handler
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()

        # Mock receive to return a test message
        async def mock_recv():
            return '{"type": "tick", "symbol": "NIFTY", "ltp": 20000.0, "volume": 1000.0}'

        client._ws.recv = mock_recv

        # Process the message
        message = await client.receive()
        self.assertIsNotNone(message)
        self.assertEqual(message.data["symbol"], "NIFTY")

    async def test_error_handling(self):
        """Test error handling in message processing."""
        client = WebSocketClient(url="wss://test.com")
        handler = DefaultMarketDataHandler()
        client._handler = handler
        client._state = WebSocketState.CONNECTED
        client._ws = AsyncMock()

        # Mock receive to raise an exception
        async def mock_recv():
            raise Exception("Test error")

        client._ws.recv = mock_recv

        # This should handle the error gracefully
        message = await client.receive()
        self.assertIsNone(message)


if __name__ == "__main__":
    unittest.main()
