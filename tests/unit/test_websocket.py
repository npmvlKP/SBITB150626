"""
Unit tests for WebSocket constants from live_market_feed module.

Tests the reconnection and tick persistence constants used by the
live market feed WebSocket client per Kleppmann Ch.5 resilience patterns.

Author: SBITB-150626
"""

from __future__ import annotations

from src.data.live_market_feed import (
    BANKNIFTY_STRIKE_INTERVAL,
    HEARTBEAT_TIMEOUT_SEC,
    NIFTY_STRIKE_INTERVAL,
    PERSIST_INTERVAL_SEC,
    RECONNECT_BACKOFF_FACTOR,
    RECONNECT_INITIAL_DELAY_SEC,
    RECONNECT_MAX_ATTEMPTS,
    RECONNECT_MAX_DELAY_SEC,
    REDIS_TTL_SEC,
)

# ─────────────────────────────────────────────────────────────────────────────
# Test Reconnection Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestReconnectConstants:
    """Tests for reconnection timing constants."""

    def test_initial_delay_positive(self):
        """Initial reconnect delay should be positive."""
        assert RECONNECT_INITIAL_DELAY_SEC > 0

    def test_max_delay_positive(self):
        """Maximum reconnect delay should be positive."""
        assert RECONNECT_MAX_DELAY_SEC > 0

    def test_max_delay_greater_than_initial(self):
        """Max delay should be greater than initial delay."""
        assert RECONNECT_MAX_DELAY_SEC > RECONNECT_INITIAL_DELAY_SEC

    def test_backoff_factor_greater_than_one(self):
        """Backoff factor should be >= 1 for exponential backoff."""
        assert RECONNECT_BACKOFF_FACTOR >= 1.0

    def test_max_attempts_positive(self):
        """Max reconnect attempts should be positive."""
        assert RECONNECT_MAX_ATTEMPTS > 0

    def test_backoff_sequence_values(self):
        """Verify expected backoff sequence values."""
        # First few delays: 2, 4, 8, 16, 32, 60(capped)
        delays = []
        delay = RECONNECT_INITIAL_DELAY_SEC
        for _ in range(10):
            delays.append(delay)
            delay = min(
                delay * RECONNECT_BACKOFF_FACTOR,
                RECONNECT_MAX_DELAY_SEC,
            )

        # Check exponential growth
        assert delays[0] == RECONNECT_INITIAL_DELAY_SEC
        assert delays[1] == RECONNECT_INITIAL_DELAY_SEC * RECONNECT_BACKOFF_FACTOR
        # Check cap at max
        for d in delays:
            assert d <= RECONNECT_MAX_DELAY_SEC


# ─────────────────────────────────────────────────────────────────────────────
# Test Persistence Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestPersistenceConstants:
    """Tests for tick persistence timing constants."""

    def test_persist_interval_positive(self):
        """Persist interval should be positive."""
        assert PERSIST_INTERVAL_SEC > 0

    def test_heartbeat_timeout_positive(self):
        """Heartbeat timeout should be positive."""
        assert HEARTBEAT_TIMEOUT_SEC > 0

    def test_redis_ttl_positive(self):
        """Redis TTL should be positive."""
        assert REDIS_TTL_SEC > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test Strike Interval Constants
# ─────────────────────────────────────────────────────────────────────────────


class TestStrikeIntervalConstants:
    """Tests for option strike interval constants."""

    def test_nifty_interval_positive(self):
        """NIFTY strike interval should be positive."""
        assert NIFTY_STRIKE_INTERVAL > 0

    def test_banknifty_interval_positive(self):
        """BANKNIFTY strike interval should be positive."""
        assert BANKNIFTY_STRIKE_INTERVAL > 0

    def test_banknifty_greater_than_nifty(self):
        """BANKNIFTY interval typically greater than NIFTY."""
        assert BANKNIFTY_STRIKE_INTERVAL > NIFTY_STRIKE_INTERVAL
