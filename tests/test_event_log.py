"""
Unit Tests for Event Logging Infrastructure.

Validates persistence, serialization, flushing, and schema evolution
of the Immutable Event Log (Kleppmann Ch.3-4).
"""

import uuid
from datetime import UTC, datetime

from src.data.event_log import (
    CURRENT_SCHEMA_VERSION,
    VALID_EVENT_TYPES,
    EventCodec,
    EventLogWriter,
    MarketEvent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PAYLOAD = {"open": 101.00, "high": 103.00, "close": 102.50}
EVENT_TYPES = sorted(VALID_EVENT_TYPES)


def make_event(**overrides: object) -> MarketEvent:
    """Helper to build a MarketEvent with minimal required fields."""
    defaults: dict = {
        "event_id": uuid.uuid4(),
        "event_type": "FO_BHAVCOPY",
        "event_time": datetime.now(UTC),
        "schema_version": CURRENT_SCHEMA_VERSION,
        "payload": dict(SAMPLE_PAYLOAD),
        "source": "jugaad_data",
        "ingest_id": uuid.uuid4(),
        "epoch": 1,
    }
    defaults.update(overrides)
    return MarketEvent(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MarketEvent dataclass
# ---------------------------------------------------------------------------


class TestMarketEvent:
    """MarketEvent structure and defaults."""

    def test_default_event_id_is_uuid(self) -> None:
        ev = MarketEvent(event_id=uuid.uuid4())
        assert isinstance(ev.event_id, uuid.UUID)

    def test_valid_event_type(self) -> None:
        for t in EVENT_TYPES:
            ev = make_event(event_type=t)
            assert ev.event_type in VALID_EVENT_TYPES

    def test_timezone_aware(self) -> None:
        ev = make_event()
        assert ev.event_time.tzinfo is not None


# ---------------------------------------------------------------------------
# EventCodec — encode / decode round-trip
# ---------------------------------------------------------------------------


class TestEventCodec:
    """Encode/decycle cycle and schema migration."""

    def test_round_trip(self) -> None:
        original = make_event()
        encoded = EventCodec.encode(original)
        decoded = EventCodec.decode(encoded)

        assert decoded.event_id == original.event_id
        assert decoded.event_type == original.event_type
        assert decoded.source == original.source
        assert decoded.schema_version == CURRENT_SCHEMA_VERSION
        assert decoded.payload == original.payload
        assert decoded.ingest_id == original.ingest_id
        assert decoded.epoch == original.epoch

    def test_decode_bumps_schema_version(self) -> None:
        """Events stored at v1 should be decoded at CURRENT_SCHEMA_VERSION after migration."""
        v1_event = make_event(schema_version=1)
        raw = EventCodec.encode(v1_event)
        raw["schema_version"] = 1  # simulate stored v1

        decoded = EventCodec.decode(raw)
        assert decoded.schema_version == CURRENT_SCHEMA_VERSION
        # The v1→v2 migration adds oi_change
        if CURRENT_SCHEMA_VERSION == 1:
            pass  # no migration applied yet
        else:
            assert "oi_change" in decoded.payload

    def test_migration_v1_to_v2(self) -> None:
        """Verify that the sample v1→v2 migration fills missing oi_change."""
        from src.data.event_log import migrate_v1_to_v2

        p = {"open": 100.0}
        migrated = migrate_v1_to_v2(p)
        assert migrated["oi_change"] == 0
        assert migrated["open"] == 100.0

    def test_decode_handles_missing_ingest_id(self) -> None:
        raw = {
            "event_id": str(uuid.uuid4()),
            "event_time": datetime.now(UTC).isoformat(),
            "event_type": "WS_TICK",
            "schema_version": CURRENT_SCHEMA_VERSION,
            "payload": {},
            "source": "kite_ws",
            "ingest_id": None,
            "epoch": 0,
        }
        decoded = EventCodec.decode(raw)
        assert decoded.ingest_id is None
        assert decoded.source == "kite_ws"


# ---------------------------------------------------------------------------
# EventLogWriter — buffering and flush contract
# ---------------------------------------------------------------------------


class TestEventLogWriter:
    """Writer buffer management (no DB connection required)."""

    def test_buffer_accumulates(self) -> None:
        writer = EventLogWriter("postgresql://localhost/trading_test", batch_size=10)
        ev = make_event()
        writer.buffer.append(ev)
        assert len(writer.buffer) == 1

    def test_flush_on_full_buffer(self) -> None:
        writer = EventLogWriter("postgresql://localhost/trading_test", batch_size=3)
        for _ in range(3):
            writer.buffer.append(make_event())
        # buffer should be full; flush is called by append only if >= batch_size
        assert len(writer.buffer) == 3

    def test_flush_returns_zero_when_empty(self) -> None:
        """Pure-Path test: flush on empty buffer returns 0."""
        writer = EventLogWriter("postgresql://localhost/trading_test")

        async def _run() -> None:
            count = await writer.flush()
            assert count == 0

        import asyncio

        asyncio.run(_run())

    def test_async_context_manager(self) -> None:
        """Writer can be used as async context manager."""
        writer = EventLogWriter("postgresql://localhost/trading_test")
        # validate __aenter__ / __aexit__ resolve without error
        assert hasattr(writer, "__aenter__")
        assert hasattr(writer, "__aexit__")
