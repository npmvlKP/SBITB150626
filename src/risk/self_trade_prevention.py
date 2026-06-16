"""Client-side self-trade prevention as defense-in-depth.

Zerodha RMS is the primary enforcement. This is a supplementary client-side check for additional safety.
A self-trade occurs when:
- New BUY order would match existing SELL order (same symbol, same or crossing price)
- New SELL order would match existing BUY order (same symbol, same or crossing price)
Per CIR/MRD/DP/09/2012: pre-trade risk controls must prevent erroneous orders.
Self-trade prevention is an industry best practice (FIX Self-Trade Prevention, MiFID II).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.risk.audit import AuditLogger


@dataclass(frozen=True)
class SelfTradeCheckResult:
    """Result of self-trade prevention check."""

    is_self_trade: bool
    matching_order_id: str | None
    matching_side: str | None  # "BUY" or "SELL"
    reason: str
    sebi_reference: str = "CIR/MRD/DP/09/2012 (pre-trade risk controls)"


class SelfTradePrevention:
    """Client-side self-trade prevention as defense-in-depth.

    Zerodha RMS is the primary enforcement. This is a supplementary
    client-side check.
    """

    def __init__(self, audit_logger: AuditLogger):
        self._audit = audit_logger
        self._open_orders: dict[str, dict] = {}  # order_id -> order_dict

    def check_order(self, new_order: dict) -> SelfTradeCheckResult:
        """Check if new_order would self-trade against existing open orders.

        Matching criteria:
        1. Same symbol (e.g., "NIFTY2470015000CE")
        2. Opposite side (BUY vs SELL)
        3. Price overlap: new_buy_price >= existing_sell_price OR new_sell_price <= existing_buy_price
        If match found: return SelfTradeCheckResult(is_self_trade=True)
        If no match: return SelfTradeCheckResult(is_self_trade=False)
        Log result via audit_logger.
        """
        symbol = new_order.get("tradingsymbol")
        transaction_type = new_order.get("transaction_type").upper()
        price = Decimal(str(new_order.get("price", "0")))

        # Iterate through all open orders
        for order_id, existing_order in self._open_orders.items():
            existing_symbol = existing_order.get("tradingsymbol")
            existing_side = existing_order.get("transaction_type").upper()
            existing_price = Decimal(str(existing_order.get("price", "0")))

            # Check if same symbol and opposite sides
            if symbol == existing_symbol and transaction_type != existing_side:
                # Check price overlap (bid/ask crossing)
                if transaction_type == "BUY" and price >= existing_price:
                    # New BUY at/above existing SELL
                    return SelfTradeCheckResult(
                        is_self_trade=True,
                        matching_order_id=order_id,
                        matching_side=existing_side,
                        reason=f"New BUY price {price} crosses existing SELL price {existing_price}",
                    )
                elif transaction_type == "SELL" and price <= existing_price:
                    # New SELL at/below existing BUY
                    return SelfTradeCheckResult(
                        is_self_trade=True,
                        matching_order_id=order_id,
                        matching_side=existing_side,
                        reason=f"New SELL price {price} crosses existing BUY price {existing_price}",
                    )

        return SelfTradeCheckResult(is_self_trade=False)

    def register_order(self, order_id: str, order: dict) -> None:
        """Add order to tracking after it's placed."""
        self._open_orders[order_id] = order

    def remove_order(self, order_id: str) -> None:
        """Remove order from tracking after it's filled/cancelled."""
        if order_id in self._open_orders:
            del self._open_orders[order_id]

    def get_open_orders(self) -> dict[str, dict]:
        """Return current open orders dict."""
        return self._open_orders.copy()

    def clear(self) -> None:
        """Clear all tracked orders (e.g., at session start)."""
        self._open_orders.clear()
