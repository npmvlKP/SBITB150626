"""Advanced order validation beyond basic checks.

Validates order structure, modification limits, lot size compliance, and
broker-specific constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.brokers.kite_client import ALLOWED_SEGMENTS

if TYPE_CHECKING:
    from config.settings import BrokerSettings, ComplianceSettings, PositionLimitSettings
    from src.risk.audit import AuditLogger


@dataclass(frozen=True)
class OrderValidationResult:
    """Result of order validation."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    modified_order: dict[str, Any] | None  # None if invalid, sanitized order if valid with warnings


ORDER_MODIFICATION_LIMIT = 25  # Zerodha API limit: 25 mods per order


class OrderValidator:
    """Advanced order validation beyond Phase 0 basic checks.

    Validates order structure, modification limits, lot size compliance,
    and Zerodha-specific constraints.
    """

    def __init__(
        self,
        compliance_settings: ComplianceSettings,
        broker_settings: BrokerSettings,
        position_settings: PositionLimitSettings,
        audit_logger: AuditLogger,
    ):
        self._compliance_settings = compliance_settings
        self._broker_settings = broker_settings
        self._position_settings = position_settings
        self._audit = audit_logger

    def validate_order_structure(self, order: dict) -> OrderValidationResult:
        """Validate order has all required fields with correct types.

        Required fields (per Kite API place_order):
        - exchange: str (one of ["NSE", "NFO", "MCX"])
        - tradingsymbol: str (Zerodha format, e.g., "NIFTY2470015000CE")
        - transaction_type: str ("BUY" or "SELL")
        - quantity: int (> 0, multiple of lot_size)
        - product: str ("MIS" for intraday, "NRML" for positional)
        - order_type: str ("MARKET", "LIMIT", "SL", "SL-M")
        - price: float | None (required for LIMIT/SL)
        - trigger_price: float | None (required for SL/SL-M)
        Returns OrderValidationResult with errors for missing/invalid fields.
        """
        errors = []
        warnings: list[str] = []

        exchange = order.get("exchange", "")
        if not exchange:
            errors.append("exchange is required")
        else:
            if exchange.upper() not in ALLOWED_SEGMENTS:
                errors.append(f"exchange must be one of {ALLOWED_SEGMENTS}, got '{exchange}'")
            seg = exchange.upper()

        # tradingsymbol
        tradingsymbol = order.get("tradingsymbol", "")
        if not tradingsymbol:
            errors.append("tradingsymbol is required")

        # transaction_type
        transaction_type = order.get("transaction_type", "")
        if not transaction_type:
            errors.append("transaction_type is required")
        else:
            tt = transaction_type.upper()
            if tt not in ["BUY", "SELL"]:
                errors.append("transaction_type must be 'BUY' or 'SELL'")

        # quantity
        quantity = order.get("quantity")
        if quantity is None:
            errors.append("quantity is required")
        else:
            try:
                qty = int(quantity)
                if qty <= 0:
                    errors.append("quantity must be positive")
            except (ValueError, TypeError):
                errors.append("quantity must be an integer")

        # product
        product = order.get("product", "")
        if not product:
            errors.append("product is required")
        else:
            p = product.upper()
            if p not in ["MIS", "NRML"]:
                errors.append("product must be 'MIS' or 'NRML'")

        # order_type
        order_type = order.get("order_type", "")
        if not order_type:
            errors.append("order_type is required")
        else:
            ot = order_type.upper()
            if ot not in ["MARKET", "LIMIT", "SL", "SL-M"]:
                errors.append("order_type must be 'MARKET', 'LIMIT', 'SL' or 'SL-M'")

        # price (required for LIMIT/SL)
        price = order.get("price")
        ot = order_type.upper()
        if ot in ["LIMIT", "SL"]:
            if price is None:
                errors.append(f"{ot} order requires price")
            else:
                try:
                    Decimal(str(price))
                except (ValueError, TypeError):
                    errors.append(f"{ot} price must be a number")

        # trigger_price (required for SL/SL-M)
        trigger_price = order.get("trigger_price")
        if ot == "SL-M":
            if trigger_price is None:
                errors.append("SL-M order requires trigger_price")
            else:
                try:
                    Decimal(str(trigger_price))
                except (ValueError, TypeError):
                    errors.append("SL-M trigger_price must be a number")

        # quantity multiple of lot size
        if not errors and seg in ["NFO", "MCX"] and exchange:
            try:
                qty = int(quantity) if quantity is not None else 0
            except (ValueError, TypeError):
                qty = 0
            result = self.validate_lot_size(tradingsymbol, qty)
            if not result.is_valid:
                errors.append(result.errors[0])

        # tradingsymbol format validation
        if not errors:
            result = self.validate_tradingsymbol_format(tradingsymbol, seg)
            if not result.is_valid:
                errors.append(result.errors[0])

        is_valid = len(errors) == 0
        return OrderValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            modified_order=order,
        )

    def check_modification_limit(self, order_id: str, modification_count: int) -> OrderValidationResult:
        """Check if order has exceeded Zerodha's 25 modifications per order
        limit.

        Per Zerodha API docs: max 25 modifications per order.
        If modification_count >= 25: REJECT (suggest cancel + re-place instead).
        If modification_count >= 20: WARNING (approaching limit).
        Log via audit_logger.
        THIS REPLACES the erroneous "minimum_resting_time_check()" from Plan.txt.
        """
        errors = []
        warnings = []
        if modification_count >= ORDER_MODIFICATION_LIMIT:
            errors.append(f"Modification limit {ORDER_MODIFICATION_LIMIT} exceeded")
        elif modification_count >= 20:
            warnings.append(f"Approaching modification limit ({modification_count}/{ORDER_MODIFICATION_LIMIT})")

        return OrderValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            modified_order=None,
        )

    def validate_lot_size(self, symbol: str, quantity: int) -> OrderValidationResult:
        """Validate quantity is a valid multiple of lot size.

        NIFTY: lot_size = 25 (PositionLimitSettings.NIFTY_LOT_SIZE)
        BANKNIFTY: lot_size = 15 (PositionLimitSettings.BANKNIFTY_LOT_SIZE)
        If quantity % lot_size != 0: REJECT with reason "Invalid lot multiple".
        """
        errors = []
        try:
            qty = int(quantity)
        except (ValueError, TypeError):
            return OrderValidationResult(
                is_valid=False,
                errors=[f"quantity must be an integer, got {quantity}"],
                warnings=[],
                modified_order=None,
            )

        if "NIFTY" in symbol and symbol.endswith(("CE", "PE")):
            lot_size = self._position_settings.NIFTY_LOT_SIZE
        elif "BANKNIFTY" in symbol and symbol.endswith(("CE", "PE")):
            lot_size = self._position_settings.BANKNIFY_LOT_SIZE
        elif any(symbol.startswith(metal) for metal in ["GOLD", "SILVER"]):
            lot_size = 1  # MCX metals typically have lot size of 1
        else:
            return OrderValidationResult(
                is_valid=True,  # Unknown symbol - skip lot size validation
                errors=[],
                warnings=[f"Unknown symbol pattern: {symbol}, skipping lot size validation"],
                modified_order=None,
            )

        if qty % lot_size != 0:
            errors.append(f"Invalid lot multiple: {qty} % {lot_size} = {qty % lot_size}")

        return OrderValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[],
            modified_order=None,
        )

    def validate_tradingsymbol_format(self, tradingsymbol: str, exchange: str) -> OrderValidationResult:
        """Validate Zerodha tradingsymbol format.

        Pattern for options: {SYMBOL}{YYM}{DD}{STRIKE}{CE|PE}
        Examples: "NIFTY2470015000CE", "BANKNIFTY247045000PE"
        Use regex to validate.
        If invalid: REJECT.
        """
        import re

        errors = []

        # Options pattern: SYMBOL + YYM + DD + STRIKE + CE/PE
        options_pattern = r"^(NIFTY|BANKNIFTY)(\d{2})(\d{2})(\d{5})(CE|PE)$"
        if exchange == "NFO":
            if not re.match(options_pattern, tradingsymbol):
                errors.append(f"Invalid tradingsymbol format: {tradingsymbol}. Expected pattern: {options_pattern}")

        # MCX patterns (correctly ordered and indented)
        elif exchange == "MCX":
            mcx_gold_pattern = r"^(GOLD)(\d{2})(\d{2})(\dP)\d+$"
            mcx_silver_pattern = r"^(SILVER)(\d{2})(\d{2})(\dP)\d+$"
            if not (re.match(mcx_gold_pattern, tradingsymbol) or re.match(mcx_silver_pattern, tradingsymbol)):
                errors.append(
                    f"Invalid tradingsymbol format: {tradingsymbol}. Expected patterns: {mcx_gold_pattern} or {mcx_silver_pattern}"
                )

        # NSE stocks pattern (correctly ordered and indented)
        elif exchange == "NSE":
            nse_pattern = r"^[A-Z0-9]{2,20}$"
            if not re.match(nse_pattern, tradingsymbol):
                errors.append(f"Invalid tradingsymbol format: {tradingsymbol}. Expected NSE pattern: {nse_pattern}")

        return OrderValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[],
            modified_order=None,
        )

    def validate_full(self, order: dict, modification_counts: dict[str, int] | None = None) -> OrderValidationResult:
        """Run all validations:
        1. Order structure
        2. Lot size
        3. Tradingsymbol format
        4. Modification limit (if order_id exists in modification_counts)
        Aggregate all errors and warnings.
        Return combined OrderValidationResult.
        """
        # Validate order structure
        result1 = self.validate_order_structure(order)
        errors = result1.errors.copy()
        warnings = result1.warnings.copy()

        # Stop if basic structure is invalid
        if not result1.is_valid:
            return OrderValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                modified_order=None,
            )

        # Get symbol and quantity (safe since structure is valid)
        symbol = order.get("tradingsymbol", "")
        quantity = order.get("quantity", 0)
        exchange = order.get("exchange", "")

        # Lot size validation
        result2 = self.validate_lot_size(symbol, quantity)
        errors.extend(result2.errors)
        warnings.extend(result2.warnings)

        # Tradingsymbol format validation
        result3 = self.validate_tradingsymbol_format(symbol, exchange)
        errors.extend(result3.errors)
        warnings.extend(result3.warnings)

        # Modification limit check
        if modification_counts and "order_id" in order:
            order_id = order["order_id"]
            mod_count = modification_counts.get(order_id, 0)
            result4 = self.check_modification_limit(order_id, mod_count)
            errors.extend(result4.errors)
            warnings.extend(result4.warnings)

        # Return aggregate result
        is_valid = len(errors) == 0
        return OrderValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            modified_order=order if is_valid else None,
        )
