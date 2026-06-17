"""Abstract market data provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    import pandas as pd


# Stub for pandas DataFrame to avoid import issues in non-strict mode
class DataFrame:
    """Stub for pandas DataFrame."""

    pass


class MarketDataProvider(ABC):
    """Abstract market data provider interface.

    Concrete implementations: Zerodha (Phase 3), Dhan (Phase 14).
    """

    @abstractmethod
    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get current quote for a symbol.

        Args:
            symbol: Instrument symbol

        Returns:
            Quote dict with LTP, depth, etc.
        """

    @abstractmethod
    async def get_historical(self, symbol: str, from_date: date, to_date: date) -> pd.DataFrame:
        """Get historical OHLCV data.

        Args:
            symbol: Instrument symbol
            from_date: Start date
            to_date: End date

        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume
        """

    @abstractmethod
    async def subscribe(self, symbols: list[str], callback: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe to real-time quotes.

        Args:
            symbols: List of symbols to subscribe
            callback: Async callback function called on each tick
        """
