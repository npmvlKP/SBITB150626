"""End-of-day reconciliation - compare broker order book with local audit
trail.

Per ISO A.8.15: daily reconciliation is a compliance requirement.
Per Zerodha API: order book is transient (daily); positions reset for intraday.
Per MiFID II Art. 25(1): record keeping; SEBI: 5+ year retention.

Phase 0 Status: This is a production-grade skeleton with mock framework.
Full broker API integration will be implemented in Phase 3.

Note:
    Zerodha specifics:
    - Order book is transient (daily) - must reconcile before market close
    - Positions reset for intraday accounts
    - Kite API: /orders, /triggers for bracket orders (disabled since 2021)
    - Daily access token refresh required at 6:00 AM IST
"""

from __future__ import annotations

import asyncio
import io
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    pass

audit_logger = structlog.get_logger(__name__)


def _setup_windows_utf8() -> None:
    """Set UTF-8 encoding for Windows console output.

    This ensures special characters (check marks, warnings) display correctly
    on Windows terminals that default to 'charmap' encoding.
    """
    if sys.platform == "win32":
        # Reconfigure stdout/stderr to use UTF-8 encoding
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


class ReconciliationStatus(Enum):
    """Status of reconciliation check."""

    MATCHED = "matched"
    MISMATCH = "mismatch"
    MISSING_IN_BROKER = "missing_in_broker"
    MISSING_IN_LOCAL = "missing_in_local"
    STATUS_MISMATCH = "status_mismatch"
    SKIPPED = "skipped"


@dataclass
class OrderRecord:
    """Represents an order from broker or local audit."""

    order_id: str
    symbol: str
    segment: str
    quantity: int
    price: str | None  # Use string to avoid Decimal serialization issues
    order_type: str
    status: str
    timestamp: str
    source: str  # "broker" or "local"


@dataclass
class ReconciliationIssue:
    """Single reconciliation discrepancy."""

    issue_type: ReconciliationStatus
    order_id: str
    description: str
    broker_value: str | None = None
    local_value: str | None = None
    severity: str = "ERROR"


@dataclass
class ReconciliationReport:
    """Complete reconciliation report for the day."""

    report_id: str
    timestamp: str
    period_start: str
    period_end: str
    broker_orders: int = 0
    local_orders: int = 0
    matched: int = 0
    mismatches: list[ReconciliationIssue] = field(default_factory=list)
    missing_in_broker: list[ReconciliationIssue] = field(default_factory=list)
    missing_in_local: list[ReconciliationIssue] = field(default_factory=list)
    status_mismatches: list[ReconciliationIssue] = field(default_factory=list)
    is_compliant: bool = True
    notes: list[str] = field(default_factory=list)

    def add_mismatch(self, issue: ReconciliationIssue) -> None:
        """Add a mismatch and mark report as non-compliant."""
        self.mismatches.append(issue)
        self.is_compliant = False

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics as dictionary."""
        total_issues = (
            len(self.mismatches)
            + len(self.missing_in_broker)
            + len(self.missing_in_local)
            + len(self.status_mismatches)
        )
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "broker_orders": self.broker_orders,
            "local_orders": self.local_orders,
            "matched": self.matched,
            "total_issues": total_issues,
            "is_compliant": self.is_compliant,
            "severity": "ERROR" if total_issues > 0 else "OK",
        }


def _get_ist_timestamp() -> str:
    """Get current timestamp in IST timezone.

    Returns:
        ISO format timestamp string with IST timezone
    """
    # Calculate IST offset (UTC+5:30)
    ist_offset = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist_offset).strftime("%Y-%m-%dT%H:%M:%S %Z")


def _get_trading_day() -> tuple[datetime, datetime]:
    """Get the trading day boundaries in IST.

    Returns:
        Tuple of (start, end) datetime for today's trading session
    """
    ist_offset = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_offset)
    today = now_ist.date()

    # Trading hours: 9:15 AM to 3:30 PM IST
    trading_start = datetime.combine(today, datetime.min.time().replace(hour=9, minute=15))
    trading_end = datetime.combine(today, datetime.min.time().replace(hour=15, minute=30))

    return (
        trading_start.replace(tzinfo=ist_offset),
        trading_end.replace(tzinfo=ist_offset),
    )


async def fetch_broker_orders() -> list[OrderRecord]:
    """Fetch all orders from broker for the trading day.

    Per Zerodha API:
    - Order book is transient (daily)
    - GET /orders returns all orders for the day
    - Requires valid access token (refresh daily at 6:00 AM IST)

    Returns:
        List of OrderRecord from broker API

    Raises:
        NotImplementedError: Broker API not yet implemented (Phase 3)
    """
    # TODO(Phase 3): Implement Zerodha Kite API integration
    # Expected implementation:
    #   from src.brokers.zerodha import ZerodhaBroker
    #   broker = ZerodhaBroker()
    #   orders = await broker.get_orders(start_date=today, end_date=today)
    #
    # Zerodha API constraints:
    #   - Rate limit: 10 orders/sec, 400/min, 5000/day
    #   - No sandbox environment
    #   - Bracket orders disabled since 2021

    raise NotImplementedError(
        "Broker API integration not yet implemented. "
        "See Phase 3: Broker Integration. "
        "Until then, use local audit trail for reconciliation."
    )


async def fetch_local_orders(start: datetime, end: datetime) -> list[OrderRecord]:
    """Fetch order events from local audit trail.

    Args:
        start: Start of reconciliation period
        end: End of reconciliation period

    Returns:
        List of OrderRecord from local audit trail
    """
    try:
        from config.settings import AuditSettings
        from src.risk.audit import (
            ORDER_CANCELLED,
            ORDER_FILLED,
            ORDER_MODIFIED,
            ORDER_PLACED,
            ORDER_REJECTED,
            AuditLogger,
        )

        settings = AuditSettings()
        audit_logger_instance = AuditLogger(settings)

        # Query all order-related events for the period
        events = await audit_logger_instance.query_events(start=start, end=end, limit=10000)

        orders: dict[str, OrderRecord] = {}

        for event in events:
            if event.event_type not in {
                ORDER_PLACED,
                ORDER_FILLED,
                ORDER_REJECTED,
                ORDER_CANCELLED,
                ORDER_MODIFIED,
            }:
                continue

            details = event.details
            order_id = details.get("order_id", f"evt_{event.event_id}")

            if order_id not in orders:
                orders[order_id] = OrderRecord(
                    order_id=order_id,
                    symbol=details.get("symbol", "UNKNOWN"),
                    segment=details.get("segment", "UNKNOWN"),
                    quantity=details.get("quantity", 0),
                    price=details.get("price"),
                    order_type=details.get("order_type", "UNKNOWN"),
                    status=event.event_type,
                    timestamp=event.timestamp.isoformat(),
                    source="local",
                )
            else:
                # Update status to latest
                orders[order_id].status = event.event_type

        return list(orders.values())

    except Exception as e:  # noqa: BLE001
        audit_logger.error("failed_to_fetch_local_orders", error=str(e))
        return []


def compare_orders(
    broker_orders: list[OrderRecord],
    local_orders: list[OrderRecord],
) -> ReconciliationReport:
    """Compare broker orders against local audit trail.

    Args:
        broker_orders: Orders from broker API
        local_orders: Orders from local audit trail

    Returns:
        ReconciliationReport with all discrepancies
    """
    import uuid

    period_start, period_end = _get_trading_day()
    report = ReconciliationReport(
        report_id=f"REC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}",
        timestamp=_get_ist_timestamp(),
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        broker_orders=len(broker_orders),
        local_orders=len(local_orders),
    )

    # Create lookup dictionaries
    broker_by_id = {o.order_id: o for o in broker_orders}
    local_by_id = {o.order_id: o for o in local_orders}

    # Check for mismatches
    all_order_ids = set(broker_by_id.keys()) | set(local_by_id.keys())

    for order_id in all_order_ids:
        broker_order = broker_by_id.get(order_id)
        local_order = local_by_id.get(order_id)

        if broker_order and local_order:
            # Both exist - check for status mismatch
            if broker_order.status != local_order.status:
                issue = ReconciliationIssue(
                    issue_type=ReconciliationStatus.STATUS_MISMATCH,
                    order_id=order_id,
                    description=f"Status mismatch: broker={broker_order.status}, local={local_order.status}",
                    broker_value=broker_order.status,
                    local_value=local_order.status,
                    severity="WARNING",
                )
                report.status_mismatches.append(issue)
                report.add_mismatch(issue)
            else:
                report.matched += 1

        elif broker_order and not local_order:
            # Missing in local audit
            issue = ReconciliationIssue(
                issue_type=ReconciliationStatus.MISSING_IN_LOCAL,
                order_id=order_id,
                description="Order exists in broker but not in local audit trail",
                broker_value=f"{broker_order.status}@{broker_order.price}",
                local_value=None,
                severity="ERROR",
            )
            report.missing_in_local.append(issue)
            report.add_mismatch(issue)

        elif local_order and not broker_order:
            # Missing in broker (may be cancelled/expired)
            terminal_statuses = {"ORDER_CANCELLED", "ORDER_REJECTED"}
            if local_order.status not in terminal_statuses:
                issue = ReconciliationIssue(
                    issue_type=ReconciliationStatus.MISSING_IN_BROKER,
                    order_id=order_id,
                    description="Order exists locally but not in broker (non-terminal status)",
                    broker_value=None,
                    local_value=f"{local_order.status}@{local_order.price}",
                    severity="WARNING",
                )
                report.missing_in_broker.append(issue)

    return report


async def run_daily_reconciliation() -> ReconciliationReport:
    """Run end-of-day reconciliation between broker and local audit trail.

    Per ISO A.8.15: daily reconciliation is a compliance requirement.
    Per MiFID II Art. 25(1): record keeping requirements.

    This function:
      1. Fetches all orders from broker for the day (Phase 3+)
      2. Fetches all order events from local audit trail
      3. Compares order IDs, timestamps, statuses
      4. Flags mismatches (missing, extra, status mismatch)
      5. Logs and returns reconciliation report

    Returns:
        ReconciliationReport with all findings
    """
    audit_logger.info("reconciliation_started", phase="phase_0_skeleton")

    period_start, period_end = _get_trading_day()

    # Fetch orders from both sources
    local_orders = await fetch_local_orders(period_start, period_end)

    # Broker fetch is Phase 3 - currently using mock
    try:
        broker_orders = await fetch_broker_orders()
    except NotImplementedError:
        # Phase 0: Log and use empty broker orders for local-only check
        audit_logger.warning(
            "reconciliation_broker_not_available",
            message="Reconciliation not yet implemented - broker API integration required (Phase 3)",
        )
        broker_orders = []

    # Compare orders
    report = compare_orders(broker_orders, local_orders)

    # Add compliance notes
    if not broker_orders:
        report.notes.append("Phase 0: Broker API not integrated - local audit trail only")
        report.notes.append("Full reconciliation requires Phase 3 broker integration")

    # Log reconciliation event to audit trail
    try:
        from config.settings import AuditSettings
        from src.risk.audit import DAILY_RECONCILIATION, AuditLogger

        settings = AuditSettings()
        audit = AuditLogger(settings)
        await audit.log_event(
            event_type=DAILY_RECONCILIATION,
            source="daily_reconcile",
            details={
                "report_id": report.report_id,
                "broker_orders": report.broker_orders,
                "local_orders": report.local_orders,
                "matched": report.matched,
                "issues": len(report.mismatches),
                "is_compliant": report.is_compliant,
            },
        )
    except Exception as e:  # noqa: BLE001
        audit_logger.warning("failed_to_log_reconciliation_event", error=str(e))

    return report


def print_reconciliation_report(report: ReconciliationReport) -> None:
    """Print formatted reconciliation report to console.

    Args:
        report: ReconciliationReport to display
    """
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        _print_reconciliation_report_console(report)
        return

    console = Console()

    console.print()
    console.print("[bold blue]============================================================[/bold blue]")
    console.print("[bold blue]          Daily Reconciliation Report                        [/bold blue]")
    console.print("[bold blue]============================================================[/bold blue]")
    console.print(f"Report ID  : {report.report_id}")
    console.print(f"Timestamp  : {report.timestamp}")
    console.print(f"Period     : {report.period_start} to {report.period_end}")
    console.print()

    # Summary statistics
    console.print("[bold]Summary:[/bold]")
    console.print(f"  Broker Orders : {report.broker_orders}")
    console.print(f"  Local Orders  : {report.local_orders}")
    console.print(f"  Matched      : {report.matched}")
    console.print(f"  Issues       : {len(report.mismatches)}")
    console.print()

    # Issues table
    if report.mismatches:
        console.print("[bold red]Issues Found:[/bold red]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Type", style="cyan", width=18)
        table.add_column("Order ID", width=20)
        table.add_column("Description")

        for issue in report.mismatches:
            severity_color = "red" if issue.severity == "ERROR" else "yellow"
            table.add_row(
                f"[{severity_color}]{issue.issue_type.value}[/{severity_color}]",
                issue.order_id,
                issue.description,
            )

        console.print(table)
        console.print()
    else:
        console.print("[bold green]OK: No discrepancies found[/bold green]")
        console.print()

    # Compliance status
    if report.is_compliant:
        console.print("[bold green]OK: COMPLIANT - Daily reconciliation passed[/bold green]")
    else:
        console.print(f"[bold red]FAIL: NON-COMPLIANT - {len(report.mismatches)} issue(s) require investigation[/bold red]")

    # Phase notes
    for note in report.notes:
        console.print(f"[dim]Note: {note}[/dim]")

    console.print()


def _print_reconciliation_report_console(report: ReconciliationReport) -> None:
    """Print reconciliation report without rich library.

    Args:
        report: ReconciliationReport to display
    """
    print("\n" + "=" * 60)
    print("          Daily Reconciliation Report")
    print("=" * 60)
    print(f"Report ID  : {report.report_id}")
    print(f"Timestamp  : {report.timestamp}")
    print(f"Period     : {report.period_start} to {report.period_end}")
    print()
    print("Summary:")
    print(f"  Broker Orders : {report.broker_orders}")
    print(f"  Local Orders  : {report.local_orders}")
    print(f"  Matched      : {report.matched}")
    print(f"  Issues       : {len(report.mismatches)}")
    print()

    if report.mismatches:
        print("Issues Found:")
        for issue in report.mismatches:
            print(f"  [{issue.issue_type.value}] {issue.order_id}")
            print(f"    {issue.description}")
        print()
    else:
        print("No discrepancies found.\n")

    if report.is_compliant:
        print("OK: COMPLIANT - Daily reconciliation passed")
    else:
        print(f"FAIL: NON-COMPLIANT - {len(report.mismatches)} issue(s) require investigation")

    for note in report.notes:
        print(f"Note: {note}")
    print()


async def main() -> int:
    """Entry point for daily reconciliation script.

    Returns:
        Exit code: 0 if compliant, 1 if issues found
    """
    try:
        report = await run_daily_reconciliation()
        print_reconciliation_report(report)

        if not report.is_compliant:
            audit_logger.error(
                "reconciliation_non_compliant",
                report_id=report.report_id,
                issues=len(report.mismatches),
            )
            return 1

        audit_logger.info("reconciliation_completed", report_id=report.report_id)
        return 0

    except KeyboardInterrupt:
        print("\nReconciliation interrupted by user.")
        return 1
    except Exception as e:
        audit_logger.critical("reconciliation_unexpected_error", error=str(e), error_type=type(e).__name__)
        print(f"\nFATAL: Reconciliation failed unexpectedly: {e}")
        return 1


if __name__ == "__main__":
    # Setup UTF-8 encoding on Windows BEFORE any other imports/output
    _setup_windows_utf8()
    sys.exit(asyncio.run(main()))
