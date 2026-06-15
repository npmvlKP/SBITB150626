"""Abstract strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StrategyInterface(ABC):
    """Abstract strategy interface.

    All trading strategies must inherit from this and implement all methods.
    Strategies are event-driven: on_tick, on_order_update.
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique strategy identifier."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Strategy version string."""

    @abstractmethod
    async def on_tick(self, tick: dict[str, Any]) -> None:
        """Handle incoming market tick.

        Args:
            tick: Tick data dict with LTP, depth, etc.
        """

    @abstractmethod
    async def on_order_update(self, update: dict[str, Any]) -> None:
        """Handle order update (fill, rejection, etc.).

        Args:
            update: Order update dict
        """

    @abstractmethod
    async def start(self) -> None:
        """Start the strategy — initialize state, subscribe to data."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the strategy — close positions, cancel orders."""
