"""Pre-trade risk check pipeline — 10 sequential checks.

Per MiFID II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from config.settings import ComplianceSettings, RiskSettings

from src.risk.compliance import (
    Segments,
    get_trading_session,
    is_order_allowed,
    validate_symbol,
)
from src.risk.kill_switch import KillSwitch, KillSwitchLevel

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc).replace(microsecond=0)


class RiskCheckResult(Enum):
    """Result of a single risk check."""

    PASS = "pass"  # nosec B105 - Enum value, not a password
    FAIL = "fail"  # nosec B105 - Enum value, not a password
    THROTTLED = "throttled"
    KILLED = "killed"


@dataclass
class PreTradeCheckDetail:
    """Result of a single pre-trade risk check."""

    check_name: str
    result: RiskCheckResult
    reason: str | None = None
    sebi_reference: str | None = None  # Circular number for audit trail


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

        Implements standard token bucket with refill per
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
                logger.info("rate_limit_token_acquired", tokens_remaining=self._tokens)
                return True

            logger.warning(
                "rate_limit_exceeded",
                tokens=self._tokens,
                rate=self._rate,
                capacity=self._capacity,
            )
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
        # Margin stub: defaults to MAX_TOTAL_EXPOSURE until real margin API connected
        self._available_margin: Decimal = risk_settings.MAX_TOTAL_EXPOSURE

        logger.info("risk_manager_initialized")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _reset_daily_count_if_needed(self) -> None:
        """Reset daily order count at start of new trading day.

        Per SEBI circular CIR/MRD/DP/09/2012, daily order limits must
        reset at start of each trading day.
        """
        today = _utcnow().date()
        if today > self._last_daily_reset:
            async with self._daily_orders_lock:
                self._daily_order_count = 0
                self._last_daily_reset = today
                logger.info(
                    "daily_order_count_reset",
                    date=str(today),
                    max_orders=self._settings.MAX_ORDERS_PER_DAY,
                )

    # ------------------------------------------------------------------
    # Pre-trade checks (all 10)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Individual pre-trade check methods (10 checks per MiFID II RTS 6)
    # ------------------------------------------------------------------

    async def _check_symbol_allowlist(self, symbol: str, segment: Segments) -> PreTradeCheckDetail:
        """Check 1: Symbol allowlist validation."""
        check = PreTradeCheckDetail(
            check_name="Symbol Allowlist",
            result=RiskCheckResult.PASS,
            sebi_reference="ISO A.8.26",
        )
        if not validate_symbol(symbol, segment, self._settings):
            check.result = RiskCheckResult.FAIL
            check.reason = f"Symbol '{symbol}' not in allowed list for {segment.value}"
            logger.warning(
                "risk_check_failed", check=check.check_name, reason=check.reason, sebi_reference=check.sebi_reference
            )
        else:
            logger.info("risk_check_passed", check=check.check_name, sebi_reference=check.sebi_reference)
        return check

    async def _check_trading_hours(self, segment: Segments, now: datetime) -> PreTradeCheckDetail:
        """Check 2: Trading hours validation."""
        session = get_trading_session(segment, now)
        check = PreTradeCheckDetail(
            check_name="Trading Hours",
            result=RiskCheckResult.PASS,
            sebi_reference="SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013",
        )
        if not is_order_allowed(session):
            check.result = RiskCheckResult.FAIL
            check.reason = f"Orders not allowed in {session.value} session"
            logger.warning(
                "risk_check_failed", check=check.check_name, reason=check.reason, sebi_reference=check.sebi_reference
            )
        else:
            logger.info(
                "risk_check_passed", check=check.check_name, session=session.value, sebi_reference=check.sebi_reference
            )
        return check

    async def _check_max_order_value(self, order_value: Decimal) -> PreTradeCheckDetail:
        """Check 3: Max order value validation."""
        check = PreTradeCheckDetail(
            check_name="Max Order Value",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012",
        )
        if order_value > self._risk_settings.MAX_ORDER_VALUE_PER_TRADE:
            check.result = RiskCheckResult.FAIL
            check.reason = f"Order value {order_value} exceeds max {self._risk_settings.MAX_ORDER_VALUE_PER_TRADE}"
            logger.warning(
                "risk_check_failed", check=check.check_name, reason=check.reason, sebi_reference=check.sebi_reference
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check.check_name,
                order_value=str(order_value),
                sebi_reference=check.sebi_reference,
            )
        return check

    async def _check_daily_order_count(self) -> PreTradeCheckDetail:
        """Check 4: Daily order count validation."""
        async with self._daily_orders_lock:
            check = PreTradeCheckDetail(
                check_name="Daily Order Count",
                result=RiskCheckResult.PASS,
                sebi_reference="Self-imposed best practice",
            )
            if self._daily_order_count >= self._settings.MAX_ORDERS_PER_DAY:
                check.result = RiskCheckResult.FAIL
                check.reason = (
                    f"Daily count {self._daily_order_count} reached limit {self._settings.MAX_ORDERS_PER_DAY}"
                )
                logger.warning(
                    "risk_check_failed",
                    check=check.check_name,
                    reason=check.reason,
                    sebi_reference=check.sebi_reference,
                )
            else:
                logger.info(
                    "risk_check_passed",
                    check=check.check_name,
                    daily_count=self._daily_order_count,
                    sebi_reference=check.sebi_reference,
                )
            return check

    async def _check_rate_limit(self) -> PreTradeCheckDetail:
        """Check 5: Rate limit (token bucket) validation."""
        check = PreTradeCheckDetail(
            check_name="Rate Limit",
            result=RiskCheckResult.PASS,
            sebi_reference="MiFID II RTS 6, FIX Order Throttling, NSE/INVG/67858",
        )
        if not await self._rate_limiter.acquire():
            check.result = RiskCheckResult.FAIL
            check.reason = "Rate limit exceeded"
            logger.warning(
                "risk_check_failed", check=check.check_name, reason=check.reason, sebi_reference=check.sebi_reference
            )
        else:
            logger.info("risk_check_passed", check=check.check_name, sebi_reference=check.sebi_reference)
        return check

    async def _check_margin_available(self, required_margin: Decimal) -> PreTradeCheckDetail:
        """Check 6: Margin available validation."""
        check = PreTradeCheckDetail(
            check_name="Margin Available",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012",
        )
        if self._available_margin < required_margin:
            check.result = RiskCheckResult.FAIL
            check.reason = f"Available margin {self._available_margin} < required margin {required_margin}"
            logger.warning(
                "risk_check_failed", check=check.check_name, reason=check.reason, sebi_reference=check.sebi_reference
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check.check_name,
                available_margin=str(self._available_margin),
                required_margin=str(required_margin),
                sebi_reference=check.sebi_reference,
            )
        return check

    async def _check_position_limit(self, position_notional: Decimal) -> PreTradeCheckDetail:
        """Check 7: Position limit validation."""
        check = PreTradeCheckDetail(
            check_name="Position Limit",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012",
        )
        if position_notional > self._risk_settings.MAX_POSITION_NOTIONAL_PER_SYMBOL:
            check.result = RiskCheckResult.FAIL
            check.reason = f"Position notional {position_notional} exceeds limit {self._risk_settings.MAX_POSITION_NOTIONAL_PER_SYMBOL}"
            logger.warning(
                "risk_check_failed", check=check.check_name, reason=check.reason, sebi_reference=check.sebi_reference
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check.check_name,
                notional=str(position_notional),
                sebi_reference=check.sebi_reference,
            )
        return check

    async def _check_max_exposure(self, order_value: Decimal) -> PreTradeCheckDetail:
        """Check 8: Max exposure validation."""
        check = PreTradeCheckDetail(
            check_name="Max Exposure",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012",
        )
        if order_value > self._risk_settings.MAX_TOTAL_EXPOSURE:
            check.result = RiskCheckResult.FAIL
            check.reason = f"Exposure {order_value} exceeds max total exposure {self._risk_settings.MAX_TOTAL_EXPOSURE}"
            logger.warning(
                "risk_check_failed", check=check.check_name, reason=check.reason, sebi_reference=check.sebi_reference
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check.check_name,
                exposure=str(order_value),
                sebi_reference=check.sebi_reference,
            )
        return check

    async def _check_price_protection(self, price: Decimal, ltp: Decimal) -> PreTradeCheckDetail:
        """Check 9: Price protection validation."""
        check = PreTradeCheckDetail(
            check_name="Price Protection",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012; Zerodha market_protection",
        )
        if ltp > 0:
            price_difference = abs(price - ltp) / ltp
            if price_difference > self._risk_settings.CIRCUIT_LIMIT_PCT:
                check.result = RiskCheckResult.FAIL
                check.reason = f"Price deviation {price_difference:.4%} exceeds price protection limit of {self._risk_settings.CIRCUIT_LIMIT_PCT}"
                logger.warning(
                    "risk_check_failed",
                    check=check.check_name,
                    reason=check.reason,
                    sebi_reference=check.sebi_reference,
                )
            else:
                logger.info(
                    "risk_check_passed",
                    check=check.check_name,
                    deviation=f"{price_difference:.4%}",
                    sebi_reference=check.sebi_reference,
                )
        else:
            logger.info(
                "risk_check_passed",
                check=check.check_name,
                note="ltp_zero_skipped",
                sebi_reference=check.sebi_reference,
            )
        return check

    async def _check_kill_switch(self) -> PreTradeCheckDetail:
        """Check 10: Kill switch status validation."""
        check = PreTradeCheckDetail(
            check_name="Kill Switch Status",
            result=RiskCheckResult.PASS,
            sebi_reference="NIST RS.RP-1, MiFID II Art. 17, ISO A.8.26",
        )
        if not self._kill_switch.is_order_allowed():
            check.result = RiskCheckResult.FAIL
            check.reason = "Kill switch active"
            logger.warning(
                "risk_check_failed", check=check.check_name, reason=check.reason, sebi_reference=check.sebi_reference
            )
        else:
            logger.info("risk_check_passed", check=check.check_name, sebi_reference=check.sebi_reference)
        return check

    async def pre_trade_check(self, order: dict[str, Any]) -> PreTradeCheckResult:
        """Run all 10 pre-trade risk checks sequentially.

        If ANY check fails, overall_result = FAIL with reason. Per MiFID
        II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012.
        """
        await self._reset_daily_count_if_needed()
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

        # Run all 10 checks
        checks = [
            await self._check_symbol_allowlist(symbol, segment),
            await self._check_trading_hours(segment, now),
            await self._check_max_order_value(order_value),
            await self._check_daily_order_count(),
            await self._check_rate_limit(),
            await self._check_margin_available(order_value),
            await self._check_position_limit(order_value),
            await self._check_max_exposure(order_value),
            await self._check_price_protection(price, Decimal(str(order.get("ltp", price)))),
            await self._check_kill_switch(),
        ]

        # Aggregate results
        failed_checks = [d for d in checks if d.result == RiskCheckResult.FAIL]
        overall = RiskCheckResult.FAIL if failed_checks else RiskCheckResult.PASS

        if overall == RiskCheckResult.PASS:
            async with self._daily_orders_lock:
                self._daily_order_count += 1

        return PreTradeCheckResult(
            overall_result=overall,
            details=checks,
            timestamp=now,
            order_id=order.get("order_id"),
        )

    # ------------------------------------------------------------------
    # Automatic risk monitoring checks
    # ------------------------------------------------------------------

    async def check_daily_loss(self, current_pnl: Decimal) -> KillSwitchLevel | None:
        """Check if daily P&L loss limit exceeded.

        If current_pnl <= -DAILY_LOSS_LIMIT: return KILL.

        Args:
            current_pnl: Current day's realized + unrealized P&L

        Returns:
            KillSwitchLevel.KILL if loss limit exceeded, None otherwise
        """
        if current_pnl <= -self._risk_settings.DAILY_LOSS_LIMIT:
            logger.critical(
                "daily_loss_limit_exceeded",
                current_pnl=str(current_pnl),
                loss_limit=str(self._risk_settings.DAILY_LOSS_LIMIT),
                action="KILL",
            )
            return KillSwitchLevel.KILL
        return None

    async def check_margin_utilization(self, utilization: Decimal) -> KillSwitchLevel | None:
        """Check if margin utilization exceeds thresholds.

        - If utilization >= MARGIN_UTILIZATION_KILL: return KILL
        - If utilization >= MARGIN_UTILIZATION_THRESHOLD: return THROTTLE + alert

        Args:
            utilization: Current margin utilization as decimal (0-1)

        Returns:
            KillSwitchLevel.KILL or KillSwitchLevel.THROTTLE if threshold
            exceeded, None otherwise
        """
        if utilization >= self._risk_settings.MARGIN_UTILIZATION_KILL:
            logger.critical(
                "margin_utilization_kill",
                utilization=str(utilization),
                kill_threshold=str(self._risk_settings.MARGIN_UTILIZATION_KILL),
                action="KILL",
            )
            return KillSwitchLevel.KILL
        if utilization >= self._risk_settings.MARGIN_UTILIZATION_THRESHOLD:
            logger.warning(
                "margin_utilization_threshold_alert",
                utilization=str(utilization),
                threshold=str(self._risk_settings.MARGIN_UTILIZATION_THRESHOLD),
                action="THROTTLE",
                message="Margin utilization threshold exceeded — throttling orders",
            )
            return KillSwitchLevel.THROTTLE
        return None

    async def check_rejection_rate(self, rejections_last_minute: int) -> KillSwitchLevel | None:
        """Check order rejection rate threshold.

        If rejections_last_minute >= ORDER_REJECTION_THRESHOLD: return KILL.

        Args:
            rejections_last_minute: Number of rejected orders in last 60 seconds

        Returns:
            KillSwitchLevel.KILL if threshold exceeded, None otherwise
        """
        if rejections_last_minute >= self._risk_settings.ORDER_REJECTION_THRESHOLD:
            logger.critical(
                "rejection_rate_exceeded",
                rejections_last_minute=rejections_last_minute,
                threshold=self._risk_settings.ORDER_REJECTION_THRESHOLD,
                action="KILL",
            )
            return KillSwitchLevel.KILL
        return None
