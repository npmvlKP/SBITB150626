"""Tests for src/risk/audit.py."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

import pytest

from config.settings import AuditSettings
from src.risk.audit import (
    ALL_EVENT_TYPES,
    ORDER_PLACED,
    RISK_CHECK_FAILED,
    AuditLogger,
    NTPClock,
)


class TestAuditEvent:
    """Tests for AuditEvent creation and checksum."""

    @pytest.mark.asyncio
    async def test_audit_event_creation(self, audit_logger: AuditLogger) -> None:
        """log_event produces AuditEvent with all fields."""
        event = await audit_logger.log_event(
            event_type=ORDER_PLACED,
            source="test_module",
            details={"order_id": "test_123", "symbol": "NIFTY"},
        )
        assert event.event_id is not None
        assert isinstance(event.event_id, uuid.UUID)
        assert event.event_type == ORDER_PLACED
        assert event.source == "test_module"
        assert event.details["order_id"] == "test_123"
        assert event.checksum is not None
        assert event.timestamp is not None

    @pytest.mark.asyncio
    async def test_audit_event_checksum(self, audit_logger: AuditLogger) -> None:
        """Checksum is valid SHA-256 of event fields."""
        event = await audit_logger.log_event(
            event_type=RISK_CHECK_FAILED,
            source="test",
            details={"check": "symbol", "reason": "invalid"},
        )
        # Recompute checksum manually
        payload = (
            str(event.event_id)
            + event.timestamp.isoformat()
            + event.event_type
            + event.source
            + json.dumps(event.details, sort_keys=True)
        )
        expected = hashlib.sha256(payload.encode()).hexdigest()
        assert event.checksum == expected

    @pytest.mark.asyncio
    async def test_audit_event_timestamp_ist(self, audit_logger: AuditLogger) -> None:
        """Timestamp is timezone-aware (UTC)."""
        event = await audit_logger.log_event(
            event_type=ORDER_PLACED,
            source="test",
            details={},
        )
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.tzinfo == UTC

    @pytest.mark.asyncio
    async def test_audit_event_append_only(self, audit_logger: AuditLogger) -> None:
        """Events are stored sequentially."""
        await audit_logger.log_event(event_type=ORDER_PLACED, source="test", details={})
        event2 = await audit_logger.log_event(event_type=RISK_CHECK_FAILED, source="test", details={})
        events = await audit_logger.query_events()
        assert len(events) >= 2
        # Events are appended, check ordering
        assert events[-1].event_id == event2.event_id

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_valid(self, audit_logger: AuditLogger) -> None:
        """Fresh chain -> True."""
        await audit_logger.log_event(event_type=ORDER_PLACED, source="test", details={})
        result = await audit_logger.verify_chain_integrity()
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_tampered(self, audit_logger: AuditLogger) -> None:
        """Tampered event -> False."""
        await audit_logger.log_event(event_type=ORDER_PLACED, source="test", details={})
        # Tamper with stored event
        audit_logger._events[-1].event_type = "TAMPERED"
        result = await audit_logger.verify_chain_integrity()
        assert result is False


class TestAuditEventTypes:
    """Tests for event type constants."""

    def test_all_event_types_are_strings(self) -> None:
        """All defined event type constants are valid strings."""
        for et in ALL_EVENT_TYPES:
            assert isinstance(et, str)
            assert len(et) > 0

    def test_event_types_not_empty(self) -> None:
        """ALL_EVENT_TYPES is not empty."""
        assert len(ALL_EVENT_TYPES) > 0

    def test_expected_event_types_present(self) -> None:
        """Expected event types are all present."""
        expected = {
            "ORDER_PLACED",
            "ORDER_FILLED",
            "ORDER_REJECTED",
            "ORDER_CANCELLED",
            "KILL_SWITCH_ACTIVATED",
            "KILL_SWITCH_DEACTIVATED",
            "RISK_CHECK_PASSED",
            "RISK_CHECK_FAILED",
            "MARGIN_ALERT",
            "DAILY_LOSS_LIMIT",
            "SESSION_START",
            "SESSION_END",
            "DAILY_RECONCILIATION",
            "CONFIG_CHANGE",
            "STRATEGY_DEPLOYED",
            "STRATEGY_STOPPED",
        }
        assert expected.issubset(ALL_EVENT_TYPES)


class TestNTPClock:
    """Tests for NTPClock."""

    @pytest.mark.asyncio
    async def test_ntp_clock_returns_float(self) -> None:
        """NTPClock.check_offset returns float offset."""
        settings = AuditSettings()
        clock = NTPClock(settings)
        offset = await clock.check_offset()
        assert isinstance(offset, float)

    @pytest.mark.asyncio
    async def test_ntp_clock_get_time_returns_datetime(self) -> None:
        """NTPClock.get_time returns timezone-aware datetime."""
        settings = AuditSettings()
        clock = NTPClock(settings)
        t = await clock.get_time()
        assert isinstance(t, datetime)
        assert t.tzinfo is not None


class TestQueryEvents:
    """Tests for query_events()."""

    @pytest.mark.asyncio
    async def test_query_events_by_type(self, audit_logger: AuditLogger) -> None:
        """Query events filtered by type."""
        await audit_logger.log_event(event_type=ORDER_PLACED, source="test", details={})
        await audit_logger.log_event(event_type=RISK_CHECK_FAILED, source="test", details={})
        events = await audit_logger.query_events(event_type=ORDER_PLACED)
        for e in events:
            assert e.event_type == ORDER_PLACED

    @pytest.mark.asyncio
    async def test_query_events_limit(self, audit_logger: AuditLogger) -> None:
        """Query events respects limit."""
        for i in range(10):
            await audit_logger.log_event(event_type=ORDER_PLACED, source="test", details={"i": i})
        events = await audit_logger.query_events(limit=5)
        assert len(events) == 5
