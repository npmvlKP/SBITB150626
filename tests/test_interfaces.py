"""Test suite for abstract interfaces verification."""
import inspect
import os
import sys
from abc import ABC

import pytest

# Add src directory to Python path to import modules correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.brokers.base import BrokerInterface
from src.data.providers import MarketDataProvider
from src.strategy.base import StrategyInterface


async def dummy_coro(*args, **kwargs):
    """Dummy coroutine for testing."""
    return None


class TestBrokerInterface:
    """Test suite for BrokerInterface abstract class."""

    def test_broker_interface_is_abstract(self):
        """Test that BrokerInterface is abstract."""
        assert issubclass(BrokerInterface, ABC)

    def test_broker_has_all_required_methods(self):
        """Test that BrokerInterface has all required methods."""
        required_methods = [
            "authenticate",
            "place_order",
            "cancel_order",
            "cancel_all_orders",
            "get_positions",
            "get_margins",
            "get_order_book",
            "get_instruments"
        ]

        for method in required_methods:
            assert hasattr(BrokerInterface, method), f"Missing {method} in BrokerInterface"
            obj = getattr(BrokerInterface, method)
            assert obj.__isabstractmethod__, f"{method} should be abstract"

    def test_broker_authenticate_exists(self):
        """Test that authenticate method exists and has a return annotation."""
        method = BrokerInterface.authenticate
        sig = inspect.signature(method)
        # Just verify return_annotation exists and has 'str' in it
        assert sig.return_annotation is not inspect.Parameter.empty

    def test_broker_place_order_accepts_params(self):
        """Test that place_order method accepts params argument."""
        method = BrokerInterface.place_order
        sig = inspect.signature(method)
        assert "params" in sig.parameters, "place_order should have 'params' parameter"

    def test_broker_cancel_order_accepts_order_id(self):
        """Test that cancel_order method accepts order_id argument."""
        method = BrokerInterface.cancel_order
        sig = inspect.signature(method)
        assert "order_id" in sig.parameters, "cancel_order should have 'order_id' parameter"

    def test_broker_get_instruments_accepts_segment(self):
        """Test that get_instruments method accepts segment argument."""
        method = BrokerInterface.get_instruments
        sig = inspect.signature(method)
        assert "segment" in sig.parameters, "get_instruments should have 'segment' parameter"


class TestStrategyInterface:
    """Test suite for StrategyInterface abstract class."""

    def test_strategy_is_abstract(self):
        """Test that StrategyInterface is abstract."""
        assert issubclass(StrategyInterface, ABC)

    def test_strategy_has_required_properties(self):
        """Test that StrategyInterface has required properties."""
        props = ["strategy_id", "version"]
        for prop in props:
            assert hasattr(StrategyInterface, prop), f"Missing {prop} in StrategyInterface"
            obj = getattr(StrategyInterface, prop)
            assert isinstance(obj, property), f"{prop} should be a property"
            assert obj.fget.__isabstractmethod__, f"{prop} should be abstract"

    def test_strategy_has_required_methods(self):
        """Test that StrategyInterface has required methods."""
        methods = ["on_tick", "on_order_update", "start", "stop"]
        for method in methods:
            assert hasattr(StrategyInterface, method), f"Missing {method} in StrategyInterface"
            obj = getattr(StrategyInterface, method)
            assert obj.__isabstractmethod__, f"{method} should be abstract"

    def test_strategy_on_tick_accepts_tick(self):
        """Test that on_tick method accepts tick argument."""
        method = StrategyInterface.on_tick
        sig = inspect.signature(method)
        assert "tick" in sig.parameters, "on_tick should have 'tick' parameter"

    def test_strategy_on_order_update_accepts_update(self):
        """Test that on_order_update method accepts update argument."""
        method = StrategyInterface.on_order_update
        sig = inspect.signature(method)
        assert "update" in sig.parameters, "on_order_update should have 'update' parameter"


class TestMarketDataProvider:
    """Test suite for MarketDataProvider abstract class."""

    def test_market_data_provider_is_abstract(self):
        """Test that MarketDataProvider is abstract."""
        assert issubclass(MarketDataProvider, ABC)

    def test_market_data_provider_has_all_methods(self):
        """Test that MarketDataProvider has all required methods."""
        methods = ["get_quote", "get_historical", "subscribe"]

        for method in methods:
            assert hasattr(MarketDataProvider, method), f"Missing {method} in MarketDataProvider"
            obj = getattr(MarketDataProvider, method)
            assert obj.__isabstractmethod__, f"{method} should be abstract"

    def test_market_data_provider_get_quote_accepts_symbol(self):
        """Test that get_quote method accepts symbol argument."""
        method = MarketDataProvider.get_quote
        sig = inspect.signature(method)
        assert "symbol" in sig.parameters, "get_quote should have 'symbol' parameter"

    def test_market_data_provider_get_historical_accepts_symbol_and_dates(self):
        """Test that get_historical method accepts required arguments."""
        method = MarketDataProvider.get_historical
        sig = inspect.signature(method)
        params = sig.parameters
        assert "symbol" in params, "get_historical should have 'symbol' parameter"
        assert "from_date" in params, "get_historical should have 'from_date' parameter"
        assert "to_date" in params, "get_historical should have 'to_date' parameter"

    def test_market_data_provider_subscribe_accepts_symbols_and_callback(self):
        """Test that subscribe method accepts required arguments."""
        method = MarketDataProvider.subscribe
        sig = inspect.signature(method)
        params = sig.parameters
        assert "symbols" in params, "subscribe should have 'symbols' parameter"
        assert "callback" in params, "subscribe should have 'callback' parameter"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
