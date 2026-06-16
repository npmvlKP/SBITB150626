"""Abstract strategy interface for algorithmic trading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    __all__ = ["StrategyInterface"]


class StrategyInterface(ABC):
    """Abstract base class for trading strategies."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique identifier for the strategy."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Version of the strategy."""
        pass

    @abstractmethod
    async def on_tick(self, tick: dict[str, Any]) -> None:
        """Process incoming market tick.

        Args:
            tick: Market tick data containing symbol, price, volume, etc.
        """
        pass

    @abstractmethod
    async def on_order_update(self, update: dict[str, Any]) -> None:
        """Process order update notification.

        Args:
            update: Order update containing status, execution details, etc.
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the strategy. Performs initialization and sets up required subscriptions."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the strategy. Cleans up resources and cancels active orders."""
        pass
