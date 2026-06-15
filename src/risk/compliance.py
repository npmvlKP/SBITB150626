"""SEBI compliance enforcement — constants, session checks, OPS threshold.

References:
- SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013: Retail algo framework
- NSE/INVG/67858 (May 5, 2025): OPS threshold = 10, IP registration
- SEBI/HO/MRD/DP/CIR/P/2018/62: 500ms resting time — NOT MANDATED (dropped)
- CIR/MRD/DP/09/2012: Pre-trade risk controls mandatory

CRITICAL CORRECTIONS:
- 500ms resting time is NOT a SEBI mandate — was proposed in 2016 discussion paper,
  dropped in SEBI/HO/MRD/DP/CIR/P/2018/62. No constant, no reference, no DO NOT rule.
- Algo ID tagging is BROKER's responsibility per SEBI Feb 2025 circular.
  Our `tag` field is for our own audit trail/attribution only.
- OPS threshold = 10 per NSE/INVG/67858 (May 5, 2025).
"""

from datetime import datetime, time
from enum import Enum

import structlog

from config.settings import ComplianceSettings

logger = structlog.get_logger(__name__)


class ComplianceLevel(Enum):
    """Algo registration status based on OPS.

    Per NSE/INVG/67858: <=10 OPS = UNREGISTERED; >10 OPS = must REGISTER with exchange.
    """

    UNREGISTERED = "unregistered"
    REGISTERED = "registered"


class Segments(Enum):
    """Allowed trading segments."""

    NSE = "NSE"
    MCX = "MCX"


class TradingSession(Enum):
    """Market session states."""

    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    POST_MARKET = "post_market"
    CLOSED = "closed"


SEBI_CIRCULAR_REFERENCES: dict = {
    "ops_threshold": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 + NSE/INVG/67858",
    "algo_tagging": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 (broker responsibility)",
    "pre_trade_risk": "CIR/MRD/DP/09/2012",
    "trading_hours": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013",
    "price_checks": "CIR/MRD/DP/09/2012",
    "margin_controls": "CIR/MRD/DP/09/2012",
}


def get_trading_session(segment: Segments, now: datetime) -> TradingSession:
    """Return current trading session for the given segment.

    NSE hours (IST):
      - PRE_MARKET: 9:00-9:15 (call auction)
      - REGULAR: 9:15-15:30
      - POST_MARKET: 15:30-15:40
      - CLOSED: else

    MCX hours (IST):
      - MORNING: 9:00-14:30
      - EVENING: 17:00-23:30
      - CLOSED: else

    Per SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013.

    Args:
        segment: NSE or MCX
        now: Current datetime (IST-aware or naive, treated as IST)

    Returns:
        TradingSession enum value
    """
    ist_now = now.replace(tzinfo=None)
    current_time = ist_now.time()

    if segment == Segments.NSE:
        pre_market_start = time(9, 0)
        pre_market_end = time(9, 15)
        regular_end = time(15, 30)
        post_market_end = time(15, 40)

        if pre_market_start <= current_time < pre_market_end:
            return TradingSession.PRE_MARKET
        if pre_market_end <= current_time < regular_end:
            return TradingSession.REGULAR
        if regular_end <= current_time < post_market_end:
            return TradingSession.POST_MARKET
        return TradingSession.CLOSED

    elif segment == Segments.MCX:
        morning_start = time(9, 0)
        morning_end = time(14, 30)
        evening_start = time(17, 0)
        evening_end = time(23, 30)

        if morning_start <= current_time < morning_end:
            return TradingSession.REGULAR
        if evening_start <= current_time < evening_end:
            return TradingSession.REGULAR
        return TradingSession.CLOSED

    return TradingSession.CLOSED


def is_order_allowed(session: TradingSession) -> bool:
    """Check if orders are allowed in the given session.

    Only REGULAR session allows order placement.
    PRE_MARKET, POST_MARKET, CLOSED all return False.

    Args:
        session: Current trading session

    Returns:
        True if orders allowed, False otherwise
    """
    return session == TradingSession.REGULAR


def check_ops_threshold(current_ops: float, settings: ComplianceSettings | None = None) -> ComplianceLevel:
    """Check if current OPS exceeds SEBI registration threshold.

    Per NSE/INVG/67858: >10 OPS requires exchange registration through broker.
    We self-impose 3 OPS (well below threshold).

    Args:
        current_ops: Current orders per second rate
        settings: ComplianceSettings instance

    Returns:
        ComplianceLevel.UNREGISTERED if current_ops <= SEBI_OPS_REGISTRATION_THRESHOLD
        ComplianceLevel.REGISTERED otherwise (and log WARNING)
    """
    if settings is None:
        settings = ComplianceSettings()

    threshold = settings.SEBI_OPS_REGISTRATION_THRESHOLD

    if current_ops <= threshold:
        logger.debug(
            "ops_within_threshold",
            current_ops=current_ops,
            threshold=threshold,
            reference=SEBI_CIRCULAR_REFERENCES["ops_threshold"],
        )
        return ComplianceLevel.UNREGISTERED

    logger.warning(
        "ops_exceeds_threshold_registration_required",
        current_ops=current_ops,
        threshold=threshold,
        reference=SEBI_CIRCULAR_REFERENCES["ops_threshold"],
    )
    return ComplianceLevel.REGISTERED


def validate_symbol(symbol: str, segment: Segments, settings: ComplianceSettings | None = None) -> bool:
    """Validate symbol is in the allowed instruments list for the segment.

    Args:
        symbol: Instrument symbol (e.g., "NIFTY", "GOLD")
        segment: Trading segment
        settings: ComplianceSettings instance

    Returns:
        True if symbol is allowed, False otherwise
    """
    if settings is None:
        settings = ComplianceSettings()

    if segment == Segments.NSE:
        return symbol.upper() in [s.upper() for s in settings.ALLOWED_NSE_INSTRUMENTS]
    elif segment == Segments.MCX:
        return symbol.upper() in [s.upper() for s in settings.ALLOWED_MCX_INSTRUMENTS]

    return False


def format_algo_tag(strategy_id: str, version: str, max_length: int = 20) -> str:
    """Format algo tag for the Kite API `tag` field.

    CRITICAL NOTE: This tag is for our own audit trail and order attribution.
    Exchange-mandated algo ID tagging is the BROKER's responsibility per
    SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013. The broker (Zerodha) assigns
    and tags the official exchange algo ID server-side.

    Our `tag` field: "strategy_id:version" for our internal audit + attribution.

    Args:
        strategy_id: Strategy identifier
        version: Strategy version string
        max_length: Max tag length (Zerodha limit = 20 chars per Kite API docs)

    Returns:
        Truncated tag string max_length chars
    """
    tag = f"{strategy_id}:{version}"

    if len(tag) > max_length:
        avail = max_length - len(version) - 1
        if avail > 0:
            return f"{strategy_id[:avail]}:{version}"
        else:
            return tag[:max_length]

    return tag
