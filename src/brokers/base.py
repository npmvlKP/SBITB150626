"""Abstract broker interface.

Concrete implementations: Zerodha (Phase 3), Angel One (Phase 14), Dhan (Phase 14).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BrokerInterface(ABC):
    """Abstract broker interface — all broker implementations must implement these methods.

    Methods are async to support both sync (Zerodha) and async-capable (Angel One) brokers.
    """

    @abstractmethod
    async def authenticate(self) -> str:
        """Authenticate with the broker API.

        Returns:
            Access token string
        """

    @abstractmethod
    async def place_order(self, params: dict[str, Any]) -> dict[str, Any]:
        """Place a new order.

        Args:
            params: Order parameters dict

        Returns:
            Order response dict with order_id
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an open order.

        Args:
            order_id: Order ID to cancel

        Returns:
            Cancellation response dict
        """

    @abstractmethod
    async def cancel_all_orders(self) -> list[dict[str, Any]]:
        """Cancel all open orders.

        Returns:
            List of cancellation response dicts
        """

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """Get current open positions.

        Returns:
            List of position dicts
        """

    @abstractmethod
    async def get_margins(self) -> dict[str, Any]:
        """Get available margins and usage.

        Returns:
            Margins dict with available, used, etc.
        """

    @abstractmethod
    async def get_order_book(self) -> list[dict[str, Any]]:
        """Get all orders (open + historical).

        Returns:
            List of order dicts
        """

    @abstractmethod
    async def get_instruments(self, segment: str) -> list[dict[str, Any]]:
        """Get instrument list for a segment.

        Args:
            segment: "NSE" or "MCX"

        Returns:
            List of instrument dicts
        """
