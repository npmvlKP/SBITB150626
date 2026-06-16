"""Tests for scripts/daily_reconcile.py."""

from __future__ import annotations

from datetime import timedelta

import pytest

from scripts.daily_reconcile import (
    OrderRecord,
    ReconciliationIssue,
    ReconciliationReport,
    ReconciliationStatus,
    _get_ist_timestamp,
    _get_trading_day,
    compare_orders,
)


class TestReconciliationStatus:
    """Tests for ReconciliationStatus enum."""

    def test_all_status_values(self) -> None:
        """Verify all expected status values exist."""
        assert ReconciliationStatus.MATCHED.value == "matched"
        assert ReconciliationStatus.MISMATCH.value == "mismatch"
        assert ReconciliationStatus.MISSING_IN_BROKER.value == "missing_in_broker"
        assert ReconciliationStatus.MISSING_IN_LOCAL.value == "missing_in_local"
        assert ReconciliationStatus.STATUS_MISMATCH.value == "status_mismatch"
        assert ReconciliationStatus.SKIPPED.value == "skipped"


class TestOrderRecord:
    """Tests for OrderRecord dataclass."""

    def test_create_order_record(self) -> None:
        """OrderRecord should store all order fields."""
        record = OrderRecord(
            order_id="ORD001",
            symbol="NIFTY",
            segment="NSE",
            quantity=50,
            price="25000.50",
            order_type="LIMIT",
            status="ORDER_PLACED",
            timestamp="2024-01-15T09:30:00+05:30",
            source="broker",
        )

        assert record.order_id == "ORD001"
        assert record.symbol == "NIFTY"
        assert record.quantity == 50
        assert record.source == "broker"


class TestReconciliationIssue:
    """Tests for ReconciliationIssue dataclass."""

    def test_create_issue(self) -> None:
        """ReconciliationIssue should store all issue details."""
        issue = ReconciliationIssue(
            issue_type=ReconciliationStatus.MISMATCH,
            order_id="ORD001",
            description="Price mismatch",
            broker_value="25000",
            local_value="25001",
            severity="ERROR",
        )

        assert issue.order_id == "ORD001"
        assert issue.broker_value == "25000"
        assert issue.severity == "ERROR"


class TestReconciliationReport:
    """Tests for ReconciliationReport dataclass."""

    def test_initial_state(self) -> None:
        """New report should be compliant with no issues."""
        report = ReconciliationReport(
            report_id="REC-001",
            timestamp="2024-01-15T15:30:00+05:30",
            period_start="2024-01-15T09:15:00+05:30",
            period_end="2024-01-15T15:30:00+05:30",
        )

        assert report.is_compliant is True
        assert len(report.mismatches) == 0
        assert report.matched == 0

    def test_add_mismatch(self) -> None:
        """Adding mismatch should mark report as non-compliant."""
        report = ReconciliationReport(
            report_id="REC-001",
            timestamp="2024-01-15T15:30:00+05:30",
            period_start="2024-01-15T09:15:00+05:30",
            period_end="2024-01-15T15:30:00+05:30",
        )

        issue = ReconciliationIssue(
            issue_type=ReconciliationStatus.MISMATCH,
            order_id="ORD001",
            description="Mismatch",
        )

        report.add_mismatch(issue)

        assert report.is_compliant is False
        assert len(report.mismatches) == 1

    def test_get_summary(self) -> None:
        """get_summary should return correct statistics."""
        report = ReconciliationReport(
            report_id="REC-001",
            timestamp="2024-01-15T15:30:00+05:30",
            period_start="2024-01-15T09:15:00+05:30",
            period_end="2024-01-15T15:30:00+05:30",
            broker_orders=10,
            local_orders=10,
            matched=8,
        )

        summary = report.get_summary()

        assert summary["broker_orders"] == 10
        assert summary["local_orders"] == 10
        assert summary["matched"] == 8
        assert summary["is_compliant"] is True


class TestGetISTTimestamp:
    """Tests for IST timestamp helper."""

    def test_timestamp_format(self) -> None:
        """Timestamp should include timezone offset."""
        timestamp = _get_ist_timestamp()

        # Should contain the +05:30 offset for IST
        assert "+05:30" in timestamp
        assert "T" in timestamp  # ISO format separator


class TestGetTradingDay:
    """Tests for trading day boundaries."""

    def test_trading_hours(self) -> None:
        """Trading day should span 9:15 AM to 3:30 PM IST."""
        start, end = _get_trading_day()

        assert start.hour == 9
        assert start.minute == 15
        assert end.hour == 15
        assert end.minute == 30
        assert start < end

    def test_timezone_ist(self) -> None:
        """Trading day should be in IST timezone."""
        start, end = _get_trading_day()

        # IST is UTC+5:30
        offset = start.utcoffset()
        assert offset == timedelta(hours=5, minutes=30)


class TestFetchBrokerOrders:
    """Tests for broker order fetching."""

    @pytest.mark.asyncio
    async def test_broker_not_implemented(self) -> None:
        """fetch_broker_orders should raise NotImplementedError."""
        from scripts.daily_reconcile import fetch_broker_orders

        with pytest.raises(NotImplementedError, match="Broker API integration"):
            await fetch_broker_orders()


class TestCompareOrders:
    """Tests for order comparison logic."""

    def test_matching_orders(self) -> None:
        """Identical orders should be matched."""
        broker_orders = [
            OrderRecord(
                order_id="ORD001",
                symbol="NIFTY",
                segment="NSE",
                quantity=50,
                price="25000",
                order_type="LIMIT",
                status="ORDER_PLACED",
                timestamp="2024-01-15T09:30:00+05:30",
                source="broker",
            )
        ]
        local_orders = [
            OrderRecord(
                order_id="ORD001",
                symbol="NIFTY",
                segment="NSE",
                quantity=50,
                price="25000",
                order_type="LIMIT",
                status="ORDER_PLACED",
                timestamp="2024-01-15T09:30:00+05:30",
                source="local",
            )
        ]

        report = compare_orders(broker_orders, local_orders)

        assert report.matched == 1
        assert len(report.mismatches) == 0
        assert report.is_compliant is True

    def test_missing_in_local(self) -> None:
        """Order in broker but not local should be flagged."""
        broker_orders = [
            OrderRecord(
                order_id="ORD001",
                symbol="NIFTY",
                segment="NSE",
                quantity=50,
                price="25000",
                order_type="LIMIT",
                status="ORDER_PLACED",
                timestamp="2024-01-15T09:30:00+05:30",
                source="broker",
            )
        ]
        local_orders = []  # No local orders

        report = compare_orders(broker_orders, local_orders)

        assert report.matched == 0
        assert len(report.missing_in_local) == 1
        assert report.missing_in_local[0].order_id == "ORD001"
        assert report.is_compliant is False

    def test_status_mismatch(self) -> None:
        """Same order with different status should be flagged."""
        broker_orders = [
            OrderRecord(
                order_id="ORD001",
                symbol="NIFTY",
                segment="NSE",
                quantity=50,
                price="25000",
                order_type="LIMIT",
                status="ORDER_FILLED",
                timestamp="2024-01-15T09:30:00+05:30",
                source="broker",
            )
        ]
        local_orders = [
            OrderRecord(
                order_id="ORD001",
                symbol="NIFTY",
                segment="NSE",
                quantity=50,
                price="25000",
                order_type="LIMIT",
                status="ORDER_PLACED",
                timestamp="2024-01-15T09:30:00+05:30",
                source="local",
            )
        ]

        report = compare_orders(broker_orders, local_orders)

        assert len(report.status_mismatches) == 1
        assert "ORDER_FILLED" in report.status_mismatches[0].description
        assert "ORDER_PLACED" in report.status_mismatches[0].description

    def test_empty_orders(self) -> None:
        """No orders should result in compliant report."""
        report = compare_orders([], [])

        assert report.matched == 0
        assert report.is_compliant is True


class TestPrintReconciliationReport:
    """Tests for report printing (console fallback)."""

    def test_print_empty_report_no_rich(self) -> None:
        """Should print empty report without errors (no rich library)."""
        from scripts.daily_reconcile import ReconciliationReport, print_reconciliation_report

        report = ReconciliationReport(
            report_id="REC-001",
            timestamp="2024-01-15T15:30:00+05:30",
            period_start="2024-01-15T09:15:00+05:30",
            period_end="2024-01-15T15:30:00+05:30",
            broker_orders=0,
            local_orders=0,
            matched=0,
        )

        # This should work without rich library
        print_reconciliation_report(report)
