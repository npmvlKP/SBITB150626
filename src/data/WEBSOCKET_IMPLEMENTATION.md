# WebSocket Implementation for SBITB-150626

## Overview
This document describes the WebSocket implementation in `src/data/websocket.py`, which provides a robust, production-ready WebSocket client framework for real-time market data streaming from brokers like Zerodha Kite.

## Architecture

### Core Components

#### 1. Custom Exceptions
```python
- WebSocketError: Base exception for WebSocket operations
- ConnectionError: Connection-related failures
- AuthenticationError: Authentication failures
- MessageTimeoutError: Message timeout errors
```

#### 2. Message Types
```python
@dataclass
class WebSocketMessage:
    """Represents a WebSocket message with type, data, timestamp, and raw content."""
    message_type: str
    data: Any
    timestamp: datetime
    raw_message: Optional[str] = None

@dataclass
class WebSocketError:
    """Error container with message, code, and recoverable flag."""
    message: str
    code: Optional[int] = None
    recoverable: bool = True
```

#### 3. Connection State (Enum)
```python
class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"
```

## Core Classes

### 1. WebSocketConfig
Configuration dataclass with defaults:
- URL, API key, access token
- Reconnection settings (max attempts, delay, backoff)
- Heartbeat settings (interval, timeout)
- Message buffer size
- SSL verification
- Timeout settings

### 2. WebSocketClient (Core Class)
The main WebSocket client implementation with comprehensive features.

#### Key Methods:
- `connect()` / `disconnect()`: Connection management
- `send()`: Message sending with validation
- `receive()`: Message receiving with timeout
- `subscribe()` / `unsubscribe()`: Subscription management
- `ping()` / `pong()`: Heartbeat handling
- `reconnect()`: Automatic reconnection with backoff

#### Features:
- **Connection Management**: Full lifecycle (connect, disconnect, reconnect)
- **Message Handling**: Send/receive with validation and timeout
- **Reconnection Logic**: Exponential backoff with jitter
- **Heartbeat**: Automatic ping/pong to maintain connection
- **Error Handling**: Comprehensive error classification
- **State Management**: Clear state transitions
- **Rate Limiting**: Configurable message rate limits
- **Message Buffering**: For handling bursts of messages

### 3. BaseWebSocketHandler (Abstract Base)
Handler interface for processing WebSocket messages.

#### Abstract Methods (must implement):
- `on_connect(client)`: Called on successful connection
- `on_message(message)`: Process incoming messages
- `on_error(error)`: Handle errors
- `on_disconnect()`: Cleanup on disconnect

#### Optional Overrides:
- `on_reconnect(attempt, client)`: Reconnection callback
- `on_reconnect_success(client)`: After successful reconnect
- `on_reconnect_failed(error)`: When reconnection fails

### 4. KiteTickerHandler (Concrete Implementation)
Zerodha Kite-specific handler implementation.

#### Key Features:
- **Authentication**: Kite API key + access token
- **Message Types**: Handles order, trade, ticks, mode, full
- **Subscription Management**: Track subscribed instruments
- **Statistics**: Tick count, last tick time, subscription count

#### Message Handlers:
- `_handle_ticks(data)`: Process LTP and volume data
- `_handle_order(data)`: Order updates
- `_handle_trade(data)`: Trade updates
- `_handle_mode(data)`: Mode changes
- `_handle_full(data)`: Full market data

## Usage Examples

### Basic Client Usage
```python
from src.data.websocket import WebSocketClient, WebSocketConfig

config = WebSocketConfig(
    url="wss://api.kite.trade",
    api_key="your_api_key",
    access_token="your_access_token"
)

client = WebSocketClient(config)

async def main():
    await client.connect()

    # Send a message
    await client.send(json.dumps({"subscribe": "NIFTY"}))

    # Receive messages
    async for message in client.receive_stream():
        print(f"Received: {message.data}")

    await client.disconnect()

asyncio.run(main())
```

### Using Kite Ticker
```python
from src.data.websocket import KiteTickerHandler, WebSocketClient

handler = KiteTickerHandler(api_key="your_api_key", access_token="your_access_token")
client = WebSocketClient(config, handler=handler)

async def main():
    await client.connect()

    # Subscribe to instruments
    await handler.subscribe(client, [256265, 256266])  # NIFTY, BANKNIFTY

    # Keep connection alive
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
```

## Error Handling

### Error Classification
- **Recoverable**: Connection errors, timeouts → automatic retry
- **Non-Recoverable**: Authentication failures, invalid API key → manual intervention

### Error Codes
- `1000`: Normal closure
- `1001`: Going away
- `1006`: Abnormal closure
- `1008`: Policy violation
- `1011`: Internal error
- `4000-4999`: Application-specific errors

## Reconnection Strategy

### Exponential Backoff with Jitter
```python
base_delay = config.reconnect_delay  # Default: 5 seconds
max_attempts = config.max_reconnect_attempts  # Default: 5
backoff_factor = 2

# Formula: delay = base_delay * (backoff_factor ** (attempt - 1)) + random jitter
```

### Jitter Calculation
```python
jitter = random.uniform(0, base_delay * 0.5)  # 0-50% of base delay
```

## Heartbeat Mechanism

### Configuration
- **Interval**: Time between pings (default: 30 seconds)
- **Timeout**: Time to wait for pong response (default: 10 seconds)

### Implementation
```python
async def _heartbeat_loop(self):
    while self._state == ConnectionState.CONNECTED:
        await self.ping()
        await asyncio.sleep(self._config.heartbeat_interval)
```

## Message Processing

### Message Validation
- Check for empty messages
- Validate message size (< buffer_size)
- Parse JSON (catch exceptions)

### Message Buffer
- Stores incoming messages for batch processing
- Configurable size (default: 1000 messages)
- Thread-safe operations

## Testing

The implementation includes comprehensive tests in `tests/unit/test_websocket.py` covering:
- Connection lifecycle
- Message sending/receiving
- Error handling
- Reconnection logic
- Heartbeat functionality
- Rate limiting
- Message buffering

## Performance Considerations

### Optimizations
1. **Async I/O**: All operations are non-blocking
2. **Connection Pooling**: Reuses connections when possible
3. **Buffer Management**: Efficient message queuing
4. **Rate Limiting**: Prevents API throttling
5. **Memory Management**: Cleanup on disconnect

### Resource Usage
- Single WebSocket connection per broker
- Minimal memory footprint for message buffer
- Low CPU usage (async event loop)

## Integration with SBITB-150626

### Data Pipeline
```
Kite WebSocket → WebSocketClient → KiteTickerHandler → Data Store
                                      ↓
                               Strategy Engine
                                      ↓
                                Risk Module
```

### Expected Usage
1. **Real-time Data**: Market ticks, order updates
2. **Strategy Signals**: Trigger based on WebSocket events
3. **Risk Monitoring**: Real-time position updates
4. **Alert System**: Notifications on market events

## Configuration Recommendations

### Production Settings
```python
config = WebSocketConfig(
    url="wss://api.kite.trade",
    api_key=os.getenv("KITE_API_KEY"),
    access_token=os.getenv("KITE_ACCESS_TOKEN"),
    max_reconnect_attempts=10,
    reconnect_delay=3,  # Start with 3 seconds
    max_reconnect_delay=60,  # Max 60 seconds between retries
    heartbeat_interval=20,  # Ping every 20 seconds
    heartbeat_timeout=10,  # Wait 10 seconds for pong
    message_buffer_size=2000,  # Handle bursts
    rate_limit=100  # Max 100 messages/second
)
```

### Development Settings
```python
config = WebSocketConfig(
    url="wss://api.kite.trade",
    api_key="dev_key",
    access_token="dev_token",
    max_reconnect_attempts=3,
    reconnect_delay=1,
    message_buffer_size=100,
    ssl_verify=False  # For testing with self-signed certs
)
```

## Troubleshooting

### Common Issues

1. **Connection Drops**
   - Check network connectivity
   - Verify API key and access token
   - Check broker API status

2. **Authentication Failures**
   - Verify access token is valid
   - Check token expiration
   - Ensure proper headers are set

3. **Message Loss**
   - Check message buffer size
   - Verify rate limits
   - Check for errors in message handlers

4. **High Latency**
   - Check network latency
   - Verify server location
   - Check message processing time

## Best Practices

1. **Error Handling**: Always implement error handlers
2. **Reconnection**: Use exponential backoff
3. **Rate Limiting**: Respect API rate limits
4. **Logging**: Enable debug logging for troubleshooting
5. **Monitoring**: Track connection stats and errors
6. **Testing**: Test with mock WebSocket servers
7. **Security**: Use SSL/TLS for all connections

## Future Enhancements

1. **Multiple Broker Support**: Extend for other brokers (Upstox, etc.)
2. **Message Compression**: Support for compressed messages
3. **Load Balancing**: Multiple connections for high volume
4. **Message Persistence**: Store messages for offline processing
5. **Advanced Reconnection**: Session resumption support
6. **Metrics**: Prometheus metrics for monitoring

## API Reference

### WebSocketClient Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `connect()` | Establish WebSocket connection | `bool` |
| `disconnect()` | Close connection gracefully | `None` |
| `send(message)` | Send a message | `bool` |
| `receive(timeout=None)` | Receive a message | `Optional[WebSocketMessage]` |
| `receive_stream()` | Async generator for messages | `AsyncIterator[WebSocketMessage]` |
| `subscribe(tokens)` | Subscribe to instruments | `bool` |
| `unsubscribe(tokens)` | Unsubscribe from instruments | `bool` |
| `ping()` | Send ping | `bool` |
| `pong()` | Send pong | `bool` |
| `reconnect()` | Reconnect to server | `bool` |
| `is_connected()` | Check connection status | `bool` |

### KiteTickerHandler Properties

| Property | Description | Type |
|----------|-------------|------|
| `subscriptions` | Current subscriptions | `Dict[int, Dict[str, Any]]` |
| `stats` | Handler statistics | `Dict[str, Any]` |

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `url` | `None` | WebSocket URL |
| `api_key` | `None` | API key for authentication |
| `access_token` | `None` | Access token for authentication |
| `max_reconnect_attempts` | 5 | Maximum reconnection attempts |
| `reconnect_delay` | 5 | Initial reconnection delay (seconds) |
| `max_reconnect_delay` | 60 | Maximum reconnection delay (seconds) |
| `heartbeat_interval` | 30 | Heartbeat interval (seconds) |
| `heartbeat_timeout` | 10 | Heartbeat timeout (seconds) |
| `message_buffer_size` | 1000 | Message buffer size |
| `rate_limit` | 100 | Messages per second limit |
| `ssl_verify` | `True` | SSL certificate verification |
| `connect_timeout` | 10 | Connection timeout (seconds) |
| `message_timeout` | 5 | Message timeout (seconds) |

## Dependencies

```python
import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, AsyncIterator
import aiohttp
import websockets
```

## License
This implementation is part of SBITB-150626 and follows the project's licensing terms.
