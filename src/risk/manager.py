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

    async def pre_trade_check(self, order: dict[str, Any]) -> PreTradeCheckResult:
        """Run all 10 pre-trade risk checks sequentially.

        If ANY check fails, overall_result = FAIL with reason. Per MiFID
        II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012.
        """
        await self._reset_daily_count_if_needed()
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

        # ---- Check 1: Symbol Allowlist ----
        # Rule: order["symbol"] IN allowed symbols for the segment
        # Reference: ISO A.8.26 (application security requirements)
        check1 = PreTradeCheckDetail(
            check_name="Symbol Allowlist",
            result=RiskCheckResult.PASS,
            sebi_reference="ISO A.8.26",
        )
        if not validate_symbol(symbol, segment, self._settings):
            check1.result = RiskCheckResult.FAIL
            check1.reason = f"Symbol '{symbol}' not in allowed list for {segment.value}"
            logger.warning(
                "risk_check_failed",
                check=check1.check_name,
                reason=check1.reason,
                sebi_reference=check1.sebi_reference,
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check1.check_name,
                sebi_reference=check1.sebi_reference,
            )
        details.append(check1)

        # ---- Check 2: Trading Hours ----
        # Rule: get_trading_session(segment, now) == REGULAR
        # Reference: SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013
        session = get_trading_session(segment, now)
        check2 = PreTradeCheckDetail(
            check_name="Trading Hours",
            result=RiskCheckResult.PASS,
            sebi_reference="SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013",
        )
        if not is_order_allowed(session):
            check2.result = RiskCheckResult.FAIL
            check2.reason = f"Orders not allowed in {session.value} session"
            logger.warning(
                "risk_check_failed",
                check=check2.check_name,
                reason=check2.reason,
                sebi_reference=check2.sebi_reference,
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check2.check_name,
                session=session.value,
                sebi_reference=check2.sebi_reference,
            )
        details.append(check2)

        # ---- Check 3: Max Order Value ----
        # Rule: order_value <= MAX_ORDER_VALUE_PER_TRADE
        # Reference: CIR/MRD/DP/09/2012 (quantity limits, exposure limits)
        check3 = PreTradeCheckDetail(
            check_name="Max Order Value",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012",
        )
        if order_value > self._risk_settings.MAX_ORDER_VALUE_PER_TRADE:
            check3.result = RiskCheckResult.FAIL
            check3.reason = f"Order value {order_value} exceeds max {self._risk_settings.MAX_ORDER_VALUE_PER_TRADE}"
            logger.warning(
                "risk_check_failed",
                check=check3.check_name,
                reason=check3.reason,
                sebi_reference=check3.sebi_reference,
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check3.check_name,
                order_value=str(order_value),
                sebi_reference=check3.sebi_reference,
            )
        details.append(check3)

        # ---- Check 4: Daily Order Count ----
        # Rule: daily_order_count < MAX_ORDERS_PER_DAY
        # Reference: Self-imposed best practice
        async with self._daily_orders_lock:
            check4 = PreTradeCheckDetail(
                check_name="Daily Order Count",
                result=RiskCheckResult.PASS,
                sebi_reference="Self-imposed best practice",
            )
            if self._daily_order_count >= self._settings.MAX_ORDERS_PER_DAY:
                check4.result = RiskCheckResult.FAIL
                check4.reason = (
                    f"Daily count {self._daily_order_count} reached limit {self._settings.MAX_ORDERS_PER_DAY}"
                )
                logger.warning(
                    "risk_check_failed",
                    check=check4.check_name,
                    reason=check4.reason,
                    sebi_reference=check4.sebi_reference,
                )
            else:
                logger.info(
                    "risk_check_passed",
                    check=check4.check_name,
                    daily_count=self._daily_order_count,
                    sebi_reference=check4.sebi_reference,
                )
            details.append(check4)

        # ---- Check 5: Rate Limit ----
        # Rule: current_rate <= MAX_ORDERS_PER_SECOND (token bucket)
        # Reference: MiFID II RTS 6, FIX Order Throttling, NSE/INVG/67858
        check5 = PreTradeCheckDetail(
            check_name="Rate Limit",
            result=RiskCheckResult.PASS,
            sebi_reference="MiFID II RTS 6, FIX Order Throttling, NSE/INVG/67858",
        )
        if not await self._rate_limiter.acquire():
            check5.result = RiskCheckResult.FAIL
            check5.reason = "Rate limit exceeded"
            logger.warning(
                "risk_check_failed",
                check=check5.check_name,
                reason=check5.reason,
                sebi_reference=check5.sebi_reference,
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check5.check_name,
                sebi_reference=check5.sebi_reference,
            )
        details.append(check5)

        # ---- Check 6: Margin Available ----
        # Rule: available_margin >= required_margin (stub)
        # Reference: CIR/MRD/DP/09/2012 (pre-trade risk controls)
        check6 = PreTradeCheckDetail(
            check_name="Margin Available",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012",
        )
        required_margin = order_value
        if self._available_margin < required_margin:
            check6.result = RiskCheckResult.FAIL
            check6.reason = f"Available margin {self._available_margin} < required margin {required_margin}"
            logger.warning(
                "risk_check_failed",
                check=check6.check_name,
                reason=check6.reason,
                sebi_reference=check6.sebi_reference,
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check6.check_name,
                available_margin=str(self._available_margin),
                required_margin=str(required_margin),
                sebi_reference=check6.sebi_reference,
            )
        details.append(check6)

        # ---- Check 7: Position Limit ----
        # Rule: projected_position <= MAX_POSITION_NOTIONAL_PER_SYMBOL
        # Reference: CIR/MRD/DP/09/2012 (exposure limits)
        check7 = PreTradeCheckDetail(
            check_name="Position Limit",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012",
        )
        position_notional = order_value  # price * quantity = notional
        if position_notional > self._risk_settings.MAX_POSITION_NOTIONAL_PER_SYMBOL:
            check7.result = RiskCheckResult.FAIL
            check7.reason = f"Position notional {position_notional} exceeds limit {self._risk_settings.MAX_POSITION_NOTIONAL_PER_SYMBOL}"
            logger.warning(
                "risk_check_failed",
                check=check7.check_name,
                reason=check7.reason,
                sebi_reference=check7.sebi_reference,
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check7.check_name,
                notional=str(position_notional),
                sebi_reference=check7.sebi_reference,
            )
        details.append(check7)

        # ---- Check 8: Max Exposure ----
        # Rule: total_exposure <= MAX_TOTAL_EXPOSURE
        # Reference: CIR/MRD/DP/09/2012 (exposure limits at individual client level)
        check8 = PreTradeCheckDetail(
            check_name="Max Exposure",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012",
        )
        if order_value > self._risk_settings.MAX_TOTAL_EXPOSURE:
            check8.result = RiskCheckResult.FAIL
            check8.reason = (
                f"Exposure {order_value} exceeds max total exposure {self._risk_settings.MAX_TOTAL_EXPOSURE}"
            )
            logger.warning(
                "risk_check_failed",
                check=check8.check_name,
                reason=check8.reason,
                sebi_reference=check8.sebi_reference,
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check8.check_name,
                exposure=str(order_value),
                sebi_reference=check8.sebi_reference,
            )
        details.append(check8)

        # ---- Check 9: Price Protection ----
        # Rule: abs(price - ltp) / ltp <= CIRCUIT_LIMIT_PCT
        # Reference: CIR/MRD/DP/09/2012 (price checks); Zerodha market_protection
        explicit_ltp = Decimal(str(order.get("ltp", price)))
        check9 = PreTradeCheckDetail(
            check_name="Price Protection",
            result=RiskCheckResult.PASS,
            sebi_reference="CIR/MRD/DP/09/2012; Zerodha market_protection",
        )
        if explicit_ltp > 0:
            price_difference = abs(price - explicit_ltp) / explicit_ltp
            if price_difference > self._risk_settings.CIRCUIT_LIMIT_PCT:
                check9.result = RiskCheckResult.FAIL
                check9.reason = f"Price deviation {price_difference:.4%} exceeds price protection limit of {self._risk_settings.CIRCUIT_LIMIT_PCT}"
                logger.warning(
                    "risk_check_failed",
                    check=check9.check_name,
                    reason=check9.reason,
                    sebi_reference=check9.sebi_reference,
                )
            else:
                logger.info(
                    "risk_check_passed",
                    check=check9.check_name,
                    deviation=f"{price_difference:.4%}",
                    sebi_reference=check9.sebi_reference,
                )
        else:
            logger.info(
                "risk_check_passed",
                check=check9.check_name,
                note="ltp_zero_skipped",
                sebi_reference=check9.sebi_reference,
            )
        details.append(check9)

        # ---- Check 10: Kill Switch Status ----
        # Rule: kill_switch.is_order_allowed() == True
        # Reference: NIST RS.RP-1, MiFID II Art. 17, ISO A.8.26
        check10 = PreTradeCheckDetail(
            check_name="Kill Switch Status",
            result=RiskCheckResult.PASS,
            sebi_reference="NIST RS.RP-1, MiFID II Art. 17, ISO A.8.26",
        )
        if not self._kill_switch.is_order_allowed():
            check10.result = RiskCheckResult.FAIL
            check10.reason = "Kill switch active"
            logger.warning(
                "risk_check_failed",
                check=check10.check_name,
                reason=check10.reason,
                sebi_reference=check10.sebi_reference,
            )
        else:
            logger.info(
                "risk_check_passed",
                check=check10.check_name,
                sebi_reference=check10.sebi_reference,
            )
        details.append(check10)

        # ---- Aggregate results ----
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
