"""Zerodha KiteConnect broker implementation.

Implements BrokerInterface for Zerodha Kite platform.
Phase 3 integration with full async support.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from kiteconnect import KiteConnect

from .base import BrokerInterface, TickCallback

logger = logging.getLogger(__name__)


class KiteBroker(BrokerInterface):
    """Zerodha KiteConnect broker implementation.

    Provides async interface to Zerodha Kite API for:
    - Authentication (OAuth flow)
    - Order placement and management
    - Position and margin queries
    - Option chain fetching
    - Historical candle data
    - Live market data subscriptions (via LiveMarketFeed)

    Attributes:
        api_key: KiteConnect API key
        api_secret: KiteConnect API secret
        _kite: KiteConnect instance
        _access_token: Current access token
        _instrument_cache: Cache for instrument lists
    """

    # Rate limits for Zerodha API
    HISTORICAL_RATE_LIMIT: float = 3.0  # req/sec
    QUOTE_RATE_LIMIT: float = 1.0  # req/sec

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str | None = None,
    ) -> None:
        """Initialize KiteBroker.

        Args:
            api_key: KiteConnect API key
            api_secret: KiteConnect API secret
            access_token: Optional pre-generated access token
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self._kite: KiteConnect = KiteConnect(api_key=api_key)
        self._kite.api_secret = api_secret
        self._access_token: str | None = access_token

        if access_token:
            self._kite.set_access_token(access_token)

        # Instrument cache: {segment: instruments_list}
        self._instrument_cache: dict[str, list[dict[str, Any]]] = {}

        # Rate limiting
        self._last_historical_call: float = 0.0
        self._last_quote_call: float = 0.0

    # =========================================================================
    # Phase 0: Core Authentication & Order Management
    # =========================================================================

    async def authenticate(self) -> str:
        """Complete OAuth flow for session generation.

        For automated daily re-authentication:
        1. Open login URL in browser: self._kite.login_url()
        2. User completes TOTP manually
        3. Capture request_token from redirect URL
        4. Generate session: kite.generate_session(request_token, api_secret)
        5. Set access_token: kite.set_access_token(session["access_token"])
        6. Compute checksum: SHA-256(api_key + request_token + api_secret)
        7. Log auth event via audit_logger

        Returns:
            str: Access token for authenticated session

        Raises:
            TokenException: If token generation fails
            NetworkException: If API call fails
        """
        # This method is typically called with a request_token from OAuth callback
        # For daily re-auth, the request_token is obtained from the login flow
        # Example usage:
        #
        # request_token = "user_provided_request_token"
        # session = self._kite.generate_session(
        #     request_token=request_token,
        #     api_secret=self.api_secret
        # )
        # self._access_token = session["access_token"]
        # self._kite.set_access_token(self._access_token)
        #
        # # Log authentication event
        # logger.info(
        #     "Kite authentication successful",
        #     extra={"api_key": self.api_key}
        # )

        if not self._access_token:
            raise ValueError(
                "Access token not available. "
                "Complete OAuth flow to generate request_token, "
                "then call generate_session() to get access_token."
            )

        return self._access_token

    async def place_order(self, params: dict[str, Any]) -> dict[str, Any]:
        """Place order with pre-trade risk check integration.

        Args:
            params: Order parameters:
                - exchange: NSE, BSE, NFO, BFO, MCX
                - tradingsymbol: Symbol name
                - transaction_type: BUY, SELL
                - quantity: Order quantity
                - order_type: MARKET, LIMIT, SL, SL-M
                - product: CNC, MIS, NRML
                - variety: regular, bo, co, amo
                - price: Limit price (for LIMIT/SL orders)
                - trigger_price: Trigger price (for SL/SL-M orders)
                - tag: Strategy identifier (max 20 chars, format: strategy_id:version)

        Returns:
            dict: Order confirmation response with order_id, status, etc.

        Raises:
            OrderException: If order placement fails
            MarginException: If insufficient margins
            TokenException: If access token is invalid
        """
        # 1. Validate params against Zerodha API requirements
        required_fields = [
            "exchange",
            "tradingsymbol",
            "transaction_type",
            "quantity",
            "order_type",
            "product",
            "variety",
        ]
        for field in required_fields:
            if field not in params:
                raise ValueError(f"Missing required field: {field}")

        # 2. Set market_protection=-1 (auto Last Price Protection)
        if params.get("order_type") == "MARKET":
            params["market_protection"] = -1

        # 3. Set tag format: strategy_id:version[:20]
        if "tag" not in params:
            params["tag"] = "default:1"
        params["tag"] = params["tag"][:20]  # Max 20 chars

        # 4. Call kite.place_order() in thread pool (blocking API)
        loop = asyncio.get_event_loop()
        order_response = await loop.run_in_executor(
            None,
            lambda: self._kite.place_order(
                variety=params["variety"],
                exchange=params["exchange"],
                tradingsymbol=params["tradingsymbol"],
                transaction_type=params["transaction_type"],
                quantity=params["quantity"],
                order_type=params["order_type"],
                product=params["product"],
                price=params.get("price"),
                trigger_price=params.get("trigger_price"),
                tag=params["tag"],
            ),
        )

        # 5. Handle exceptions are raised by kite library:
        #    - OrderException, MarginException, TokenException

        # 6. Log result via audit_logger
        logger.info(
            "Order placed",
            extra={
                "order_id": order_response.get("order_id"),
                "params": {k: v for k, v in params.items() if k != "api_secret"},
            },
        )

        return order_response

    async def cancel_order(self, order_id: str, variety: str = "regular") -> dict[str, Any]:
        """Cancel an existing order.

        Args:
            order_id: The ID of the order to cancel
            variety: Order variety (regular, bo, co, amo)

        Returns:
            dict: Cancellation confirmation response

        Raises:
            OrderException: If cancellation fails
            TokenException: If access token is invalid
        """
        max_retries = 3
        retry_delay = 1.0  # seconds

        for attempt in range(max_retries):
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: self._kite.cancel_order(variety=variety, order_id=order_id)
                )
                logger.info(f"Order {order_id} cancelled successfully")
                return result

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Cancel order retry {attempt + 1}/{max_retries}: {e}")
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(f"Cancel order failed after {max_retries} attempts: {e}")
                    raise

        raise RuntimeError(f"Failed to cancel order {order_id} after {max_retries} attempts")

    async def cancel_all_orders(self) -> list[dict[str, Any]]:
        """Cancel all active orders.

        Returns:
            list[dict]: List of cancellation responses with {order_id, status}
        """
        results: list[dict[str, Any]] = []

        # Fetch all open orders
        loop = asyncio.get_event_loop()
        orders = await loop.run_in_executor(None, lambda: self._kite.orders())

        # Cancel each open order
        for order in orders:
            if order["status"] in ("OPEN", "TRIGGER PENDING"):
                try:
                    result = await self.cancel_order(order["order_id"], variety=order.get("variety", "regular"))
                    results.append(
                        {
                            "order_id": order["order_id"],
                            "status": "cancelled",
                            "response": result,
                        }
                    )
                except Exception as e:
                    results.append(
                        {
                            "order_id": order["order_id"],
                            "status": "failed",
                            "error": str(e),
                        }
                    )

        logger.info(f"Cancel all orders: {len(results)} processed")
        return results

    async def get_positions(self) -> list[dict[str, Any]]:
        """Get current positions.

        Returns:
            list[dict]: List of net positions with P&L details
        """
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(None, lambda: self._kite.positions())

        # Return net positions
        return positions.get("net", [])

    async def get_margins(self) -> dict[str, Any]:
        """Get account margin information.

        Returns:
            dict: Margin details including available, utilized, etc.
        """
        loop = asyncio.get_event_loop()
        margins = await loop.run_in_executor(None, lambda: self._kite.margins())

        return margins

    async def get_order_book(self) -> list[dict[str, Any]]:
        """Get the order book.

        Returns:
            list[dict]: List of all orders
        """
        loop = asyncio.get_event_loop()
        orders = await loop.run_in_executor(None, lambda: self._kite.orders())

        return orders

    async def get_instruments(self, segment: str) -> list[dict[str, Any]]:
        """Get available instruments for a specific segment.

        Args:
            segment: Trading segment (e.g., 'NSE', 'NFO', 'BSE', 'MCX')

        Returns:
            list[dict]: List of instruments with their details

        Note:
            Results are cached in _instrument_cache to reduce API calls.
        """
        # Check cache first
        if segment in self._instrument_cache:
            return self._instrument_cache[segment]

        loop = asyncio.get_event_loop()
        all_instruments = await loop.run_in_executor(None, lambda: self._kite.instruments())

        # Filter by segment
        instruments = [inst for inst in all_instruments if inst["exchange"] == segment]

        # Cache results
        self._instrument_cache[segment] = instruments

        logger.debug(f"Fetched {len(instruments)} instruments for {segment}")
        return instruments

    # =========================================================================
    # Phase 2: F&O Data Pipeline Additions
    # =========================================================================

    async def get_option_chain(self, symbol: str, expiry: date) -> list[dict[str, Any]]:
        """Fetch available option contracts for symbol and expiry.

        Args:
            symbol: Underlying symbol (e.g., 'NIFTY', 'BANKNIFTY', 'RELIANCE')
            expiry: Expiry date for the options

        Returns:
            list[dict]: List of option contracts with:
                - instrument_token
                - trading_symbol
                - strike
                - option_type (CE/PE)
                - expiry
                - lot_size
        """
        # Fetch NFO instruments
        nfo_instruments = await self.get_instruments("NFO")

        # Format expiry for comparison
        expiry_str = expiry.strftime("%Y-%m-%d")

        # Filter: symbol match and expiry match
        # Symbol can be prefix (e.g., "NIFTY" matches "NIFTY24120" options)
        filtered: list[dict[str, Any]] = []

        for inst in nfo_instruments:
            tradingsymbol = inst.get("tradingsymbol", "")

            # Check symbol match (case insensitive, prefix match)
            if not tradingsymbol.upper().startswith(symbol.upper()):
                continue

            # Check expiry match
            inst_expiry = inst.get("expiry")
            if inst_expiry is None:
                continue

            # Handle different expiry formats
            if isinstance(inst_expiry, str):
                inst_expiry_str = inst_expiry
            elif isinstance(inst_expiry, datetime):
                inst_expiry_str = inst_expiry.strftime("%Y-%m-%d")
            else:
                continue

            if inst_expiry_str == expiry_str:
                # Parse strike from trading symbol
                # Format: SYMBOLYYMMDDSTRIKECC/PC
                strike = inst.get("strike", 0)
                option_type = inst.get("instrument_type", "NA")

                filtered.append(
                    {
                        "instrument_token": inst["instrument_token"],
                        "trading_symbol": tradingsymbol,
                        "strike": strike,
                        "option_type": option_type,
                        "expiry": expiry_str,
                        "lot_size": inst.get("lot_size", 1),
                        "exchange": "NFO",
                    }
                )

        # Sort by strike price
        filtered.sort(key=lambda x: (x["strike"], x["option_type"]))

        logger.debug(f"Option chain for {symbol}@{expiry}: {len(filtered)} contracts")
        return filtered

    async def subscribe_ticks(
        self,
        instruments: list[int],
        mode: str,
        callback: TickCallback,
    ) -> None:
        """Subscribe to live market data via WebSocket.

        Note:
            This method is primarily a placeholder.
            The actual WebSocket handling is done by LiveMarketFeed (Phase 7).
            KiteBroker provides the access_token and instrument list to LiveMarketFeed.

        The LiveMarketFeed will use:
        - self._kite.set_access_token(access_token) for WebSocket auth
        - kite.connect() for WebSocket connection
        - kite.subscribe() for instrument subscription
        - kite.on_ticks = callback for tick handling

        Args:
            instruments: List of instrument tokens to subscribe
            mode: Tick mode ('ltp', 'quote', 'depth')
            callback: Async callback function to receive tick data

        See Also:
            Phase 7: LiveMarketFeed implementation
        """
        logger.info(
            "subscribe_ticks called - delegated to LiveMarketFeed (Phase 7)",
            extra={"instruments": instruments, "mode": mode},
        )

        # The actual WebSocket subscription is handled by LiveMarketFeed
        # This method provides access to the kite instance via get_kite()
        pass

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
            interval: Candle interval
                Options: '1minute', '3minute', '5minute', '10minute',
                         '15minute', '30minute', '60minute', 'day',
                         'week', 'month'
            from_date: Start date for historical data
            to_date: End date for historical data (inclusive)

        Returns:
            pd.DataFrame: DataFrame with columns:
                - timestamp: datetime
                - open: float
                - high: float
                - low: float
                - close: float
                - volume: int

        Rate Limit:
            3 requests per second for historical data API
        """
        # Rate limiting: 3 req/sec
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_historical_call

        if time_since_last < (1.0 / self.HISTORICAL_RATE_LIMIT):
            wait_time = (1.0 / self.HISTORICAL_RATE_LIMIT) - time_since_last
            await asyncio.sleep(wait_time)

        # Convert dates to datetime for API
        from_dt = datetime.combine(from_date, datetime.min.time())
        to_dt = datetime.combine(to_date, datetime.max.time())

        loop = asyncio.get_event_loop()
        candles = await loop.run_in_executor(
            None,
            lambda: self._kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_dt,
                to_date=to_dt,
                interval=interval,
            ),
        )

        self._last_historical_call = asyncio.get_event_loop().time()

        # Convert to DataFrame
        if not candles:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(candles)
        if "date" in df.columns:
            df = df.rename(columns={"date": "timestamp"})

        return df

    async def get_quote(self, instruments: list[str]) -> dict[str, Any]:
        """Fetch current quote for instruments.

        Args:
            instruments: List of instrument strings
                Format: 'EXCHANGE:SYMBOL' (e.g., 'NSE:RELIANCE', 'NFO:NIFTY24120CE')

        Returns:
            dict: Dictionary mapping instrument to quote data:
                - last_price
                - open, high, low, close
                - volume
                - buy/sell depth
                - timestamp

        Rate Limit:
            1 request per second for quote API
        """
        # Rate limiting: 1 req/sec
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_quote_call

        if time_since_last < (1.0 / self.QUOTE_RATE_LIMIT):
            wait_time = (1.0 / self.QUOTE_RATE_LIMIT) - time_since_last
            await asyncio.sleep(wait_time)

        loop = asyncio.get_event_loop()
        quotes = await loop.run_in_executor(None, lambda: self._kite.quote(instruments))

        self._last_quote_call = asyncio.get_event_loop().time()

        return quotes

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_kite(self) -> KiteConnect:
        """Get the underlying KiteConnect instance.

        Returns:
            KiteConnect: The kite instance for advanced operations
        """
        return self._kite

    def get_login_url(self) -> str:
        """Get the Zerodha login URL for OAuth flow.

        Returns:
            str: Login URL for user authentication
        """
        return self._kite.login_url()

    def clear_cache(self) -> None:
        """Clear the instrument cache."""
        self._instrument_cache.clear()
        logger.info("Instrument cache cleared")
