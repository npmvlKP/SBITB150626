"""Pre-trade risk check pipeline — 10 sequential checks.

Per MiFID II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

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

def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(UTC).replace(microsecond=0)

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
        self._last_refill: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire a token if available.

        Implements token bucket algorithm for rate limiting per
        MiFID II RTS 6, FIX Order Throttling, NSE/INVG/67858.

        Returns:
            True if token was acquired (order allowed),
            False if rate limit exceeded (order rejected)
        """
        async with self._lock:
            now = asyncio.get_event_loop().time()
            if self._last_refill is None:
                self._last_refill = now
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True

            logger.warning("rate_limit_exceeded", tokens=self._tokens, rate=self._rate, capacity=self._capacity)
            return False

class RiskManager:
    """Pre-trade risk check pipeline — 10 sequential checks.

    Per MiFID II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012.
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
        self._last_daily_reset = _utcnow().date()
        self._daily_orders_lock = asyncio.Lock()
        self._daily_checked_on = None

        # Set a default available margin
        self.AVAILABLE_MARGIN = risk_settings.MAX_TOTAL_EXPOSURE

        logger.info("risk_manager_initialized")

    def get_avail_margin(self) -> Decimal:
        """Safely return the available margin."""
        return self._risk_settings.MAX_TOTAL_EXPOSURE

    def _reset_daily_count_if_needed(self) -> None:
        """Reset daily order count at start of new trading day.

        Per SEBI circular CIR/MRD/DP/09/2012, daily order limits
        must reset at start of each trading day.
        """
        today = _utcnow().date()
        if today > self._last_daily_reset and self._last_daily_reset != today:
            async def internal_reset():
                async with self._daily_orders_lock:
                    self._daily_order_count = 0
                    self._last_daily_reset = today
                    logger.info("daily_order_count_reset", date=str(today), max_orders=self._settings.MAX_ORDERS_PER_DAY)
            asyncio.create_task(internal_reset())
            self._daily_checked_on = today

    async def _perform_daily_check_if_needed(self) -> None:
        """Check and reset daily count if needed."""
        if self._daily_checked_on != _utcnow().date():
            self._reset_daily_count_if_needed()
            self._daily_checked_on = _utcnow().date()
            await asyncio.sleep(0.1)

    async def pre_trade_check(self, order: dict[str, Any]) -> PreTradeCheckResult:
        """Run all 10 pre-trade risk checks sequentially."""
        await self._perform_daily_check_if_needed()
        details: list[PreTradeCheckDetail] = []
        now = _utcnow()

        # Extract order fields
        symbol = order.get("symbol", "")
        segment_str = order.get("segment", "NSE").upper()
        quantity = order.get("quantity", 0)
        price = Decimal(str(order.get("price", 0)))
        order_value = price * Decimal(str(quantity))

        # Validate segment specification
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
            check5.reason = f"Rate limit exceeded"
            logger.warning("risk_check_failed", check=check5.check_name, reason=check5.reason)
        details.append(check5)

        # Check 6: Margin Available
        check6 = PreTradeCheckDetail(
            check_name="Margin Available",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("margin_controls")
        )
        margin_limit = self._risk_settings.MAX_TOTAL_EXPOSURE
        if order_value > margin_limit:
            check6.result = RiskCheckResult.FAIL
            check6.reason = f"price deviation {order_value - margin_limit} exceeds margin {margin_limit}"
            logger.warning("risk_check_failed", check=check6.check_name, reason=check6.reason)
        details.append(check6)

        # Check 7: Position Limit
        check7 = PreTradeCheckDetail(
            check_name="Position Limit",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("pre_trade_risk"),
        )
        # For this check, position limit can be segment-specific or default
        position_limit_name = f"{segment.value}_POSITION_LIMIT"
        if hasattr(self._risk_settings, position_limit_name):
            position_limit = getattr(self._risk_settings, position_limit_name)
        else:
            position_limit = self._risk_settings.MAX_POSITION_NOTIONAL_PER_SYMBOL

        if quantity > position_limit:
            check7.result = RiskCheckResult.FAIL
            check7.reason = f"position {quantity} exceeds limit of {position_limit}"
            logger.warning("risk_check_failed", check=check7.check_name, reason=check7.reason)
        details.append(check7)

        # Check 8: Max Exposure
        check8 = PreTradeCheckDetail(
            check_name="Max Exposure",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("pre_trade_risk")
        )
        exposure_limit = self._risk_settings.MAX_TOTAL_EXPOSURE
        if order_value > exposure_limit:
            check8.result = RiskCheckResult.FAIL
            check8.reason = f"exposure {order_value} exceeds limit of {exposure_limit} (risk settings)"
            logger.warning("risk_check_failed", check=check8.check_name, reason=check8.reason)
        details.append(check8)

        # Check 9: Price Protection
        explicit_ltp = Decimal(str(order.get("ltp", price)))
        check9 = PreTradeCheckDetail(
            check_name="Price Protection",
            result=RiskCheckResult.PASS,
            sebi_reference=SEBI_CIRCULAR_REFERENCES.get("price_checks"),
        )
        if explicit_ltp > 0:
            price_difference = abs(price - explicit_ltp) / explicit_ltp
            if price_difference > self._risk_settings.CIRCUIT_LIMIT_PCT:
                check9.result = RiskCheckResult.FAIL
                check9.reason = f"price deviation {price_difference:.4%} exceeds price protection limit of {self._risk_settings.CIRCUIT_LIMIT_PCT}"
                logger.warning("risk_check_failed", check=check9.check_name, reason=check9.reason)
        details.append(check9)

        # Check 10: Kill Switch
        check10 = PreTradeCheckDetail(
            check_name="Kill Switch Status",
            result=RiskCheckResult.PASS,
            sebi_reference="NIST RS.RP-1, MiFID II Art. 17, ISO A.8.26",
        )
        if not self._kill_switch.is_order_allowed():
            check10.result = RiskCheckResult.FAIL
            check10.reason = "kill switch active"
            logger.warning("risk_check_failed", check=check10.check_name, reason=check10.reason)
        details.append(check10)

        # Aggregate and return results
        failed_checks = [d for d in details if d.result == RiskCheckResult.FAIL]
        overall = RiskCheckResult.FAIL if failed_checks else RiskCheckResult.PASS

        if overall == RiskCheckResult.PASS:
            async with self._daily_orders_lock:
                self._daily_order_count += 1

        return PreTradeCheckResult(
            overall_result=overall,
            details=details,
            timestamp=now,
            order_id=order.get("order_id"),
        )

    async def check_daily_loss(self, current_pnl: Decimal) -> KillSwitchLevel | None:
        """Check if daily P&L loss limit exceeded."""
        if current_pnl <= -self._risk_settings.DAILY_LOSS_LIMIT:
            return KillSwitchLevel.KILL
        return None

    async def check_margin_utilization(self, utilization: Decimal) -> KillSwitchLevel | None:
        """Check if utilization limits exceeded."""
        if utilization >= self._risk_settings.MARGIN_UTILIZATION_KILL:
            return KillSwitchLevel.KILL
        if utilization >= self._risk_settings.MARGIN_UTILIZATION_THRESHOLD:
            return KillSwitchLevel.THROTTLE
        return None

    async def check_rejection_rate(self, rejections_last_minute: int) -> KillSwitchLevel | None:
        """Check order rejection rate threshold."""
        if rejections_last_minute >= self._risk_settings.ORDER_REJECTION_THRESHOLD:
            return KillSwitchLevel.KILL
        return None