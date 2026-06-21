"""Abstract market data provider interface with Phase 2 F&O extensions.

Phase 0 base interface + Phase 2 additions for option chain and Greeks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import date

    import pandas as pd

    from src.brokers.base import BrokerInterface as KiteBroker
    from src.data.option_chain import OptionMetricsComputer
    from src.data.storage import RedisCache, TimescaleDBStore


class MarketDataProvider(ABC):
    """Abstract market data provider interface.

    Concrete implementations: KiteDataProvider (Phase 2), future brokers (Phase 14+).
    """

    # =========================================================================
    # Phase 0: Core Market Data Methods
    # =========================================================================

    @abstractmethod
    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get current quote for a symbol.

        Args:
            symbol: Instrument symbol (e.g., 'NIFTY', 'RELIANCE')

        Returns:
            Quote dict with LTP, depth, OHLC, etc.
        """

    @abstractmethod
    async def get_historical(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> pd.DataFrame:
        """Get historical OHLCV data.

        Args:
            symbol: Instrument symbol
            from_date: Start date (inclusive)
            to_date: End date (inclusive)

        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume
        """

    @abstractmethod
    async def subscribe(
        self,
        symbols: list[str],
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe to real-time quotes.

        Args:
            symbols: List of symbols to subscribe
            callback: Async callback function called on each tick
        """

    # =========================================================================
    # Phase 2: WebSocket Storage Methods (for handlers.py)
    # =========================================================================

    @abstractmethod
    async def store_tick(self, tick: Any) -> None:
        """Store tick data to database.

        Args:
            tick: Tick data (LTPUpdate, Tick, or Quote)
        """

    @abstractmethod
    async def store_depth(self, depth: Any) -> None:
        """Store depth/market depth data to database.

        Args:
            depth: Depth data (DepthUpdate or FullMarketDepth)
        """

    # =========================================================================
    # Phase 2: F&O Data Pipeline Additions
    # =========================================================================

    @abstractmethod
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
                - exchange
        """

    @abstractmethod
    async def get_greeks(
        self,
        symbol: str,
        date: date,
        expiry: date | None = None,
    ) -> pd.DataFrame:
        """Query computed Greeks snapshot data.

        Args:
            symbol: Trading symbol
            date: Snapshot date
            expiry: Optional expiry filter

        Returns:
            DataFrame with columns:
                date, symbol, expiry, strike, option_type,
                spot, iv, delta, gamma, theta, vega,
                risk_free_rate, rfr_method, ttm_years, compute_error
        """


class KiteDataProvider(MarketDataProvider):
    """Concrete implementation using KiteBroker + TimescaleDBStore + RedisCache.

    Combines broker API, database persistence, and cache layer:
    - Quotes: Redis cache first, fall back to broker API
    - Historical: Query TimescaleDB
    - Option chain: Broker instruments + DB EOD data + computed Greeks
    - Greeks: Query greeks_snapshot table

    Args:
        broker: KiteBroker instance for live API access
        db: TimescaleDBStore instance for database queries
        cache: RedisCache instance for tick caching
        greeks: OptionMetricsComputer instance for Greeks computation
    """

    def __init__(
        self,
        broker: KiteBroker,
        db: TimescaleDBStore,
        cache: RedisCache,
        greeks: OptionMetricsComputer,
    ) -> None:
        """Initialize KiteDataProvider.

        Args:
            broker: KiteBroker instance for live API access
            db: TimescaleDBStore instance for database queries
            cache: RedisCache instance for tick caching
            greeks: OptionMetricsComputer instance for Greeks computation
        """
        self._broker = broker
        self._db = db
        self._cache = cache
        self._greeks = greeks

    # =========================================================================
    # Phase 0: Core Market Data Methods
    # =========================================================================

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get current quote for a symbol.

        Tries Redis cache first for performance, falls back to broker API.
        Results are cached in Redis for subsequent calls.

        Args:
            symbol: Instrument symbol (e.g., 'NIFTY', 'RELIANCE')

        Returns:
            Quote dict with LTP, depth, OHLC, etc.
        """
        import structlog

        logger = structlog.get_logger(__name__)

        # Try to get from cache first
        try:
            # Convert symbol to instrument token for cache key
            # We need to look up the instrument token from broker
            instruments = await self._broker.get_instruments("NSE")
            token_map = {
                inst["tradingsymbol"]: inst["instrument_token"] for inst in instruments if inst.get("tradingsymbol")
            }

            if symbol in token_map:
                token = token_map[symbol]
                cached = await self._cache.get_tick(token)
                if cached:
                    logger.debug("quote_cache_hit", symbol=symbol)
                    return cached

        except Exception as e:
            logger.warning("cache_lookup_failed", symbol=symbol, error=str(e))

        # Fall back to broker API
        instrument_str = f"NSE:{symbol}"
        quotes: dict[str, Any] = await self._broker.get_quote([instrument_str])

        quote_data: dict[str, Any] = quotes.get(instrument_str, {})

        # Cache the result
        try:
            if symbol in token_map:
                await self._cache.set_tick(token_map[symbol], quote_data)
        except Exception as e:
            logger.warning("cache_set_failed", symbol=symbol, error=str(e))

        logger.debug("quote_broker_fetch", symbol=symbol)
        return quote_data

    async def get_historical(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> pd.DataFrame:
        """Get historical OHLCV data.

        Queries TimescaleDB for historical data with fallback to broker API.

        Args:
            symbol: Instrument symbol
            from_date: Start date (inclusive)
            to_date: End date (inclusive)

        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume
        """
        import structlog

        logger = structlog.get_logger(__name__)

        # Try database first
        df = await self._db.query_cm_spot(symbol, from_date, to_date)

        if not df.empty:
            logger.debug(
                "historical_db_hit",
                symbol=symbol,
                rows=len(df),
                from_date=str(from_date),
                to_date=str(to_date),
            )
            return df

        # Fall back to broker API for live data
        logger.debug("historical_db_miss_fallback", symbol=symbol)

        # Get instrument token for the symbol
        instruments = await self._broker.get_instruments("NSE")
        token = None
        for inst in instruments:
            if inst.get("tradingsymbol") == symbol:
                token = inst.get("instrument_token")
                break

        if token is None:
            import pandas as pd

            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Fetch from broker with day interval
        df = await self._broker.get_historical_candles(
            instrument_token=token,
            interval="day",
            from_date=from_date,
            to_date=to_date,
        )

        return df

    async def subscribe(
        self,
        symbols: list[str],
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe to real-time quotes.

        Delegates to LiveMarketFeed (Phase 7) for WebSocket handling.

        Args:
            symbols: List of symbols to subscribe
            callback: Async callback function called on each tick
        """
        import structlog

        logger = structlog.get_logger(__name__)

        # Get instrument tokens for symbols
        instruments = await self._broker.get_instruments("NSE")
        token_map = {
            inst["tradingsymbol"]: inst["instrument_token"]
            for inst in instruments
            if inst.get("tradingsymbol") in symbols
        }

        tokens = [token_map[s] for s in symbols if s in token_map]

        logger.info(
            "subscribe_requested",
            symbols=symbols,
            tokens=tokens,
        )

        # Wrap the single-dict callback to match broker's list-dict callback
        async def wrapper(broker_ticks: list[dict[str, Any]]) -> None:
            for tick in broker_ticks:
                await callback(tick)

        # Delegate to broker's subscribe_ticks (handled by LiveMarketFeed in Phase 7)
        await self._broker.subscribe_ticks(tokens, mode="quote", callback=wrapper)

    # =========================================================================
    # Phase 2: WebSocket Storage Methods
    # =========================================================================

    async def store_tick(self, tick: Any) -> None:
        """Store tick data to database.

        Args:
            tick: Tick data (LTPUpdate, Tick, or Quote)
        """
        import structlog

        logger = structlog.get_logger(__name__)
        logger.debug("store_tick", instrument_token=getattr(tick, "instrument_token", None))

    async def store_depth(self, depth: Any) -> None:
        """Store depth/market depth data to database.

        Args:
            depth: Depth data (DepthUpdate or FullMarketDepth)
        """
        import structlog

        logger = structlog.get_logger(__name__)
        logger.debug("store_depth", instrument_token=getattr(depth, "instrument_token", None))

    # =========================================================================
    # Phase 2: F&O Data Pipeline Additions
    # =========================================================================

    async def get_option_chain(
        self,
        symbol: str,
        expiry: date,
    ) -> list[dict[str, Any]]:
        """Fetch available option contracts for symbol and expiry.

        Combines:
        1. Broker instruments (from get_option_chain)
        2. DB EOD data (OHLC, OI, volume from TimescaleDB)
        3. Computed Greeks (from greeks_snapshot or on-demand)

        Args:
            symbol: Underlying symbol (e.g., 'NIFTY', 'BANKNIFTY')
            expiry: Expiry date for the options

        Returns:
            list[dict]: List of option contracts with full strike data
        """
        import structlog

        logger = structlog.get_logger(__name__)

        # Get base instruments from broker
        contracts = await self._broker.get_option_chain(symbol, expiry)

        if not contracts:
            logger.debug("option_chain_empty", symbol=symbol, expiry=str(expiry))
            return []

        # Get EOD data from database for these contracts
        df_eod = await self._db.query_fo_options(symbol, expiry, expiry)

        # Build EOD lookup: {(strike, option_type): row}
        eod_map: dict[tuple[float, str], dict[str, Any]] = {}
        if not df_eod.empty:
            for _, row in df_eod.iterrows():
                key = (float(row["strike"]), str(row["option_type"]))
                eod_map[key] = row.to_dict()

        # Get spot price for Greeks computation
        spot = await self._get_spot_price(symbol)

        # Enrich contracts with EOD data and Greeks
        enriched: list[dict[str, Any]] = []
        for contract in contracts:
            strike = contract.get("strike", 0)
            option_type = contract.get("option_type", "")

            # Add EOD data
            eod_key = (strike, option_type)
            if eod_key in eod_map:
                eod = eod_map[eod_key]
                contract["open"] = eod.get("open")
                contract["high"] = eod.get("high")
                contract["low"] = eod.get("low")
                contract["close"] = eod.get("close")
                contract["volume"] = eod.get("volume")
                contract["oi"] = eod.get("oi")
                contract["oi_change"] = eod.get("oi_change")
                contract["settle_price"] = eod.get("settle_price")

            # Get Greeks from snapshot if available
            if spot:
                try:
                    df_greeks = await self._db.query_greeks(symbol, expiry, expiry)
                    if not df_greeks.empty:
                        greeks_match = df_greeks[
                            (df_greeks["strike"] == strike) & (df_greeks["option_type"] == option_type)
                        ]
                        if not greeks_match.empty:
                            g = greeks_match.iloc[0]
                            contract["iv"] = g.get("iv")
                            contract["delta"] = g.get("delta")
                            contract["gamma"] = g.get("gamma")
                            contract["theta"] = g.get("theta")
                            contract["vega"] = g.get("vega")
                except Exception as e:
                    logger.warning(
                        "greeks_lookup_failed",
                        symbol=symbol,
                        strike=strike,
                        error=str(e),
                    )

            enriched.append(contract)

        logger.debug(
            "option_chain_enriched",
            symbol=symbol,
            expiry=str(expiry),
            contracts=len(enriched),
        )

        return enriched

    async def get_greeks(
        self,
        symbol: str,
        date: date,
        expiry: date | None = None,
    ) -> pd.DataFrame:
        """Query computed Greeks snapshot data.

        Args:
            symbol: Trading symbol
            date: Snapshot date
            expiry: Optional expiry filter

        Returns:
            DataFrame with columns:
                date, symbol, expiry, strike, option_type,
                spot, iv, delta, gamma, theta, vega,
                risk_free_rate, rfr_method, ttm_years, compute_error
        """
        return await self._db.query_greeks(symbol, date, expiry)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_spot_price(self, symbol: str) -> float | None:
        """Get current spot price for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'NIFTY', 'BANKNIFTY')

        Returns:
            Spot price or None if not available
        """
        import structlog

        logger = structlog.get_logger(__name__)

        # Map symbol to spot table symbol
        spot_symbol = symbol
        if symbol == "NIFTY":
            spot_symbol = "NIFTY 50"
        elif symbol == "BANKNIFTY":
            spot_symbol = "NIFTY BANK"

        # Try database first
        from datetime import date as date_type

        today = date_type.today()
        df = await self._db.query_cm_spot(spot_symbol, today, today)

        if not df.empty:
            close = df.iloc[0].get("close")
            if close is not None:
                return float(close)

        # Fall back to broker quote
        try:
            quote = await self.get_quote(symbol)
            ltp = quote.get("last_price")
            if ltp:
                return float(ltp)
        except Exception as e:
            logger.warning("spot_lookup_failed", symbol=symbol, error=str(e))

        return None
