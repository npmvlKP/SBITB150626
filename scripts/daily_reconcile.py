"""End-of-day reconciliation — compare broker order book with local audit trail.

Per ISO A.8.15: daily reconciliation is a compliance requirement.
Per Zerodha API: order book is transient (daily); positions reset for intraday.

Note:
    Reconciliation not yet implemented — broker API integration required (Phase 3).
    This skeleton will be completed when Zerodha broker integration is built.
"""

import structlog

logger = structlog.get_logger(__name__)


async def run_daily_reconciliation() -> None:
    """Run end-of-day reconciliation between broker and local audit trail.

    Steps (Phase 3+ implementation):
      1. Fetch all orders from broker for the day
      2. Fetch all order events from local audit trail
      3. Compare order IDs, timestamps, statuses
      4. Flag mismatches (missing, extra, status mismatch)
      5. Log reconciliation report
    """
    logger.warning(
        "daily_reconciliation_not_implemented",
        message="Reconciliation not yet implemented — broker API integration required (Phase 3)",
    )
    print("Reconciliation not yet implemented — broker API integration required (Phase 3)")


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_daily_reconciliation())
