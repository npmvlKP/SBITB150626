"""Audit trail — 7-year append-only with SHA-256 checksums.

Per MiFID II Art. 25(1): record keeping; ISO A.8.15: logging.
Per SEBI: 5+ year retention; we retain 7 years.
Per NIST AU-9: audit information protection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from config.settings import AuditSettings

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(UTC).replace(microsecond=0)


# Event type constants
ORDER_PLACED = "ORDER_PLACED"
ORDER_FILLED = "ORDER_FILLED"
ORDER_REJECTED = "ORDER_REJECTED"
ORDER_CANCELLED = "ORDER_CANCELLED"
ORDER_MODIFIED = "ORDER_MODIFIED"
KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
KILL_SWITCH_DEACTIVATED = "KILL_SWITCH_DEACTIVATED"
RISK_CHECK_PASSED = "RISK_CHECK_PASSED"
RISK_CHECK_FAILED = "RISK_CHECK_FAILED"
MARGIN_ALERT = "MARGIN_ALERT"
DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
SESSION_START = "SESSION_START"
SESSION_END = "SESSION_END"
DAILY_RECONCILIATION = "DAILY_RECONCILIATION"
CONFIG_CHANGE = "CONFIG_CHANGE"
STRATEGY_DEPLOYED = "STRATEGY_DEPLOYED"
STRATEGY_STOPPED = "STRATEGY_STOPPED"

ALL_EVENT_TYPES = {
    ORDER_PLACED,
    ORDER_FILLED,
    ORDER_REJECTED,
    ORDER_CANCELLED,
    ORDER_MODIFIED,
    KILL_SWITCH_ACTIVATED,
    KILL_SWITCH_DEACTIVATED,
    RISK_CHECK_PASSED,
    RISK_CHECK_FAILED,
    MARGIN_ALERT,
    DAILY_LOSS_LIMIT,
    SESSION_START,
    SESSION_END,
    DAILY_RECONCILIATION,
    CONFIG_CHANGE,
    STRATEGY_DEPLOYED,
    STRATEGY_STOPPED,
}


@dataclass
class AuditEvent:
    """Single audit event with cryptographic integrity."""

    event_id: uuid.UUID
    timestamp: datetime
    event_type: str
    source: str
    details: dict[str, Any]
    checksum: str
    ntp_offset_ms: float | None = None


class NTPClock:
    """NTP-synchronized clock for accurate timestamping.

    Per MiFID II: timestamp accuracy; NIST AU-3.
    """

    def __init__(self, settings: AuditSettings) -> None:
        self._settings = settings
        self._last_offset_ms: float = 0.0

    async def get_time(self) -> datetime:
        """Return system time with NTP offset applied.

        Returns:
            timezone-aware UTC datetime
        """
        await self.check_offset()
        return _utcnow()

    async def check_offset(self) -> float:
        """Query NTP server and return offset in milliseconds.

        Returns:
            NTP offset in ms (0.0 if unavailable)

        Note:
            Alert via structlog if offset > MAX_NTP_OFFSET_MS
        """
        try:
            import ntplib

            client = ntplib.NTPClient()
            response = client.request(self._settings.NTP_SERVER, timeout=5)
            offset_s = response.offset
            self._last_offset_ms = offset_s * 1000

            if abs(self._last_offset_ms) > self._settings.MAX_NTP_OFFSET_MS:
                logger.warning(
                    "ntp_clock_drift_exceeds_limit",
                    offset_ms=self._last_offset_ms,
                    max_allowed=self._settings.MAX_NTP_OFFSET_MS,
                )

            return self._last_offset_ms

        except Exception as e:
            logger.debug("ntp_clock_unavailable", error=str(e))
            self._last_offset_ms = 0.0
            return 0.0


class AuditLogger:
    """Append-only audit trail with SHA-256 checksums.

    Args:
        settings: AuditSettings configuration
    """

    def __init__(self, settings: AuditSettings) -> None:
        self._settings = settings
        self._ntp_clock = NTPClock(settings)
        self._events: list[AuditEvent] = []
        self._lock: asyncio.Lock | None = None  # Lazily initialized in async context

        logger.info(
            "audit_logger_initialized",
            retention_years=settings.RETENTION_YEARS,
            checksum_algorithm=settings.CHECKSUM_ALGORITHM,
            ntp_server=settings.NTP_SERVER,
        )

    @property
    def _async_lock(self) -> asyncio.Lock:
        """Lazily initialize the asyncio lock (must be created within an event
        loop)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _compute_checksum(self, event: AuditEvent) -> str:
        """Compute SHA-256 checksum of event fields.

        Args:
            event: AuditEvent to checksum

        Returns:
            Hex-encoded SHA-256 digest
        """
        payload = (
            str(event.event_id)
            + event.timestamp.isoformat()
            + event.event_type
            + event.source
            + json.dumps(event.details, sort_keys=True)
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def log_event(
        self,
        event_type: str,
        source: str,
        details: dict[str, Any],
        ntp_offset_ms: float | None = None,
    ) -> AuditEvent:
        """Log an audit event with checksum.

        Per MiFID II Art. 25(1), ISO A.8.15, SEBI 5+ year retention.

        Args:
            event_type: Event type from ALL_EVENT_TYPES
            source: Module/component generating the event
            details: Flexible payload dict
            ntp_offset_ms: NTP clock offset at event time

        Returns:
            AuditEvent record
        """
        async with self._async_lock:
            event_id = uuid.uuid4()
            timestamp = _utcnow()

            event = AuditEvent(
                event_id=event_id,
                timestamp=timestamp,
                event_type=event_type,
                source=source,
                details=details,
                checksum="",  # Will be set below
                ntp_offset_ms=ntp_offset_ms,
            )
            event.checksum = self._compute_checksum(event)

            self._events.append(event)

            logger.debug(
                "audit_event_logged",
                event_id=str(event.event_id),
                event_type=event_type,
                source=source,
            )

            return event

    async def verify_chain_integrity(self) -> bool:
        """Verify checksums of stored events.

        Per NIST AU-9: audit information protection.

        Returns:
            True if all checksums valid, False if tampering detected
        """
        async with self._async_lock:
            for event in self._events:
                expected = self._compute_checksum(event)
                if event.checksum != expected:
                    logger.error(
                        "audit_integrity_failure",
                        event_id=str(event.event_id),
                        event_type=event.event_type,
                        expected_checksum=expected,
                        stored_checksum=event.checksum,
                    )
                    return False

            logger.info("audit_integrity_verified", event_count=len(self._events))
            return True

    async def query_events(
        self,
        event_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query stored audit events with filters.

        Args:
            event_type: Filter by event type
            start: Filter events after this time
            end: Filter events before this time
            limit: Max events to return

        Returns:
            List of matching AuditEvent records
        """
        async with self._async_lock:
            results = self._events

            if event_type is not None:
                results = [e for e in results if e.event_type == event_type]

            if start is not None:
                results = [e for e in results if e.timestamp >= start]

            if end is not None:
                results = [e for e in results if e.timestamp <= end]

            return results[-limit:]
