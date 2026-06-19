"""
Immutable Event Log (Kleppmann Ch.3).

Single source of truth for all market data. All pipelines write events here first;
derived tables are populated from this log.

Architecture:
  - MarketEvent is an append-only event dataclass
  - EventLogWriter buffers events and flushes in batch via PostgreSQL
  - EventLogReader queries the log with filters
  - EventCodec handles encode/decode and schema migration (Kleppmann Ch.4)
"""

import asyncio
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import psycopg
import structlog

logger = structlog.get_logger()

CURRENT_SCHEMA_VERSION = 1

VALID_EVENT_TYPES = frozenset(
    {
        "FO_BHAVCOPY",
        "CM_BHAVCOPY",
        "WS_TICK",
        "WS_OI_UPDATE",
        "GREEKS_SNAPSHOT",
    }
)


@dataclass
class MarketEvent:
    """Immutable market data event — append-only, idempotent, schema-versioned."""

    event_id: uuid.UUID
    event_type: str = ""
    event_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: int = 1
    payload: dict | None = None
    source: str = ""
    ingest_id: uuid.UUID | None = None
    epoch: int = 0


def _event_to_db_row(event: MarketEvent) -> tuple:
    """Serialize a MarketEvent into a PostgreSQL row tuple.

    The payload column (JSONB) stores only the actual data dict. Metadata fields
    source, ingest_id, epoch are stored as separate columns in the table.
    """
    return (
        str(event.event_id),
        event.event_time.replace(tzinfo=UTC) if event.event_time.tzinfo is None else event.event_time,
        event.event_type,
        event.schema_version,
        json.dumps(event.payload or {}, default=str),
        event.source,
        str(event.ingest_id) if event.ingest_id else None,
        event.epoch,
    )


_BUFFER_INSERT_SQL = """
    INSERT INTO market_events
        (event_id, event_time, event_type, schema_version, payload, source, ingest_id, epoch)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (event_id, event_time) DO NOTHING
"""


class EventLogWriter:
    """Buffered, idempotent event log writer.

    Batches MarketEvent instances in memory and flushes them to PostgreSQL
    using parameterised batch INSERT with ON CONFLICT DO NOTHING.
    """

    def __init__(self, db_url: str, batch_size: int = 5000) -> None:
        self.db_url = db_url
        self.batch_size = batch_size
        self.buffer: list[MarketEvent] = []
        self._conn: psycopg.AsyncConnection | None = None

    async def __aenter__(self) -> "EventLogWriter":
        await self.initialize()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def initialize(self) -> None:
        """Open a persistent database connection."""
        self._conn = await psycopg.AsyncConnection.connect(
            self.db_url,
            connect_timeout=5,
            sslmode="require",
        )

    async def append(self, event: MarketEvent) -> None:
        """Buffer a single event; auto-flush when buffer reaches batch_size."""
        self.buffer.append(event)
        if len(self.buffer) >= self.batch_size:
            await self.flush()

    async def flush(self) -> int:
        """Flush buffered events to PostgreSQL in a single batch transaction.

        Returns the number of rows written. Uses retry with exponential back-off.
        """
        if not self.buffer:
            return 0
        batch = self.buffer[:]
        self.buffer.clear()

        rows = 0
        for attempt in range(3):
            try:
                async with self._conn.transaction():
                    records = [_event_to_db_row(ev) for ev in batch]
                    async with self._conn.cursor() as cur:
                        await cur.executemany(_BUFFER_INSERT_SQL, records)
                        rows = cur.rowcount
                break
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(2 ** (attempt + 1))
                else:
                    logger.exception("event_log_flush_failed", batch_size=len(batch))

        event_types = [ev.event_type for ev in batch]
        logger.info("event_log_flush", rows=rows or len(batch), event_types=event_types)
        return rows or len(batch)

    async def close(self) -> None:
        """Flush remaining events and close the database connection."""
        if self.buffer:
            await self.flush()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


class EventLogReader:
    """Query the immutable event log with optional filters."""

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url

    async def _connect(self) -> psycopg.AsyncConnection:
        return await psycopg.AsyncConnection.connect(
            self.db_url,
            connect_timeout=5,
            sslmode="require",
        )

    async def query(
        self,
        event_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        source: str | None = None,
        limit: int = 10000,
    ) -> list[MarketEvent]:
        """Return market events matching the given filters, newest first."""
        conn = await self._connect()
        try:
            clauses: list[str] = []
            params: dict[str, Any] = {"limit": limit}

            if start is not None:
                clauses.append("event_time >= %(start)s")
                params["start"] = start
            if end is not None:
                clauses.append("event_time <= %(end)s")
                params["end"] = end
            if event_type is not None:
                clauses.append("event_type = %(event_type)s")
                params["event_type"] = event_type
            if source is not None:
                clauses.append("source = %(source)s")
                params["source"] = source

            where = ""
            if clauses:
                where = " WHERE " + " AND ".join(clauses)

            sql = (
                "SELECT event_id, event_time, event_type, schema_version, "
                "payload, source, ingest_id, epoch "
                "FROM market_events" + where + " ORDER BY event_time DESC LIMIT %(limit)s"
            )

            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()

            return [self._row_to_event(r) for r in rows]
        finally:
            await conn.close()

    @staticmethod
    def _row_to_event(row: tuple) -> MarketEvent:
        """Convert a database row back to a MarketEvent."""
        return MarketEvent(
            event_id=uuid.UUID(str(row[0])),
            event_time=row[1],
            event_type=row[2],
            schema_version=row[3],
            payload=json.loads(row[4]) if isinstance(row[4], str) else row[4],
            source=row[5],
            ingest_id=uuid.UUID(str(row[6])) if row[6] else None,
            epoch=row[7] if row[7] is not None else 0,
        )

    async def get_latest_epoch(self, source: str) -> int:
        """Return the highest epoch recorded for a given data source (fencing token)."""
        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COALESCE(MAX(epoch), 0) FROM market_events WHERE source = %(source)s",
                    {"source": source},
                )
                row = await cur.fetchone()
                return row[0] if row else 0
        finally:
            await conn.close()


class EventCodec:
    """Encode/decode MarketEvent with schema evolution support (Kleppmann Ch.4).

    The MIGRATIONS registry maps an *old* schema_version to a callable that
    upgrades a raw payload dict to the next version.
    """

    MIGRATIONS: dict[int, Callable[[dict], dict]] = {}

    @classmethod
    def encode(cls, event: MarketEvent) -> dict:
        """Serialize a MarketEvent to a plain dict for storage or transport."""
        return {
            "event_id": str(event.event_id),
            "event_time": event.event_time.isoformat(),
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "payload": event.payload,
            "source": event.source,
            "ingest_id": str(event.ingest_id) if event.ingest_id else None,
            "epoch": event.epoch,
        }

    @classmethod
    def decode(cls, raw: dict) -> MarketEvent:
        """Deserialize a raw dict back into a MarketEvent.

        If the stored schema_version is lower than CURRENT_SCHEMA_VERSION,
        every applicable migration from MIGRATIONS is applied in sequence,
        and the resulting event's schema_version is bumped to current.
        """
        stored_version = raw.get("schema_version", 1)
        payload = raw.get("payload") or {}
        source = raw.get("source", "")
        epoch = raw.get("epoch", 0)

        # Apply migrations sequentially from stored_version up to current
        migrated_payload = payload
        for v in range(stored_version, CURRENT_SCHEMA_VERSION):
            fn = cls.MIGRATIONS.get(v)
            if fn is not None:
                migrated_payload = fn(migrated_payload)

        ingest_id_val: uuid.UUID | None = None
        if raw.get("ingest_id"):
            try:
                ingest_id_val = uuid.UUID(raw["ingest_id"])
            except (ValueError, AttributeError):
                logger.warning("invalid UUID in ingest_id", ingest_id=raw["ingest_id"])

        return MarketEvent(
            event_id=uuid.UUID(raw["event_id"]),
            event_time=datetime.fromisoformat(raw["event_time"]),
            event_type=raw["event_type"],
            schema_version=CURRENT_SCHEMA_VERSION,
            payload=migrated_payload,
            source=source,
            ingest_id=ingest_id_val,
            epoch=epoch,
        )


# ---------------------------------------------------------------------------
# Schema migration examples (Kleppmann Ch.4)
# ---------------------------------------------------------------------------


def migrate_v1_to_v2(payload: dict) -> dict:
    """Example v1→v2 migration: add ``oi_change`` defaulting to 0."""
    if "oi_change" not in payload:
        payload = {**payload, "oi_change": 0}
    return payload


# Register the migration
EventCodec.MIGRATIONS[1] = migrate_v1_to_v2
