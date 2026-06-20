"""
Unit tests for Broker Abstraction Layer (Phase 2).

Covers:
- BrokerInterface abstract class
- KiteBroker (Zerodha) implementation
- AngelBroker stub
- DhanBroker stub
- Rate limiting
- Error handling

Author: SBITB-150626
"""

from __future__ import annotations

import pytest

from src.brokers.base import BrokerInterface

# ─────────────────────────────────────────────────────────────────────────────
# Test BrokerInterface Abstract Class
# ─────────────────────────────────────────────────────────────────────────────


class TestBrokerInterface:
    """Tests for BrokerInterface abstract class."""

    def test_interface_is_abstract(self):
        """BrokerInterface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BrokerInterface()

    def test_interface_has_required_methods(self):
        """BrokerInterface should have all required abstract methods."""
        required_methods = [
            "authenticate",
            "place_order",
            "cancel_order",
            "cancel_all_orders",
            "get_positions",
            "get_margins",
            "get_order_book",
            "get_instruments",
            "get_option_chain",
            "subscribe_ticks",
            "get_historical_candles",
            "get_quote",
        ]

        for method in required_methods:
            assert hasattr(BrokerInterface, method), f"Missing method: {method}"
            assert getattr(BrokerInterface, method).__isabstractmethod__, f"{method} should be abstract"


# ─────────────────────────────────────────────────────────────────────────────
# Test KiteBroker Implementation
# ─────────────────────────────────────────────────────────────────────────────


class TestKiteBroker:
    """Tests for KiteBroker (Zerodha) implementation."""

    def test_kite_broker_raises_import_error(self):
        """KiteBroker should raise ImportError when kiteconnect not installed."""
        try:
            from src.brokers.zerodha import KiteBroker
        except ImportError:
            pytest.skip("kiteconnect package not installed")

        # If import succeeds, check that instantiation raises ImportError
        # when kiteconnect is not available
        from src.brokers import zerodha as zerodha_module

        original_kite = zerodha_module.KiteConnect
        zerodha_module.KiteConnect = None

        try:
            with pytest.raises(ImportError, match="kiteconnect package is required"):
                KiteBroker(api_key="test_api_key", api_secret="test_api_secret")
        finally:
            zerodha_module.KiteConnect = original_kite


# ─────────────────────────────────────────────────────────────────────────────
# Test Stub Brokers
# ─────────────────────────────────────────────────────────────────────────────


class TestStubBrokers:
    """Tests for stub broker implementations."""

    @pytest.mark.asyncio
    async def test_angel_broker_raises_not_implemented(self):
        """AngelBroker should raise NotImplementedError."""
        from src.brokers.angelone import AngelBroker

        broker = AngelBroker(
            api_key="test_key",
            client_id="test_client",
            password="test_password",
            totp_secret="test_secret",
        )

        with pytest.raises(NotImplementedError, match="Phase 16"):
            await broker.authenticate()

    @pytest.mark.asyncio
    async def test_angel_broker_get_quote_raises(self):
        """AngelBroker.get_quote() should raise NotImplementedError."""
        from src.brokers.angelone import AngelBroker

        broker = AngelBroker(
            api_key="test_key",
            client_id="test_client",
            password="test_password",
            totp_secret="test_secret",
        )

        with pytest.raises(NotImplementedError, match="Phase 16"):
            await broker.get_quote(["NSE:NIFTY"])

    @pytest.mark.asyncio
    async def test_angel_broker_place_order_raises(self):
        """AngelBroker.place_order() should raise NotImplementedError."""
        from src.brokers.angelone import AngelBroker

        broker = AngelBroker(
            api_key="test_key",
            client_id="test_client",
            password="test_password",
            totp_secret="test_secret",
        )

        with pytest.raises(NotImplementedError, match="Phase 16"):
            await broker.place_order({})

    @pytest.mark.asyncio
    async def test_dhan_raises_not_implemented(self):
        """DhanBroker should raise NotImplementedError."""
        from src.brokers.dhan import DhanBroker

        broker = DhanBroker(client_id="test_client")
        with pytest.raises(NotImplementedError):
            await broker.authenticate()

    @pytest.mark.asyncio
    async def test_dhan_place_order_raises(self):
        """DhanBroker.place_order() should raise NotImplementedError."""
        from src.brokers.dhan import DhanBroker

        broker = DhanBroker(client_id="test_client")
        with pytest.raises(NotImplementedError):
            await broker.place_order({})
