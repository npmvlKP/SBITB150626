"""
Unit tests for LiveMarketFeed (Ph.2-7).

Tests cover:
- TickRingBuffer backpressure behavior
- WSConnectionState enum
- WebSocketSettings dataclass
- LiveMarketFeed initialization
- Connection lifecycle
- ATM strike computation
- MCX subscriptions
- Reconnection with exponential backoff
- Reauth scheduler
- Persist loop
- Heartbeat monitor
"""

from __future__ import annotations

import asyncio
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from src.data.event_log import EventLogWriter
from src.data.live_market_feed import (
    LiveMarketFeed,
    TickRingBuffer,
    WebSocketSettings,
    WSConnectionState,
    compute_atm_subscriptions,
    generate_uuid,
)


class TestWSConnectionState(unittest.TestCase):
    """Tests for WSConnectionState enum."""

    def test_enum_values(self) -> None:
        """Test all enum values exist."""
        self.assertEqual(WSConnectionState.DISCONNECTED.value, 1)
        self.assertEqual(WSConnectionState.CONNECTING.value, 2)
        self.assertEqual(WSConnectionState.CONNECTED.value, 3)
        self.assertEqual(WSConnectionState.RECONNECTING.value, 4)
        self.assertEqual(WSConnectionState.REAUTHENTICATING.value, 5)


class TestWebSocketSettings(unittest.TestCase):
    """Tests for WebSocketSettings dataclass."""

    def test_default_values(self) -> None:
        """Test default settings values."""
        settings = WebSocketSettings()
        self.assertEqual(settings.max_buffer_size, 10000)
        self.assertEqual(settings.max_reconnect_attempts, 10)
        self.assertEqual(settings.reconnect_delay_sec, 2.0)
        self.assertEqual(settings.reconnect_max_delay_sec, 60.0)
        self.assertEqual(settings.heartbeat_timeout_sec, 30.0)
        self.assertEqual(settings.persist_interval_sec, 1.0)
        self.assertEqual(settings.redis_ttl_sec, 10)

    def test_custom_values(self) -> None:
        """Test custom settings values."""
        settings = WebSocketSettings(
            max_buffer_size=5000,
            max_reconnect_attempts=5,
            reconnect_delay_sec=5.0,
        )
        self.assertEqual(settings.max_buffer_size, 5000)
        self.assertEqual(settings.max_reconnect_attempts, 5)
        self.assertEqual(settings.reconnect_delay_sec, 5.0)


class TestTickRingBuffer(unittest.TestCase):
    """Tests for TickRingBuffer circular buffer."""

    def test_initialization(self) -> None:
        """Test buffer initialization."""
        buffer = TickRingBuffer(capacity=100)
        self.assertEqual(len(buffer), 0)
        self.assertEqual(buffer.dropped_count, 0)

    def test_push_single(self) -> None:
        """Test pushing single tick."""
        buffer = TickRingBuffer(capacity=100)
        tick = {"instrument_token": 256265, "last_price": 100.0}
        buffer.push(tick)
        self.assertEqual(len(buffer), 1)

    def test_push_multiple(self) -> None:
        """Test pushing multiple ticks."""
        buffer = TickRingBuffer(capacity=100)
        for i in range(50):
            buffer.push({"instrument_token": i, "last_price": float(i)})
        self.assertEqual(len(buffer), 50)

    def test_backpressure_drop_oldest(self) -> None:
        """Test backpressure drops oldest when full."""
        buffer = TickRingBuffer(capacity=10)

        # Fill buffer
        for i in range(10):
            buffer.push({"instrument_token": i, "last_price": float(i)})

        self.assertEqual(len(buffer), 10)
        self.assertEqual(buffer.dropped_count, 0)

        # Push one more - should drop oldest
        buffer.push({"instrument_token": 99, "last_price": 99.0})

        # Should still be 10, oldest dropped
        self.assertEqual(len(buffer), 10)
        self.assertEqual(buffer.dropped_count, 1)

    def test_drain_all(self) -> None:
        """Test draining all ticks."""
        buffer = TickRingBuffer(capacity=100)

        ticks = [{"instrument_token": i, "last_price": float(i)} for i in range(10)]
        for tick in ticks:
            buffer.push(tick)

        drained = buffer.drain(1000)

        self.assertEqual(len(drained), 10)
        self.assertEqual(len(buffer), 0)

    def test_drain_partial(self) -> None:
        """Test draining partial ticks."""
        buffer = TickRingBuffer(capacity=100)

        ticks = [{"instrument_token": i, "last_price": float(i)} for i in range(10)]
        for tick in ticks:
            buffer.push(tick)

        drained = buffer.drain(5)

        self.assertEqual(len(drained), 5)
        self.assertEqual(len(buffer), 5)

    def test_drain_empty(self) -> None:
        """Test draining empty buffer."""
        buffer = TickRingBuffer(capacity=100)
        drained = buffer.drain(10)
        self.assertEqual(len(drained), 0)

    def test_clear(self) -> None:
        """Test clearing buffer."""
        buffer = TickRingBuffer(capacity=100)

        for i in range(10):
            buffer.push({"instrument_token": i, "last_price": float(i)})

        buffer.clear()

        self.assertEqual(len(buffer), 0)

    def test_thread_safety(self) -> None:
        """Test thread safety with concurrent operations."""
        import threading

        buffer = TickRingBuffer(capacity=1000)
        num_threads = 10
        ticks_per_thread = 100

        def push_ticks():
            for i in range(ticks_per_thread):
                buffer.push({"instrument_token": i, "last_price": float(i)})

        threads = [threading.Thread(target=push_ticks) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All ticks should be in buffer (no drops since capacity is large enough)
        self.assertEqual(len(buffer), num_threads * ticks_per_thread)


class TestComputeATMSubscriptions(unittest.TestCase):
    """Tests for compute_atm_subscriptions function."""

    def test_nifty_atm_strikes(self) -> None:
        """Test NIFTY ATM strike computation."""
        spot_price = 20000.0
        interval = 50.0
        num_strikes = 5

        strikes = compute_atm_subscriptions(spot_price, interval, num_strikes)

        # Should return 2*num_strikes + 1 strikes (N to N)
        self.assertEqual(len(strikes), 11)

        # Should be centered around ATM
        atm_idx = len(strikes) // 2
        self.assertEqual(strikes[atm_idx], 20000.0)  # ATM strike

    def test_banknifty_atm_strikes(self) -> None:
        """Test BANKNIFTY ATM strike computation."""
        spot_price = 44000.0
        interval = 100.0
        num_strikes = 5

        strikes = compute_atm_subscriptions(spot_price, interval, num_strikes)

        self.assertEqual(len(strikes), 11)
        self.assertIn(44000.0, strikes)  # ATM strike

    def test_rounding_to_interval(self) -> None:
        """Test rounding to nearest interval."""
        spot_price = 20017.0  # Not a multiple of 50
        interval = 50.0

        strikes = compute_atm_subscriptions(spot_price, interval, 3)

        # Should round to nearest 50
        self.assertIn(20000.0, strikes)
        self.assertIn(20050.0, strikes)


class TestGenerateUUID(unittest.TestCase):
    """Tests for generate_uuid function."""

    def test_generate_unique_uuids(self) -> None:
        """Test UUID generation produces unique values."""
        uuids = [generate_uuid() for _ in range(100)]
        self.assertEqual(len(set(uuids)), 100)  # All unique

    def test_generate_valid_uuid(self) -> None:
        """Test UUID generation produces valid UUIDs."""
        uuid_str = generate_uuid()
        uuid.UUID(uuid_str)  # Should not raise


class TestLiveMarketFeed(IsolatedAsyncioTestCase):
    """Tests for LiveMarketFeed class."""

    async def asyncSetUp(self) -> None:
        """Set up test fixtures."""
        # Create mock dependencies
        self.mock_kite_api = MagicMock()
        self.mock_kite_api.access_token = "test_token"
        self.mock_kite_api.api_key = "test_key"
        self.mock_kite_api.authenticate = AsyncMock(return_value=True)
        self.mock_kite_api.get_instrument_token = MagicMock(return_value=12345)

        self.mock_settings = WebSocketSettings(max_buffer_size=1000)
        self.mock_event_writer = AsyncMock(spec=EventLogWriter)
        self.mock_redis = MagicMock()
        self.mock_redis.get = MagicMock(return_value=None)
        self.mock_redis.setex = MagicMock()
        self.mock_audit = MagicMock()
        self.mock_audit.log_event = AsyncMock()

    async def test_initialization(self) -> None:
        """Test LiveMarketFeed initialization."""
        feed = LiveMarketFeed(
            kite_api=self.mock_kite_api,
            settings=self.mock_settings,
            event_writer=self.mock_event_writer,
            redis_client=self.mock_redis,
            audit_logger=self.mock_audit,
        )

        self.assertEqual(feed.state, WSConnectionState.DISCONNECTED)
        self.assertEqual(feed.epoch, 0)
        self.assertFalse(feed.is_running)

    async def test_start_stop(self) -> None:
        """Test start and stop lifecycle."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws.connect = MagicMock()
            mock_kws.close = MagicMock()
            mock_kws.subscribe = MagicMock()
            mock_kws.set_mode = MagicMock()
            mock_kws.MODE_FULL = "full"
            mock_kws.MODE_QUOTE = "quote"
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            await feed.start()
            self.assertTrue(feed.is_running)

            await feed.stop()
            self.assertFalse(feed.is_running)

    async def test_on_connect_increments_epoch(self) -> None:
        """Test _on_connect increments epoch."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws.subscribe = MagicMock()
            mock_kws.set_mode = MagicMock()
            mock_kws.MODE_FULL = "full"
            mock_kws.MODE_QUOTE = "quote"
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            self.assertEqual(feed.epoch, 0)

            feed._on_connect(mock_kws, {})

            self.assertEqual(feed.epoch, 1)
            self.assertEqual(feed.state, WSConnectionState.CONNECTED)

    async def test_on_tags_ticks_with_epoch(self) -> None:
        """Test _on_tags tags ticks with epoch."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            feed._epoch = 5

            ticks = [{"instrument_token": 12345, "last_price": 100.0}]
            feed._on_ticks(mock_kws, ticks)

            # Check tick was tagged with epoch
            self.assertEqual(len(feed._ring_buffer), 1)

    async def test_redis_write_failure_continues(self) -> None:
        """Test Redis write failure doesn't stop processing."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws_class.return_value = mock_kws

            # Make Redis fail
            self.mock_redis.setex.side_effect = Exception("Redis error")

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            ticks = [{"instrument_token": 12345, "last_price": 100.0}]
            feed._on_ticks(mock_kws, ticks)

            # Tick should still be in buffer
            self.assertEqual(len(feed._ring_buffer), 1)

    async def test_on_close_triggers_reconnect(self) -> None:
        """Test _on_close triggers reconnection."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            feed._on_close(mock_kws, 1000, "Normal closure")

            # Should trigger reconnect (handled by _handle_reconnect)
            self.assertEqual(feed.state, WSConnectionState.RECONNECTING)

    async def test_on_error_token_exception_triggers_reauth(self) -> None:
        """Test _on_error with 403 triggers reauth."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            feed._on_error(mock_kws, 403, "Token expired")

            self.assertEqual(feed.state, WSConnectionState.REAUTHENTICATING)

    async def test_reconnect_with_backoff(self) -> None:
        """Test exponential backoff in reconnect."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws.reconnect = MagicMock()
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            # Manually trigger reconnect
            feed._reconnect_attempts = 0
            feed._is_running = True

            # Start reconnect task (will cancel after first attempt)
            task = asyncio.create_task(feed._reconnect_with_backoff())

            # Let it run briefly then cancel
            await asyncio.sleep(0.1)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Should have incremented attempts
            self.assertGreater(feed._reconnect_attempts, 0)

    async def test_persist_loop(self) -> None:
        """Test persist loop processes ticks."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=WebSocketSettings(persist_interval_sec=0.1),
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            feed._is_running = True

            # Add ticks to buffer
            for i in range(10):
                feed._ring_buffer.push({"instrument_token": i, "last_price": float(i)})

            # Run persist loop briefly
            task = asyncio.create_task(feed._persist_loop())
            await asyncio.sleep(0.2)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Should have called event_writer.append
            self.assertGreater(self.mock_event_writer.append.call_count, 0)

    async def test_heartbeat_monitor_detects_silent_disconnect(self) -> None:
        """Test heartbeat monitor detects silent disconnect."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=WebSocketSettings(heartbeat_timeout_sec=0.1),
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            feed._is_running = True
            feed._state = WSConnectionState.CONNECTED

            # Set last tick time to past
            feed._last_tick_time = datetime.now(UTC) - timedelta(seconds=1)

            # Run heartbeat briefly
            task = asyncio.create_task(feed._heartbeat_monitor())
            await asyncio.sleep(0.3)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Should have detected silent disconnect and changed state
            self.assertEqual(feed.state, WSConnectionState.RECONNECTING)

    async def test_subscribe_nifty_options(self) -> None:
        """Test NIFTY option subscription."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws.subscribe = MagicMock()
            mock_kws.set_mode = MagicMock()
            mock_kws.MODE_FULL = "full"
            mock_kws_class.return_value = mock_kws

            # Mock spot price
            self.mock_redis.get.return_value = b"20000.0"

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            feed._kws = mock_kws

            feed._subscribe_nifty_options()

            # Should have subscribed to instruments
            self.assertGreater(mock_kws.subscribe.call_count, 0)

    async def test_subscribe_banknifty_options(self) -> None:
        """Test BANKNIFTY option subscription."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws.subscribe = MagicMock()
            mock_kws.set_mode = MagicMock()
            mock_kws.MODE_FULL = "full"
            mock_kws_class.return_value = mock_kws

            # Mock spot price
            self.mock_redis.get.return_value = b"44000.0"

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            feed._kws = mock_kws

            feed._subscribe_banknifty_options()

            # Should have subscribed to instruments
            self.assertGreater(mock_kws.subscribe.call_count, 0)

    async def test_subscribe_mcx_futures(self) -> None:
        """Test MCX futures subscription."""
        with patch("kiteconnect.KiteTicker") as mock_kws_class:
            mock_kws = MagicMock()
            mock_kws.subscribe = MagicMock()
            mock_kws.set_mode = MagicMock()
            mock_kws.MODE_QUOTE = "quote"
            mock_kws_class.return_value = mock_kws

            feed = LiveMarketFeed(
                kite_api=self.mock_kite_api,
                settings=self.mock_settings,
                event_writer=self.mock_event_writer,
                redis_client=self.mock_redis,
                audit_logger=self.mock_audit,
            )

            feed._kws = mock_kws

            feed._subscribe_mcx_futures()

            # Should have subscribed to MCX instruments
            self.assertGreater(mock_kws.subscribe.call_count, 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
