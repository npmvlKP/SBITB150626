"""Abstract broker interface.

Concrete implementations: Zerodha (Phase 3), Angel One (Phase 16), Dhan (Phase 16).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import pandas as pd

__all__ = ["BrokerInterface"]


# Type alias for tick callback
TickCallback = Callable[[list[dict[str, Any]]], Awaitable[None]]


class BrokerInterface(ABC):
    """Abstract broker interface for trading operations.

    Phase 0 base methods + Phase 2 additions for F&O data pipeline.
    """

    # =========================================================================
    # Phase 0: Core Authentication & Order Management
    # =========================================================================

    @abstractmethod
    async def authenticate(self) -> str:
        """Authenticate with the broker and return access token.

        Returns:
            str: Access token for authenticated session
        """
        pass

    @abstractmethod
    async def place_order(self, params: dict[str, Any]) -> dict[str, Any]:
        """Place a new order with the broker.

        Args:
            params: Order parameters including symbol, quantity, order type, etc.

        Returns:
            dict: Order confirmation response
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> dict[str, Any]:
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

    # =========================================================================
    # Phase 2: F&O Data Pipeline Additions
    # =========================================================================

    @abstractmethod
    async def get_option_chain(self, symbol: str, expiry: date) -> list[dict[str, Any]]:
        """Fetch available option contracts for a symbol and expiry date.

        Args:
            symbol: Underlying symbol (e.g., 'NIFTY', 'BANKNIFTY')
            expiry: Expiry date for the options

        Returns:
            list[dict]: List of option contracts with strike, type, instrument_token, etc.
        """
        pass

    @abstractmethod
    async def subscribe_ticks(
        self,
        instruments: list[int],
        mode: str,
        callback: TickCallback,
    ) -> None:
        """Subscribe to live market data via WebSocket.

        Args:
            instruments: List of instrument tokens to subscribe
            mode: Tick mode ('ltp', 'quote', 'depth')
            callback: Async callback function to receive tick data

        Note:
            This is handled by LiveMarketFeed (Phase 7).
            Broker implementation provides access_token + instrument list.
        """
        pass

    @abstractmethod
    async def get_historical_candles(
        self,
        instrument_token: int,
        interval: str,
        from_date: date,
        to_date: date,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV candles.

        Args:
            instrument_token: Instrument token for the instrument
            interval: Candle interval (e.g., '1minute', '5minute', 'day')
            from_date: Start date for historical data
            to_date: End date for historical data

        Returns:
            pd.DataFrame: DataFrame with columns [timestamp, open, high, low, close, volume]
        """
        pass

    @abstractmethod
    async def get_quote(self, instruments: list[str]) -> dict[str, Any]:
        """Fetch current quote for instruments.

        Args:
            instruments: List of instrument strings (e.g., 'NSE:RELIANCE')

        Returns:
            dict: Dictionary mapping instrument to quote data (OHLC, LTP, depth, etc.)
        """
        pass
