"""
WebSocket Message Handlers for Zerodha Kite Connect
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from src.brokers.zerodha.types import (
    DepthUpdate,
    FullMarketDepth,
    LTPUpdate,
    Quote,
    Tick,
)

if TYPE_CHECKING:
    from src.data.providers import MarketDataProvider

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    """Represents an active subscription."""

    instrument_token: int
    exchange: str
    tradable: bool
    mode: str  # full, ltp, quote
    callback: Callable[..., Any] | None = None


class MessageHandler(Protocol):
    """Protocol for message handlers."""

    async def handle(self, message: dict[str, Any], provider: MarketDataProvider) -> bool: ...


class TickHandler:
    """Handles tick (LTP) updates from WebSocket."""

    @staticmethod
    async def handle(message: list[Any], provider: MarketDataProvider) -> bool:
        """Handle LTP tick update.

        Zerodha format:
        [42, 1, {"tradable": true, "mode": "ltp", "instrument_token": 256265}]

        Or:
        [42, 1, {"tradable": true, "mode": "ltp", ...}]
        """
        try:
            # Extract tick data
            if len(message) >= 3 and isinstance(message[2], dict):
                tick_data: dict[str, Any] = message[2]

                # Parse LTP update
                ltp_update = LTPUpdate(
                    instrument_token=tick_data.get("instrument_token"),
                    last_price=tick_data.get("last_price"),
                    last_quantity=tick_data.get("last_quantity"),
                    average_price=tick_data.get("average_price"),
                    volume=tick_data.get("volume"),
                    buy_quantity=tick_data.get("buy_quantity"),
                    sell_quantity=tick_data.get("sell_quantity"),
                    open=tick_data.get("open"),
                    high=tick_data.get("high"),
                    low=tick_data.get("low"),
                    close=tick_data.get("close"),
                    change=tick_data.get("change"),
                    exchange=tick_data.get("exchange", "NSE"),
                    timestamp=datetime.utcnow(),
                )

                # Store in database
                await provider.store_tick(ltp_update)

                logger.debug(
                    "tick_received: token=%s price=%s qty=%s",
                    ltp_update.instrument_token,
                    ltp_update.last_price,
                    ltp_update.last_quantity,
                )
                return True

        except Exception as e:
            logger.error("Failed to handle tick: %s", str(e))
            return False

        return False


class FullModeHandler:
    """Handles full mode updates (all fields)."""

    @staticmethod
    async def handle(message: list[Any], provider: MarketDataProvider) -> bool:
        """Handle full mode update.

        Zerodha format:
        [42, 1, {"tradable": true, "mode": "full", ...all fields...}]
        """
        try:
            if len(message) >= 3 and isinstance(message[2], dict):
                tick_data: dict[str, Any] = message[2]

                # Parse full tick
                tick = Tick(
                    instrument_token=tick_data.get("instrument_token"),
                    last_price=tick_data.get("last_price"),
                    last_quantity=tick_data.get("last_quantity"),
                    last_trade_time=tick_data.get("last_trade_time"),
                    average_price=tick_data.get("average_price"),
                    volume=tick_data.get("volume"),
                    total_buy_quantity=tick_data.get("total_buy_quantity"),
                    total_sell_quantity=tick_data.get("total_sell_quantity"),
                    open=tick_data.get("open"),
                    high=tick_data.get("high"),
                    low=tick_data.get("low"),
                    close=tick_data.get("close"),
                    change=tick_data.get("change"),
                    bid_price=tick_data.get("bid_price"),
                    bid_quantity=tick_data.get("bid_quantity"),
                    ask_price=tick_data.get("ask_price"),
                    ask_quantity=tick_data.get("ask_quantity"),
                    exchange=tick_data.get("exchange", "NSE"),
                    timestamp=datetime.utcnow(),
                )

                # Store in database
                await provider.store_tick(tick)

                logger.debug(
                    "full_tick_received: token=%s price=%s bid=%s ask=%s",
                    tick.instrument_token,
                    tick.last_price,
                    tick.bid_price,
                    tick.ask_price,
                )
                return True

        except Exception as e:
            logger.error("Failed to handle full tick: %s", str(e))
            return False

        return False


class QuoteModeHandler:
    """Handles quote mode updates."""

    @staticmethod
    async def handle(message: list[Any], provider: MarketDataProvider) -> bool:
        """Handle quote mode update.

        Zerodha format:
        [42, 1, {"tradable": true, "mode": "quote", ...quote fields...}]
        """
        try:
            if len(message) >= 3 and isinstance(message[2], dict):
                tick_data: dict[str, Any] = message[2]

                # Parse quote
                quote = Quote(
                    instrument_token=tick_data.get("instrument_token"),
                    last_price=tick_data.get("last_price"),
                    last_quantity=tick_data.get("last_quantity"),
                    last_trade_time=tick_data.get("last_trade_time"),
                    average_price=tick_data.get("average_price"),
                    volume=tick_data.get("volume"),
                    total_buy_quantity=tick_data.get("total_buy_quantity"),
                    total_sell_quantity=tick_data.get("total_sell_quantity"),
                    open=tick_data.get("open"),
                    high=tick_data.get("high"),
                    low=tick_data.get("low"),
                    close=tick_data.get("close"),
                    change=tick_data.get("change"),
                    bid_price=tick_data.get("bid_price"),
                    bid_quantity=tick_data.get("bid_quantity"),
                    ask_price=tick_data.get("ask_price"),
                    ask_quantity=tick_data.get("ask_quantity"),
                    oi=tick_data.get("oi"),
                    oi_day_high=tick_data.get("oi_day_high"),
                    oi_day_low=tick_data.get("oi_day_low"),
                    net_change=tick_data.get("net_change"),
                    exchange=tick_data.get("exchange", "NSE"),
                    timestamp=datetime.utcnow(),
                )

                # Store in database
                await provider.store_tick(quote)

                logger.debug(
                    "quote_received: token=%s price=%s oi=%s",
                    quote.instrument_token,
                    quote.last_price,
                    quote.oi,
                )
                return True

        except Exception as e:
            logger.error("Failed to handle quote: %s", str(e))
            return False

        return False


class DepthHandler:
    """Handles depth updates from WebSocket."""

    @staticmethod
    async def handle(message: list[Any], provider: MarketDataProvider) -> bool:
        """Handle depth update.

        Zerodha format for depth:
        [43, 1, {"tradable": true, "instrument_token": 256265, "depth": {...}}]
        """
        try:
            if len(message) >= 3 and isinstance(message[2], dict):
                depth_data: dict[str, Any] = message[2]

                # Parse depth update
                depth_update = DepthUpdate(
                    instrument_token=depth_data.get("instrument_token"),
                    exchange=depth_data.get("exchange", "NSE"),
                    bids=depth_data.get("bids", []),
                    asks=depth_data.get("asks", []),
                    timestamp=datetime.utcnow(),
                )

                # Store in database
                await provider.store_depth(depth_update)

                logger.debug(
                    "depth_received: token=%s bids=%s asks=%s",
                    depth_update.instrument_token,
                    len(depth_update.bids),
                    len(depth_update.asks),
                )
                return True

        except Exception as e:
            logger.error("Failed to handle depth: %s", str(e))
            return False

        return False


class FullMarketDepthHandler:
    """Handles full market depth updates."""

    @staticmethod
    async def handle(message: list[Any], provider: MarketDataProvider) -> bool:
        """Handle full market depth update.

        Zerodha format:
        [43, 1, {"tradable": true, "instrument_token": 256265, "depth": {...}}]
        """
        try:
            if len(message) >= 3 and isinstance(message[2], dict):
                depth_data: dict[str, Any] = message[2]

                # Parse full depth
                full_depth = FullMarketDepth(
                    instrument_token=depth_data.get("instrument_token"),
                    exchange=depth_data.get("exchange", "NSE"),
                    bids=depth_data.get("bids", []),
                    asks=depth_data.get("asks", []),
                    buy_quantities=depth_data.get("buy_quantities", []),
                    sell_quantities=depth_data.get("sell_quantities", []),
                    buy_prices=depth_data.get("buy_prices", []),
                    sell_prices=depth_data.get("sell_prices", []),
                    timestamp=datetime.utcnow(),
                )

                # Store in database
                await provider.store_depth(full_depth)

                logger.debug(
                    "full_depth_received: token=%s bids=%s asks=%s",
                    full_depth.instrument_token,
                    len(full_depth.bids),
                    len(full_depth.asks),
                )
                return True

        except Exception as e:
            logger.error("Failed to handle full depth: %s", str(e))
            return False

        return False


class OrderHandler:
    """Handles order updates."""

    @staticmethod
    async def handle(message: list[Any], provider: MarketDataProvider) -> bool:
        """Handle order update."""
        try:
            # Order updates typically have type 44 or similar
            if len(message) >= 2:
                order_data = message[1] if len(message) > 1 else message[2]

                logger.info("order_update: %s", order_data)
                return True

            return False

        except Exception as e:
            logger.error("Failed to handle order: %s", str(e))
            return False


class MessageRouter:
    """Routes incoming WebSocket messages to appropriate handlers."""

    def __init__(self, provider: MarketDataProvider) -> None:
        self.provider = provider
        self.subscriptions: dict[int, Subscription] = {}
        self.handlers: dict[int, list[Callable[..., Any]]] = {
            42: [TickHandler.handle, FullModeHandler.handle, QuoteModeHandler.handle],
            43: [DepthHandler.handle, FullMarketDepthHandler.handle],
            44: [OrderHandler.handle],
        }

    async def handle_message(self, message: Any) -> bool:
        """Route message to appropriate handler.

        Args:
            message: Raw message from WebSocket (can be list or dict)

        Returns:
            True if message was handled successfully
        """
        try:
            # Parse message if it's a string
            if isinstance(message, str | bytes):
                message = json.loads(message)

            # Handle subscription confirmation
            if self._is_subscription_confirmation(message):
                return await self._handle_subscription_confirmation(message)

            # Handle ticks and depth updates
            if isinstance(message, list) and len(message) >= 2:
                message_type = message[0]

                if message_type in self.handlers:
                    for handler in self.handlers[message_type]:
                        try:
                            if await handler(message, self.provider):
                                return True
                        except Exception as e:
                            logger.error(
                                "Handler failed for type %s: %s (%s)",
                                message_type,
                                str(e),
                                handler.__name__,
                            )
                            continue

            logger.warning("unhandled_message: type=%s msg=%s", type(message), message)
            return False

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON message: %s", str(e))
            return False
        except Exception as e:
            logger.error("Failed to handle message: %s", str(e))
            return False

    def _is_subscription_confirmation(self, message: Any) -> bool:
        """Check if message is a subscription confirmation."""
        if isinstance(message, list) and len(message) >= 2:
            # Zerodha sends confirmation as [1, ...] or similar
            msg_type = message[0]
            return msg_type in [1, 10, 11]  # Common confirmation types

        if isinstance(message, dict):
            return message.get("type") in ["subscription_confirmation", "confirmation"]

        return False

    async def _handle_subscription_confirmation(self, message: Any) -> bool:
        """Handle subscription confirmation from exchange."""
        try:
            if isinstance(message, list):
                # Extract instrument tokens from confirmation
                if len(message) >= 2:
                    instruments = message[1] if isinstance(message[1], list) else [message[1]]

                    for instr in instruments:
                        if isinstance(instr, dict):
                            token = instr.get("instrument_token")
                            if token:
                                self.subscriptions[token] = Subscription(
                                    instrument_token=token,
                                    exchange=instr.get("exchange", "NSE"),
                                    tradable=instr.get("tradable", True),
                                    mode=instr.get("mode", "ltp"),
                                )
                                logger.info(
                                    "subscription_confirmed: token=%s mode=%s",
                                    token,
                                    instr.get("mode"),
                                )

            return True

        except Exception as e:
            logger.error("Failed to handle subscription confirmation: %s", str(e))
            return False

    def add_subscription(self, subscription: Subscription) -> None:
        """Add a new subscription."""
        self.subscriptions[subscription.instrument_token] = subscription
        logger.info(
            "subscription_added: token=%s mode=%s",
            subscription.instrument_token,
            subscription.mode,
        )

    def remove_subscription(self, instrument_token: int) -> None:
        """Remove a subscription."""
        if instrument_token in self.subscriptions:
            del self.subscriptions[instrument_token]
            logger.info("subscription_removed: token=%s", instrument_token)

    def get_subscriptions(self) -> list[Subscription]:
        """Get all active subscriptions."""
        return list(self.subscriptions.values())
