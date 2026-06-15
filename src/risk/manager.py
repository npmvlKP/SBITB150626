"""Pre-trade risk check pipeline — 10 sequential checks.

Per MiFID II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from config.settings import ComplianceSettings, RiskSettings

from src.risk.compliance import (
    SEBI_CIRCULAR_REFERENCES,
    Segments,
    get_trading_session,
    is_order_allowed,
    validate_symbol,
)
from src.risk.kill_switch import KillSwitch, KillSwitchLevel

logger = structlog.get_logger(__name__)


class RiskCheckResult(Enum):
    """Result of a single risk check."""

    PASS = "pass"
    FAIL = "fail"
    THROTTLED = "throttled"
    KILLED = "killed"


@dataclass
class PreTradeCheckDetail:
    """Result of a single pre-trade risk check."""

    check_name: str
    result: RiskCheckResult
    reason: str | None = None
    sebi_reference: str | None = None


@dataclass
class PreTradeCheckResult:
    """Aggregate result of all pre-trade risk checks."""

    overall_result: RiskCheckResult
    details: list[PreTradeCheckDetail]
    timestamp: datetime
    order_id: str | None = None


class TokenBucketRateLimiter:
    """Token bucket rate limiter for order throttling.

    Per MiFID II RTS 6, FIX Order Throttling, NSE/INVG/67858.
    """

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire a token if available.

        Returns:
            True if allowed, False if rate exceeded
        """
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True

            logger.warning("rate_limit_exceeded", tokens=self._tokens, rate=self._rate)
            return False


class RiskManager:
    """Pre-trade risk check pipeline — 10 sequential checks.

    Per MiFID II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012.

    Args:
        settings: ComplianceSettings instance
        risk_settings: RiskSettings instance
        kill_switch: KillSwitch instance
    """

    def __init__(
        self,
        settings: ComplianceSettings,
        risk_settings: RiskSettings,
        kill_switch: KillSwitch,
    ) -> None:
        self._settings = settings
        self._risk_settings = risk_settings
        self._kill_switch = kill_switch
        self._rate_limiter = TokenBucketRateLimiter(
            rate=float(settings.MAX_ORDERS_PER_SECOND),
            capacity=int(settings.MAX_ORDERS_PER_SECOND),
        )
        self._daily_order_count = 0
        self._last_daily_reset = datetime.utcnow().date()
        self._daily_orders_lock = asyncio.Lock()

        logger.info("risk_manager_initialized")

    def _reset_daily_count_if_needed(self) -> None:
        """Reset daily order count at start of new trading day."""
        today = datetime.utcnow().date()
        if today > self._last_daily_reset:
            self._daily_order_count = 0
            self._last_daily_reset = today
            logger.info("daily_order_count_reset", date=str(today))

    async def pre_trade_check(self, order: dict) -> PreTradeCheckResult:
        """Run all 10 pre-trade risk checks sequentially.

        Per MiFID II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012.

        Checks:
          1. Symbol Allowlist          → ISO A.8.26
          2. Trading Hours             → SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013
          3. Max Order Value           → CIR/MRD/DP/09/2012
          4. Daily Order Count         → Self-imposed best practice
          5. Rate Limit                → MiFID II RTS 6, NSE/INVG/67858
          6. Margin Available          → CIR/MRD/DP/09/2012
          7. Position Limit            → CIR/MRD/DP/09/2012
          8. Max Exposure              → CIR/MRD/DP/09/2012
          9. Price Protection          → CIR/MRD/DP/09/2012
          10. Kill Switch Status       → NIST RS.RP-1, MiFID II Art. 17, ISO A.8.26

        Args:
            order: Order dict with keys: symbol, segment, quantity, price, exchange

        Returns:
            PreTradeCheckResult with overall result and per-check details
        """
        self._reset_daily_count_if_needed()
        details: list[PreTradeCheckDetail] = []
        now = datetime.utcnow()

        # Extract order fields
        symbol = order.get("symbol", "")
        segment_str = order.get("segment", "NSE").upper()
        quantity = order.get("quantity", 0)
        price = Decimal(str(order.get("price", 0)))
        order_value = price * Decimal(str(quantity))

        try:
            segment = Segments(segment_str)
        except ValueError:
            segment = Segments.NSE

        # Check 1: Symbol Allowlist
        check1 = PreTradeCheckDetail(
            check_name="Symbol Allowlist",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("pre_trade_risk"),
        )
        if not validate_symbol(symbol, segment, self._settings):
            check1.result = RiskCheckResult.FAIL
            check1.reason = f"Symbol '{symbol}' not in allowed list for {segment.value}"
            logger.warning("risk_check_failed", check=check1.check_name, reason=check1.reason)
        details.append(check1)

        # Check 2: Trading Hours
        session = get_trading_session(segment, now)
        check2 = PreTradeCheckDetail(
            check_name="Trading Hours",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("trading_hours"),
        )
        if not is_order_allowed(session):
            check2.result = RiskCheckResult.FAIL
            check2.reason = f"Orders not allowed in {session.value} session"
            logger.warning("risk_check_failed", check=check2.check_name, reason=check2.reason)
        details.append(check2)

        # Check 3: Max Order Value
        check3 = PreTradeCheckDetail(
            check_name="Max Order Value",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("pre_trade_risk"),
        )
        if order_value > self._risk_settings.MAX_ORDER_VALUE_PER_TRADE:
            check3.result = RiskCheckResult.FAIL
            check3.reason = f"Order value {order_value} exceeds max {self._risk_settings.MAX_ORDER_VALUE_PER_TRADE}"
            logger.warning("risk_check_failed", check=check3.check_name, reason=check3.reason)
        details.append(check3)

        # Check 4: Daily Order Count
        async with self._daily_orders_lock:
            check4 = PreTradeCheckDetail(
                check_name="Daily Order Count",
                result=RiskCheckResult.PASS,
            )
            if self._daily_order_count >= self._settings.MAX_ORDERS_PER_DAY:
                check4.result = RiskCheckResult.FAIL
                check4.reason = (
                    f"Daily count {self._daily_order_count} reached limit {self._settings.MAX_ORDERS_PER_DAY}"
                )
                logger.warning("risk_check_failed", check=check4.check_name, reason=check4.reason)
            details.append(check4)

        # Check 5: Rate Limit
        check5 = PreTradeCheckDetail(
            check_name="Rate Limit",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("ops_threshold"),
        )
        if not await self._rate_limiter.acquire():
            check5.result = RiskCheckResult.FAIL
            check5.reason = f"Rate limit exceeded: {self._settings.MAX_ORDERS_PER_SECOND} orders/sec"
            logger.warning("risk_check_failed", check=check5.check_name, reason=check5.reason)
        details.append(check5)

        # Check 6: Margin Available (stub)
        check6 = PreTradeCheckDetail(
            check_name="Margin Available",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("margin_controls"),
        )
        # TODO: Query broker for available margin in Phase 3
        details.append(check6)

        # Check 7: Position Limit (stub)
        check7 = PreTradeCheckDetail(
            check_name="Position Limit",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("pre_trade_risk"),
        )
        # TODO: Check projected position in Phase 3
        details.append(check7)

        # Check 8: Max Exposure (stub)
        check8 = PreTradeCheckDetail(
            check_name="Max Exposure",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("pre_trade_risk"),
        )
        # TODO: Check total exposure in Phase 3
        details.append(check8)

        # Check 9: Price Protection
        ltp = Decimal(str(order.get("ltp", price)))
        check9 = PreTradeCheckDetail(
            check_name="Price Protection",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("price_checks"),
        )
        if ltp > 0:
            price_deviation = abs(price - ltp) / ltp
            if price_deviation > self._risk_settings.CIRCUIT_LIMIT_PCT:
                check9.result = RiskCheckResult.FAIL
                check9.reason = (
                    f"Price deviation {price_deviation:.4%} exceeds "
                    f"circuit limit {self._risk_settings.CIRCUIT_LIMIT_PCT}"
                )
                logger.warning("risk_check_failed", check=check9.check_name, reason=check9.reason)
        details.append(check9)

        # Check 10: Kill Switch Status
        check10 = PreTradeCheckDetail(
            check_name="Kill Switch Status",
            result=RiskCheckResult.PASS,
            sebi_reference="NIST RS.RP-1, MiFID II Art. 17, ISO A.8.26",
        )
        if not self._kill_switch.is_order_allowed():
            check10.result = RiskCheckResult.FAIL
            check10.reason = f"Kill switch active: {self._kill_switch.get_state()['current_level']}"
            logger.warning("risk_check_failed", check=check10.check_name, reason=check10.reason)
        details.append(check10)

        # Determine overall result
        failed_checks = [d for d in details if d.result == RiskCheckResult.FAIL]
        overall = RiskCheckResult.FAIL if failed_checks else RiskCheckResult.PASS

        if overall == RiskCheckResult.PASS:
            async with self._daily_orders_lock:
                self._daily_order_count += 1

        logger.info(
            "pre_trade_check_completed",
            overall=overall.value,
            checks_passed=sum(1 for d in details if d.result == RiskCheckResult.PASS),
            checks_failed=len(failed_checks),
        )

        return PreTradeCheckResult(
            overall_result=overall,
            details=details,
            timestamp=now,
            order_id=order.get("order_id"),
        )

    async def check_daily_loss(self, current_pnl: Decimal) -> KillSwitchLevel | None:
        """Check if daily loss limit exceeded.

        Args:
            current_pnl: Current session P&L (negative = loss)

        Returns:
            KillSwitchLevel.KILL if limit exceeded, None otherwise
        """
        if current_pnl <= -self._risk_settings.DAILY_LOSS_LIMIT:
            logger.critical(
                "daily_loss_limit_exceeded",
                current_pnl=str(current_pnl),
                limit=str(self._risk_settings.DAILY_LOSS_LIMIT),
            )
            return KillSwitchLevel.KILL
        return None

    async def check_margin_utilization(self, utilization: Decimal) -> KillSwitchLevel | None:
        """Check margin utilization thresholds.

        Args:
            utilization: Current margin utilization as Decimal (e.g., 0.85 = 85%)

        Returns:
            KillSwitchLevel.KILL if >= 95%, THROTTLE if >= 80%, None otherwise
        """
        if utilization >= self._risk_settings.MARGIN_UTILIZATION_KILL:
            logger.critical(
                "margin_utilization_kill",
                utilization=str(utilization),
                threshold=str(self._risk_settings.MARGIN_UTILIZATION_KILL),
            )
            return KillSwitchLevel.KILL

        if utilization >= self._risk_settings.MARGIN_UTILIZATION_THRESHOLD:
            logger.warning(
                "margin_utilization_throttle",
                utilization=str(utilization),
                threshold=str(self._risk_settings.MARGIN_UTILIZATION_THRESHOLD),
            )
            return KillSwitchLevel.THROTTLE

        return None

    async def check_rejection_rate(self, rejections_last_minute: int) -> KillSwitchLevel | None:
        """Check order rejection rate.

        Args:
            rejections_last_minute: Number of rejections in last 60 seconds

        Returns:
            KillSwitchLevel.KILL if >= ORDER_REJECTION_THRESHOLD, None otherwise
        """
        if rejections_last_minute >= self._risk_settings.ORDER_REJECTION_THRESHOLD:
            logger.critical(
                "rejection_rate_kill",
                rejections=rejections_last_minute,
                threshold=self._risk_settings.ORDER_REJECTION_THRESHOLD,
            )
            return KillSwitchLevel.KILL
        return None
