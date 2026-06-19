"""
Immutable Event Log (Kleppmann Ch.3).

Single source of truth for all market data. All pipelines write events here first;
derived tables are populated from this log.
"""

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import psycopg
import structlog

# Initialize structured logger for event tracing
logger = structlog.get_logger()

# Current schema version assigned; increment upon schema change
CURRENT_SCHEMA_VERSION = 1

# Event type classification; semantically defined
_EVENT_TYPES = {
    "FO_BHAVCOPY",
    "CM_BHAVCOPY",
    "WS_TICK",
    "WS_OI_UPDATE",
    "GREEKS_SNAPSHOT",
}

# Type alias for potential eventing
EventType = str | None


@dataclass
class MarketEvent:
    event_id: uuid.UUID
    event_type: str
    event_time: datetime = datetime.now(UTC)
    schema_version: int = 1
    payload: dict = None
    source: str = ""
    ingest_id: uuid.UUID = None
    epoch: int = 0


def event_to_db_input(event: MarketEvent) -> tuple:
    """Pack event data for PostgreSQL INSERT operations."""
    return (
        str(event.event_id),
        event.event_time.replace(tzinfo=UTC) if event.event_time.tzinfo is None else event.event_time,
        event.event_type,
        json.dumps(
            {
                "schema_version": event.schema_version,
                "payload": event.payload or {},
                "source": event.source,
                "ingest_id": str(event.ingest_id) if event.ingest_id else None,
                "epoch": event.epoch,
            }
        ),
    )


class EventLogWriter:
    """Writable event log class managing event storage."""

    async def __init__(self, db_url: str, batch_size: int = 5000):
        """Setup connection and buffering structures."""
        self.db_url = db_url
        self.batch_size = batch_size
        self.buffer = []
        self.conn = None

    async def _connect(self) -> psycopg.Connection:
        """Return database connection with parameters for security and robustness."""
        return psycopg.connect(self.db_url, connect_timeout=5, sslmode="require")

    async def initialize(self):
        """Ensure a persistent db connection is available."""
        self.conn = await self._connect()

    async def append(self, event: MarketEvent) -> None:
        """Accumulate events to memory buffer."""
        if not hasattr(self, "buffer"):
            self.buffer = []
        self.buffer.append(event)
        await self.check_buffer_full()

    async def check_buffer_full(self):
        if len(self.buffer) >= self.batch_size:
            await self.flush()

    async def flush(self) -> int:
        """Atomic batch insert with retry pattern."""
        if not self.buffer:
            return 0

        retries = 0
        while retries < 3:
            try:
                records = [event_to_db_input(event) for event in self.buffer]
                with self.conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO market_events (event_id, event_time, event_type, payload) VALUES %s ON CONFLICT (event_id, event_time) DO NOTHING",
                        records,
                    )
                event_types = [e.event_type for e in self.buffer]
                flushed_events = len(self.buffer)
                self.buffer.clear()
                logger.info("event_log_flush", rows=flushed_events, event_types=event_types)
                return flushed_events
            except Exception:
                retries += 1
                await asyncio.sleep(2**retries)
        return 0

    async def close(self) -> None:
        """Freedom steward: Close db connection."""
        if self.conn:
            self.conn.close()


class EventLogReader:
    """Class responsible for querying market events."""

    async def get_write_connection(self) -> psycopg.Connection:
        """Manages database connection reuse for significant performance."""
        writer = EventLogWriter(self.db_url)
        if not hasattr(writer, "_connection") or writer._connection is None:
            writer._connection = await writer._connect()
        return writer._connection

    def __init__(self, db_url: str):
        self.db_url = db_url

    async def query(
        self,
        event_type: EventType,
        start: datetime = None,
        end: datetime = None,
        source: str = None,
        limit: int = 10000,
    ) -> list[dict]:
        """Retrieve records via extended filtering."""
        filters_applied = []
        filter_values = {"limit": limit}

        with await self.get_write_connection() as conn:
            if start:
                filters_applied.append("event_time >= %(etime_gt)s")
                filter_values["etime_gt"] = start.strftime("%Y-%m-%d %H:%M:%S")
            if end:
                filters_applied.append("event_time <= %(etime_lt)s")
                filter_values["etime_lt"] = end.strftime("%Y-%m-%d %H:%M:%S")
            if event_type:
                filters_applied.append("event_type = %(etype)s")
                filter_values["etype"] = event_type
            if source:
                filters_applied.append("payload->>'source' = %(src)s")
                filter_values["src"] = source

            query = "SELECT event_id, event_time, event_type, payload FROM market_events"
            if filters_applied:
                query += " WHERE " + " AND ".join(filters_applied)
            query += " ORDER BY event_time DESC LIMIT %(limit)s"

            await conn.execute(query, filter_values)
            records = await conn.fetchall()
            return [
                {
                    "event_id": str(r[0]),
                    "event_time": r[1],
                    "event_type": r[2],
                    "payload": json.loads(r[3]),
                }
                for r in records
            ]

    async def get_latest_epoch(self, source: str) -> int:
        """Stub: Must fetch maximal epoch for a data source."""
        raise NotImplementedError("Trigger back-end override for v2 and earlier operational cycle.")


class EventCodec:
    """
    Extremely responsive custom codec for EDA schema evolution
    while classifying: handling version differentiation & backward compatibility.
    """

    MIGRATIONS = {}  # Schema Migration Registry

    @classmethod
    def encode(cls, event: MarketEvent) -> dict:
        """Serialize event details into dictionary."""
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
        """Deserialize event with potential schema migrations if lower versioned."""
        ingest_id_val = None
        if "ingest_id" in raw and raw["ingest_id"]:
            try:
                ingest_id_val = uuid.UUID(raw["ingest_id"])
            except Exception:
                logger.warning("invalid UUID in ingest_id attribute")

        return MarketEvent(
            event_id=uuid.UUID(raw["event_id"]),
            event_time=datetime.fromisoformat(raw["event_time"]),
            event_type=raw["event_type"],
            schema_version=raw.get("schema_version", 1),
            payload=raw.get("payload"),
            source=raw.get("source", ""),
            ingest_id=ingest_id_val,
            epoch=raw.get("epoch", 0),
        )


# Sample migration handling: implementing schema wise promotion
def migrate_v1_to_v2(event: MarketEvent) -> MarketEvent:
    """When back-populating new entries in series schema (e.g., back-surge 'oi_change')."""
    return MarketEvent(
        **{**asdict(event), "payload": {**event.payload, "oi_change": event.payload.get("oi_change", 0)}}
    )
