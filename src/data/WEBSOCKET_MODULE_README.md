# WebSocket Module Documentation

## Overview

The `websocket.py` module provides a comprehensive WebSocket client infrastructure for real-time market data streaming from NSE (National Stock Exchange) and other financial data sources. It's designed for the SBITB-150626 trading platform to handle live market data, option chains, and order book depth.

## Module Structure

### Core Components

1. **Constants** - Configuration parameters for WebSocket connections
2. **Enums** - Type definitions for connection states, message types, and data types
3. **Exceptions** - Custom error handling for WebSocket operations
4. **Dataclasses** - Data structures for messages, ticks, and statistics
5. **Abstract Base Classes** - Interfaces for handlers and subscription managers
6. **Client Classes** - Main WebSocket client implementations
7. **Default Handler** - Built-in market data handler
8. **WebSocket Manager** - Singleton for managing multiple connections

---

## Constants

### WebSocket URLs

- `NSE_WS_URL`: Primary NSE WebSocket endpoint
- `NSE_WS_V2_URL`: NSE WebSocket V2 endpoint
- `NSE_FNO_WS_URL`: NSE F&O (Futures & Options) WebSocket endpoint

### Configuration Parameters

- `DEFAULT_WS_TIMEOUT`: Default connection timeout (30 seconds)
- `DEFAULT_RECONNECT_DELAY`: Delay between reconnection attempts (5 seconds)
- `MAX_RECONNECT_ATTEMPTS`: Maximum number of reconnection attempts (5)
- `MAX_MESSAGE_SIZE`: Maximum message size in bytes (16 MB)
- `PING_INTERVAL`: Heartbeat ping interval (30 seconds)
- `PONG_TIMEOUT`: Timeout waiting for pong response (10 seconds)

---

## Enums

### WebSocketState

Connection state enumeration:

```python
class WebSocketState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSED = "closed"
```

### WebSocketMessageType

Message type classification:

```python
class WebSocketMessageType(Enum):
    TEXT = "text"
    BINARY = "binary"
    PING = "ping"
    PONG = "pong"
    CLOSE = "close"
    ERROR = "error"
```

### MarketDataType

Supported market data types:

```python
class MarketDataType(Enum):
    TICK = "tick"
    DEPTH = "depth"
    INDEX = "index"
    OPTION_CHAIN = "option_chain"
    ORDER_BOOK = "order_book"
    TRADE = "trade"
```

---

## Exceptions

### WebSocketError (Base Exception)

Base class for all WebSocket-related errors.

**Attributes:**
- `code`: Error code
- `message`: Error description
- `details`: Additional error details

### ConnectionError

Raised when connection fails or is lost.

### AuthenticationError

Raised when authentication with the WebSocket server fails.

### SubscriptionError

Raised when subscription to market data fails.

### MessageParseError

Raised when message parsing fails.

### TimeoutError

Raised when WebSocket operations timeout.

### RateLimitError

Raised when rate limits are exceeded.

---

## Dataclasses

### WebSocketMessage

Represents a WebSocket message with parsing capabilities.

**Fields:**
- `data_type`: Message type (TEXT, BINARY, etc.)
- `data`: Raw message data (dict, str, or bytes)
- `timestamp`: When the message was received
- `symbol`: Optional symbol associated with the message
- `sequence_number`: Message sequence number

**Methods:**
- `is_valid()`: Check if message has valid data
- `to_dict()`: Convert to dictionary
- `from_json(cls, json_str)`: Create from JSON string
- `from_bytes(cls, data)`: Create from binary data

### MarketDataTick

Represents a single market data tick/quote.

**Fields:**
- `symbol`: Trading symbol
- `ltp`: Last traded price
- `volume`: Trading volume
- `open`: Opening price
- `high`: High price
- `low`: Low price
- `close`: Closing price
- `bid`: Current bid price
- `ask`: Current ask price
- `bid_qty`: Bid quantity
- `ask_qty`: Ask quantity
- `timestamp`: Tick timestamp
- `exchange`: Exchange name
- `option_type`: Option type (CALL/PUT) for derivatives
- `strike`: Strike price for options
- `expiry`: Expiry date for options
- `iv`: Implied volatility
- `oi`: Open interest
- `change`: Price change
- `pchange`: Percentage change

**Methods:**
- `to_dict()`: Convert to dictionary
- `is_option()`: Check if this is an option tick
- `get_mid_price()`: Calculate mid price

### WebSocketStats

Statistics for WebSocket connection monitoring.

**Fields:**
- `messages_received`: Total messages received
- `messages_sent`: Total messages sent
- `bytes_received`: Total bytes received
- `bytes_sent`: Total bytes sent
- `connection_duration`: Duration of current connection
- `reconnect_count`: Number of reconnection attempts
- `last_message_time`: Timestamp of last message
- `errors`: List of error messages
- `ping_latency`: Last ping-pong latency in ms

**Methods:**
- `reset()`: Reset all statistics
- `to_dict()`: Convert to dictionary
- `get_throughput()`: Calculate message throughput

---

## Abstract Base Classes

### MarketDataHandler (ABC)

Interface for handling market data events.

**Abstract Methods:**
- `on_tick(tick: MarketDataTick)`: Handle tick data
- `on_depth(symbol: str, bids: list, asks: list)`: Handle order book depth
- `on_index(symbol: str, value: float, change: float, pchange: float)`: Handle index updates
- `on_option_chain(symbol: str, expiry: str, strikes: dict)`: Handle option chain data
- `on_error(error: WebSocketError)`: Handle errors
- `on_connection_state_change(state: WebSocketState)`: Handle state changes

### SubscriptionManager (ABC)

Interface for managing WebSocket subscriptions.

**Abstract Methods:**
- `subscribe(symbol: str, data_types: list[MarketDataType])`: Subscribe to data
- `unsubscribe(symbol: str, data_types: list[MarketDataType])`: Unsubscribe
- `get_subscriptions()`: Get current subscriptions
- `is_subscribed(symbol: str, data_type: MarketDataType)`: Check subscription

---

## Client Classes

### WebSocketClient

Base WebSocket client with core functionality.

**Key Features:**
- Automatic reconnection with exponential backoff
- Heartbeat/ping-pong mechanism
- Message parsing and validation
- Connection state management
- Subscription management
- Statistics tracking
- Async message handling

**Constructor Parameters:**
```python
def __init__(
    self,
    url: str,
    handler: MarketDataHandler | None = None,
    timeout: float = DEFAULT_WS_TIMEOUT,
    reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
    max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS,
    ping_interval: float = PING_INTERVAL,
    pong_timeout: float = PONG_TIMEOUT,
    max_message_size: int = MAX_MESSAGE_SIZE,
    auto_reconnect: bool = True,
)
```

**Properties:**
- `url`: WebSocket URL
- `handler`: Market data handler
- `state`: Current connection state
- `stats`: Connection statistics
- `subscribed_symbols`: Set of subscribed symbols
- `subscribed_data_types`: Set of subscribed data types
- `is_connected`: Whether currently connected

**Methods:**

**Connection Management:**
- `connect()`: Establish WebSocket connection
- `disconnect()`: Close WebSocket connection
- `reconnect()`: Reconnect to WebSocket
- `is_connected()`: Check connection status

**Subscription Management:**
- `subscribe(symbol: str, data_types: list[str])`: Subscribe to data
- `unsubscribe(symbol: str, data_types: list[str])`: Unsubscribe
- `get_subscriptions()`: Get current subscriptions
- `clear_subscriptions()`: Clear all subscriptions

**Message Handling:**
- `send(message: dict | str)`: Send message
- `send_json(data: dict)`: Send JSON message
- `send_text(text: str)`: Send text message
- `send_ping()`: Send ping message

**Utility Methods:**
- `reset_stats()`: Reset connection statistics
- `get_stats()`: Get current statistics
- `set_handler(handler: MarketDataHandler)`: Set message handler
- `remove_handler()`: Remove current handler

**Internal Methods:**
- `_connect()`: Internal connection logic
- `_disconnect()`: Internal disconnection logic
- `_send_ping()`: Send ping and wait for pong
- `_handle_message(message)`: Process incoming message
- `_process_message_with_handler(message)`: Route message to handler
- `_validate_message(message)`: Validate message format
- `_handle_connection_error(error)`: Handle connection errors
- `_handle_heartbeat()`: Handle heartbeat logic

### NSEWebSocketClient (Extends WebSocketClient)

Specialized client for NSE (National Stock Exchange) WebSocket API.

**Additional Features:**
- NSE-specific message parsing
- Option chain subscription support
- NSE tick/depth/index message handlers
- Automatic NSE message format detection

**Constructor:**
```python
def __init__(
    self,
    url: str = NSE_WS_URL,
    handler: MarketDataHandler | None = None,
    timeout: float = DEFAULT_WS_TIMEOUT,
    reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
    max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS,
    ping_interval: float = PING_INTERVAL,
    pong_timeout: float = PONG_TIMEOUT,
    max_message_size: int = MAX_MESSAGE_SIZE,
    auto_reconnect: bool = True,
)
```

**NSE-Specific Methods:**
- `subscribe_to_ticks(symbols: list[str])`: Subscribe to tick data
- `subscribe_to_depth(symbols: list[str])`: Subscribe to depth data
- `subscribe_to_index(symbols: list[str])`: Subscribe to index data
- `subscribe_to_option_chain(symbol: str, expiry: str | None = None)`: Subscribe to option chain
- `get_option_chain_data(symbol: str, expiry: str)`: Get option chain data (convenience method)

**NSE Message Handlers:**
- `_handle_nse_tick(data)`: Parse NSE tick messages
- `_handle_nse_depth(data)`: Parse NSE depth messages
- `_handle_nse_index(data)`: Parse NSE index messages
- `_handle_nse_option_chain(data)`: Parse NSE option chain messages

---

## DefaultMarketDataHandler

Concrete implementation of `MarketDataHandler` with callback support.

**Features:**
- Basic logging for all market data events
- Callback registration for each event type
- Error handling for callbacks

**Constructor:**
```python
def __init__(self) -> None:
```

**Callback Registration Methods:**
- `register_tick_callback(callback)`: Register tick event callback
- `register_depth_callback(callback)`: Register depth event callback
- `register_index_callback(callback)`: Register index event callback
- `register_option_chain_callback(callback)`: Register option chain callback
- `register_error_callback(callback)`: Register error event callback
- `register_state_callback(callback)`: Register state change callback

**Handler Methods (MarketDataHandler Implementation):**
- `on_tick(tick)`: Handle tick with logging and callbacks
- `on_depth(symbol, bids, asks)`: Handle depth with logging and callbacks
- `on_index(symbol, value, change, pchange)`: Handle index with logging and callbacks
- `on_option_chain(symbol, expiry, strikes)`: Handle option chain with logging and callbacks
- `on_error(error)`: Handle errors with logging and callbacks
- `on_connection_state_change(state)`: Handle state changes with logging and callbacks

---

## WebSocketManager (Singleton)

Centralized manager for multiple WebSocket connections.

**Features:**
- Singleton pattern for global access
- Manage multiple named WebSocket clients
- Centralized start/stop control
- Automatic cleanup

**Usage:**
```python
# Get the singleton instance
manager = await WebSocketManager.get_instance()

# Start the manager
await manager.start()

# Add a client
client = NSEWebSocketClient()
await manager.add_client("nse", client)

# Get a client
client = await manager.get_client("nse")

# Remove a client
await manager.remove_client("nse")

# Stop all clients
await manager.stop()
```

**Methods:**
- `get_instance()`: Get or create singleton instance
- `start()`: Start the manager
- `stop()`: Stop all clients and manager
- `add_client(name, client)`: Add a named client
- `remove_client(name)`: Remove and disconnect a client
- `get_client(name)`: Get a client by name
- `clients`: Property to get all clients
- `is_running`: Property to check manager state

---

## Usage Examples

### Basic Usage

```python
import asyncio
from src.data.websocket import NSEWebSocketClient, DefaultMarketDataHandler

async def basic_example():
    # Create handler
    handler = DefaultMarketDataHandler()

    # Register callback
    def on_tick_callback(tick):
        print(f"Received tick: {tick.symbol} @ {tick.ltp}")

    handler.register_tick_callback(on_tick_callback)

    # Create client
    client = NSEWebSocketClient(handler=handler)

    # Connect
    await client.connect()

    # Subscribe to data
    await client.subscribe_to_ticks(["NIFTY", "BANKNIFTY"])

    # Wait for data
    await asyncio.sleep(60)

    # Disconnect
    await client.disconnect()

asyncio.run(basic_example())
```

### Using WebSocketManager

```python
import asyncio
from src.data.websocket import (
    WebSocketManager,
    NSEWebSocketClient,
    DefaultMarketDataHandler
)

async def manager_example():
    # Get manager instance
    manager = await WebSocketManager.get_instance()

    # Start manager
    await manager.start()

    # Create and add NSE client
    nse_handler = DefaultMarketDataHandler()
    nse_client = NSEWebSocketClient(handler=nse_handler)
    await manager.add_client("nse", nse_client)

    # Connect and subscribe
    await nse_client.connect()
    await nse_client.subscribe_to_ticks(["RELIANCE", "TCS"])

    # Wait for data
    await asyncio.sleep(60)

    # Cleanup
    await manager.stop()

asyncio.run(manager_example())
```

### Handling Option Chain Data

```python
import asyncio
from src.data.websocket import NSEWebSocketClient, DefaultMarketDataHandler

async def option_chain_example():
    handler = DefaultMarketDataHandler()

    def on_option_chain(symbol, expiry, strikes):
        print(f"Option chain for {symbol} {expiry}:")
        for strike, data in strikes.items():
            print(f"  Strike {strike}: Call={data.get('CE')}, Put={data.get('PE')}")

    handler.register_option_chain_callback(on_option_chain)

    client = NSEWebSocketClient(handler=handler)
    await client.connect()

    # Subscribe to NIFTY option chain
    await client.subscribe_to_option_chain("NIFTY", "2024-12-26")

    await asyncio.sleep(60)
    await client.disconnect()

asyncio.run(option_chain_example())
```

### Custom Handler Implementation

```python
import asyncio
from src.data.websocket import (
    NSEWebSocketClient,
    MarketDataHandler,
    MarketDataTick
)

class MyCustomHandler(MarketDataHandler):
    async def on_tick(self, tick: MarketDataTick) -> None:
        print(f"Custom handler: {tick.symbol} {tick.ltp}")
        # Add custom processing logic here

    async def on_error(self, error) -> None:
        print(f"Error occurred: {error.message}")

async def custom_handler_example():
    handler = MyCustomHandler()
    client = NSEWebSocketClient(handler=handler)

    await client.connect()
    await client.subscribe_to_ticks(["SBIN"])

    await asyncio.sleep(60)
    await client.disconnect()

asyncio.run(custom_handler_example())
```

---

## Error Handling

### Connection Errors

```python
from src.data.websocket import NSEWebSocketClient, ConnectionError

async def handle_connection_errors():
    client = NSEWebSocketClient()

    try:
        await client.connect()
    except ConnectionError as e:
        print(f"Connection failed: {e.message}")
        print(f"Details: {e.details}")
    except Exception as e:
        print(f"Unexpected error: {e}")
```

### Message Parsing Errors

```python
from src.data.websocket import NSEWebSocketClient, MessageParseError

class MyHandler(MarketDataHandler):
    async def on_tick(self, tick: MarketDataTick) -> None:
        try:
            # Process tick
            pass
        except Exception as e:
            print(f"Tick processing failed: {e}")

    async def on_error(self, error: WebSocketError) -> None:
        if isinstance(error, MessageParseError):
            print(f"Message parse error: {error.message}")
            print(f"Raw data: {error.details}")
```

---

## Best Practices

### 1. Connection Management

- Always use `try/finally` or context managers for connections:
  ```python
  try:
      await client.connect()
      # ... use client ...
  finally:
      await client.disconnect()
  ```

- Use WebSocketManager for production applications with multiple connections

### 2. Subscription Management

- Subscribe only to needed symbols and data types
- Unsubscribe when no longer needed to reduce bandwidth
- Use `clear_subscriptions()` when reconnecting to avoid duplicates

### 3. Error Handling

- Always implement `on_error()` in custom handlers
- Handle specific exception types for different error scenarios
- Log errors for debugging and monitoring

### 4. Performance

- Use async callbacks for non-blocking operations
- Avoid heavy processing in message handlers
- Consider batching updates for high-frequency data

### 5. Monitoring

- Use `get_stats()` to monitor connection health
- Track message throughput and latency
- Monitor reconnection attempts and errors

---

## Testing

The module includes comprehensive unit tests in `tests/test_websocket.py` covering:

- WebSocket client connection/disconnection
- Message parsing and validation
- Subscription management
- Error handling
- Reconnection logic
- NSE-specific message parsing
- Handler callback functionality
- WebSocketManager operations

Run tests with:
```bash
pytest tests/test_websocket.py -v
```

---

## Integration

### With Data Pipeline

```python
from src.data.websocket import NSEWebSocketClient, DefaultMarketDataHandler
from src.data.pipeline import DataPipeline

async def integrate_with_pipeline():
    handler = DefaultMarketDataHandler()

    # Connect to pipeline
    pipeline = DataPipeline()

    # Register callback to send data to pipeline
    def on_tick(tick):
        pipeline.process_tick(tick)

    handler.register_tick_callback(on_tick)

    client = NSEWebSocketClient(handler=handler)
    await client.connect()
    await client.subscribe_to_ticks(["NIFTY", "BANKNIFTY"])
```

### With Strategy Engine

```python
from src.strategy.engine import StrategyEngine
from src.data.websocket import NSEWebSocketClient

async def integrate_with_strategy():
    engine = StrategyEngine()
    client = NSEWebSocketClient(handler=engine)

    await client.connect()
    await client.subscribe_to_ticks(engine.get_required_symbols())
```

---

## Configuration

### Environment Variables

Configure WebSocket settings via environment variables:

```bash
# WebSocket URLs
export NSE_WS_URL="wss://nse-websocket-api.example.com"

# Timeout settings
export WS_TIMEOUT=30
export WS_RECONNECT_DELAY=5
export WS_MAX_RECONNECT_ATTEMPTS=5

# Heartbeat settings
export WS_PING_INTERVAL=30
export WS_PONG_TIMEOUT=10
```

---

## Troubleshooting

### Common Issues

1. **Connection Timeout**
   - Check network connectivity
   - Verify WebSocket URL is correct
   - Increase timeout value

2. **Authentication Failed**
   - Verify credentials/API keys
   - Check authentication method

3. **Message Parse Errors**
   - Verify message format matches expected schema
   - Check for API changes
   - Enable debug logging

4. **High Latency**
   - Check network connection
   - Reduce subscription count
   - Monitor server load

5. **Frequent Reconnections**
   - Check server stability
   - Increase reconnect delay
   - Monitor error logs

### Debug Mode

Enable debug logging for detailed information:

```python
import logging
from src.data.websocket import logger

logger.setLevel(logging.DEBUG)
```

---

## API Reference

### WebSocketClient Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `connect()` | Connect to WebSocket | `bool` |
| `disconnect()` | Disconnect from WebSocket | `None` |
| `reconnect()` | Reconnect to WebSocket | `bool` |
| `is_connected()` | Check connection status | `bool` |
| `subscribe(symbol, data_types)` | Subscribe to data | `bool` |
| `unsubscribe(symbol, data_types)` | Unsubscribe from data | `bool` |
| `send(message)` | Send message | `bool` |
| `send_json(data)` | Send JSON message | `bool` |
| `get_stats()` | Get connection stats | `WebSocketStats` |
| `reset_stats()` | Reset connection stats | `None` |

### NSEWebSocketClient Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `subscribe_to_ticks(symbols)` | Subscribe to tick data | `bool` |
| `subscribe_to_depth(symbols)` | Subscribe to depth data | `bool` |
| `subscribe_to_index(symbols)` | Subscribe to index data | `bool` |
| `subscribe_to_option_chain(symbol, expiry)` | Subscribe to option chain | `bool` |

### WebSocketManager Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `get_instance()` | Get singleton instance | `WebSocketManager` |
| `start()` | Start manager | `None` |
| `stop()` | Stop manager and clients | `None` |
| `add_client(name, client)` | Add client | `bool` |
| `remove_client(name)` | Remove client | `bool` |
| `get_client(name)` | Get client by name | `WebSocketClient | None` |

---

## Module Exports

The following are exported from the module:

### Enums
- `WebSocketState`
- `WebSocketMessageType`
- `MarketDataType`

### Exceptions
- `WebSocketError`
- `ConnectionError`
- `AuthenticationError`
- `SubscriptionError`
- `MessageParseError`
- `TimeoutError`
- `RateLimitError`

### Dataclasses
- `WebSocketMessage`
- `MarketDataTick`
- `WebSocketStats`

### Type Definitions
- `WebSocketMessageData`
- `SubscriptionRequest`

### Abstract Base Classes
- `MarketDataHandler`
- `SubscriptionManager`

### Client Classes
- `WebSocketClient`
- `NSEWebSocketClient`

### Default Handler
- `DefaultMarketDataHandler`

### Manager
- `WebSocketManager`

### Constants
- `NSE_WS_URL`
- `NSE_WS_V2_URL`
- `NSE_FNO_WS_URL`
- `DEFAULT_WS_TIMEOUT`
- `DEFAULT_RECONNECT_DELAY`
- `MAX_RECONNECT_ATTEMPTS`
- `MAX_MESSAGE_SIZE`
- `PING_INTERVAL`
- `PONG_TIMEOUT`

---

## Version History

- **1.0.0**: Initial implementation
- **1.1.0**: Added NSE-specific client
- **1.2.0**: Added WebSocketManager singleton
- **1.3.0**: Enhanced error handling and logging
- **1.4.0**: Added statistics tracking
- **1.5.0**: Improved reconnection logic

---

## License

This module is part of the SBITB-150626 trading platform and is licensed under the same terms as the main project.

## Support

For issues or questions, refer to:
- Project documentation
- Issue tracker
- Development team
