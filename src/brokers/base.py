"""Abstract broker interface.

Concrete implementations: Zerodha (Phase 3), Angel One (Phase 14), Dhan (Phase 14).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

__all__ = ["BrokerInterface"]

class BrokerInterface(ABC):
    """Abstract broker interface for trading operations."""

    @abstractmethod
    async def authenticate(self) -> str:
        """Authenticate with the broker and return access token.

        Returns:
            str: Access token for authenticated session
        """
        pass

    @abstractmethod
    async def place_order(self, params: dict) -> dict:
        """Place a new order with the broker.

        Args:
            params: Order parameters including symbol, quantity, order type, etc.

        Returns:
            dict: Order confirmation response
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> dict:
        """Cancel an existing order.

        Args:
            order_id: The ID of the order to cancel

        Returns:
            dict: Cancellation confirmation response
        """
        pass

    @abstractmethod
    async def cancel_all_orders(self) -> list[dict[str, Any]]:
        """Cancel all active orders.

        Returns:
            list[dict]: List of cancellation responses for all orders
        """
        pass

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """Get current positions.

        Returns:
            list[dict]: List of current positions
        """
        pass

    @abstractmethod
    async def get_margins(self) -> dict[str, Any]:
        """Get account margin information.

        Returns:
            dict: Margin details including available margins, utilized margins, etc.
        """
        pass

    @abstractmethod
    async def get_order_book(self) -> list[dict[str, Any]]:
        """Get the order book.

        Returns:
            list[dict]: List of order book entries
        """
        pass

    @abstractmethod
    async def get_instruments(self, segment: str) -> list[dict[str, Any]]:
        """Get available instruments for a specific segment.

        Args:
            segment: Trading segment (e.g., 'equity', 'options', 'futures')

        Returns:
            list[dict]: List of instruments with their details
        """
        pass
