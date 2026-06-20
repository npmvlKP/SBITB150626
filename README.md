# SBITB-150626 - Stock Broker Integrated Trading Bot

## Table of Contents
1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Architecture](#architecture)
4. [Components](#components)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Usage](#usage)
8. [Testing](#testing)
9. [Deployment](#deployment)
10. [Monitoring](#monitoring)
11. [Project Phases](#project-phases)
12. [Contributing](#contributing)
13. [License](#license)

---

## Overview

SBITB-150626 (Stock Broker Integrated Trading Bot) is a comprehensive algorithmic trading platform designed for Indian equity and derivatives markets. The system integrates with multiple brokers (Kite Connect, Alice Blue, Finvasia) to provide real-time market data, order execution, risk management, and advanced trading strategies.

### Key Features
- **Multi-Broker Support**: Kite Connect, Alice Blue, Finvasia integration
- **Real-time Data**: WebSocket-based market data streaming
- **Advanced Analytics**: Technical analysis, volatility analysis, Greeks calculation
- **Risk Management**: Position sizing, stop-loss mechanisms, SEBI compliance
- **Strategy Engine**: Rule-based strategies, backtesting framework
- **Monitoring**: Prometheus metrics, Grafana dashboards, health checks
- **Persistence**: TimescaleDB for time-series data, PostgreSQL for relational data

---

## Project Structure

```
SBITB-150626/
├── config/                          # Configuration files
│   ├── __init__.py
│   ├── secrets.env.example          # Environment variables template
│   └── settings.py                  # Application settings
│
├── deployment/                      # Deployment configurations
│   ├── docker-compose.yml           # Docker Compose for local development
│   ├── Dockerfile                   # Main application Dockerfile
│   ├── init.sql                     # Database initialization
│   ├── init_phase2.sql              # Phase 2 database schema
│   ├── prometheus.yml               # Prometheus configuration
│   ├── redis.conf                   # Redis configuration
│   ├── grafana/                     # Grafana dashboards
│   └── *.sh/*.bat                   # Deployment scripts
│
├── scripts/                         # Utility scripts
│   ├── daily_reconcile.py           # Daily reconciliation script
│   └── health_check.py              # Health check utilities
│
├── src/                             # Main source code
│   ├── __init__.py
│   ├── brokers/                     # Broker integrations
│   │   ├── __init__.py
│   │   ├── alice_blue.py            # Alice Blue broker implementation
│   │   ├── base.py                  # Base broker interface
│   │   ├── finvasia.py              # Finvasia broker implementation
│   │   └── kite.py                  # Kite Connect broker implementation
│   │
│   ├── data/                        # Data pipeline
│   │   ├── __init__.py
│   │   ├── event_log.py             # Immutable event logging
│   │   ├── providers.py             # Data provider interfaces
│   │   ├── storage.py               # Data storage handlers
│   │   └── websocket.py             # WebSocket client implementation
│   │
│   ├── risk/                        # Risk management
│   │   ├── __init__.py
│   │   └── engine.py                # Risk engine implementation
│   │
│   └── strategy/                    # Trading strategies
│       ├── __init__.py
│       └── base.py                  # Strategy base classes
│
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── conftest.py                  # Pytest fixtures
│   ├── test_event_log.py            # Event log tests
│   ├── test_interfaces.py           # Interface tests
│   └── unit/                        # Unit tests
│
├── SBITB-150626-Plan/               # Project planning documents
│   ├── Plan.txt                     # Overall project plan
│   ├── Ph0-Instructions.md          # Phase 0: Instructions
│   ├── Ph1-Base Technology Stack Setup.txt
│   ├── Ph2-F&O Data Pipeline + Greeks Implementation.txt
│   ├── Ph3-TA & VA Engine.txt
│   └── ... (Phases 4-18)
│
├── *.yaml                           # Configuration files
├── *.json                           # Configuration and reports
├── *.md                             # Documentation
└── requirements*.txt                # Python dependencies
```

---

## Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SBITB-150626 System                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   Kite       │    │ Alice Blue   │    │  Finvasia    │          │
│  │   Connect     │    │              │    │              │          │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
│         │                   │                   │                   │
│         └───────────────────┼───────────────────┘                   │
│                             │                                       │
│                    ┌────────▼────────┐                              │
│                    │  Broker Layer    │                              │
│                    │  (Base Interface)│                              │
│                    └────────┬────────┘                              │
│                             │                                       │
│         ┌───────────────────┼───────────────────┐                   │
│         │                   │                   │                   │
│  ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐            │
│  │ Market Data │    │ Order        │    │ Risk        │            │
│  │ Provider    │    │ Management   │    │ Engine      │            │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘            │
│         │                   │                   │                   │
│         └───────────────────┼───────────────────┘                   │
│                             │                                       │
│                    ┌────────▼────────┐                              │
│                    │  Strategy Engine │                              │
│                    │  (Rule-based,    │                              │
│                    │   Backtesting)   │                              │
│                    └────────┬────────┘                              │
│                             │                                       │
│         ┌───────────────────┼───────────────────┐                   │
│         │                   │                   │                   │
│  ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐            │
│  │ TimescaleDB │    │ PostgreSQL  │    │   Redis     │            │
│  │ (Time-series)│    │ (Relational)│    │  (Caching)  │            │
│  └─────────────┘    └─────────────┘    └─────────────┘            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Monitoring Layer                           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │   │
│  │  │Prometheus│  │  Grafana │  │   Alerts │  │  Logging │     │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology |
|-----------|------------|
| **Language** | Python 3.11+ |
| **Web Framework** | FastAPI (planned) |
| **Database** | TimescaleDB, PostgreSQL |
| **Caching** | Redis |
| **Message Queue** | Redis Pub/Sub |
| **Monitoring** | Prometheus, Grafana |
| **Containerization** | Docker, Docker Compose |
| **Testing** | pytest, pytest-asyncio |
| **Type Checking** | mypy |
| **Code Quality** | bandit, pre-commit |
| **Secret Management** | Environment variables |

---

## Components

### 1. Broker Layer (`src/brokers/`)

The broker layer provides unified interfaces for interacting with different broker APIs.

#### Base Interface (`base.py`)
- **`BrokerInterface`**: Abstract base class defining the contract for all broker implementations
- **Required Methods**:
  - `authenticate(api_key: str, access_token: str, user_id: str) -> str`
  - `place_order(params: dict) -> dict`
  - `cancel_order(order_id: str) -> dict`
  - `cancel_all_orders() -> list`
  - `get_positions() -> list`
  - `get_margins() -> dict`
  - `get_order_book() -> list`
  - `get_instruments(segment: str) -> list`

#### Implementations

**Kite Connect (`kite.py`)**
- Full implementation of Kite Connect API
- WebSocket streaming support
- REST API integration
- Authentication via API key, access token, user ID
- Order management (place, modify, cancel)
- Position and margin retrieval
- Instrument master data

**Alice Blue (`alice_blue.py`)**
- Alice Blue broker integration
- Similar interface to Kite Connect
- WebSocket support for real-time data
- Order execution capabilities

**Finvasia (`finvasia.py`)**
- Finvasia (Shoonya) broker integration
- REST and WebSocket APIs
- Order management
- Market data access

### 2. Data Pipeline (`src/data/`)

#### Event Logging (`event_log.py`)
Immutable event logging system based on Martin Kleppmann's patterns (Ch. 3-4).

**Key Classes:**
- **`MarketEvent`**: Dataclass representing market events
  - `event_id`: UUID
  - `event_type`: Event category (FO_BHAVCOPY, WS_TICK, etc.)
  - `event_time`: Timestamp with timezone
  - `schema_version`: Current schema version
  - `payload`: Event data (dict)
  - `source`: Data source identifier
  - `ingest_id`: Ingestion identifier
  - `epoch`: Event epoch

- **`VALID_EVENT_TYPES`**: Tuple of valid event types
  - FO_BHAVCOPY, EOD_BHAVCOPY, INDEX_BHAVCOPY
  - WS_TICK, WS_LTP, WS_ORDERBOOK
  - REST_QUOTE, REST_HISTORICAL
  - ORDER_PLACED, ORDER_CANCELLED, ORDER_MODIFIED
  - POSITION_CHANGE, MARGIN_UPDATE

- **`CURRENT_SCHEMA_VERSION`**: Current schema version (2)

**Schema Migration:**
- **`migrate_v1_to_v2(payload)`**: Adds `oi_change` field with default value 0

- **`EventCodec`**: Handles encoding and decoding of events
  - `encode(event: MarketEvent) -> dict`: Serializes to dictionary
  - `decode(raw: dict) -> MarketEvent`: Deserializes with schema migration

- **`EventLogWriter`**: Manages event buffering and persistence
  - Configurable batch size for flushing
  - Async flush to PostgreSQL
  - Buffer management
  - Context manager support

#### Data Providers (`providers.py`)
- **`MarketDataProvider`**: Abstract interface for market data
  - `get_quote(symbol: str) -> dict`
  - `get_historical(symbol: str, from_date: str, to_date: str) -> list`
  - `subscribe(symbols: list, callback: Callable) -> None`

#### WebSocket Client (`websocket.py`)
Comprehensive WebSocket client for real-time market data.

**Key Classes:**

- **`WebSocketState`**: Enum for connection states
  - CONNECTING, CONNECTED, DISCONNECTED, RECONNECTING, ERROR

- **`ReconnectStrategy`**: Configuration for reconnection
  - `max_attempts`: Maximum reconnection attempts
  - `base_delay`: Base delay between attempts (seconds)
  - `max_delay`: Maximum delay cap
  - `backoff_factor`: Exponential backoff multiplier
  - `jitter`: Random jitter factor

- **`MessageHandler`**: Protocol for message handling
  - `on_message(message: Any) -> Awaitable[None]`
  - `on_error(error: Exception) -> Awaitable[None]`
  - `on_connect() -> Awaitable[None]`
  - `on_disconnect() -> Awaitable[None]`

- **`WebSocketClient`**: Main WebSocket client implementation
  - **Initialization**:
    ```python
    client = WebSocketClient(
        url="wss://api.kite.trade",
        handler=MyHandler(),
        reconnect_strategy=ReconnectStrategy(
            max_attempts=5,
            base_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0
        )
    )
    ```
  - **Connection Management**:
    - `connect() -> Awaitable[None]`: Establish connection
    - `disconnect() -> Awaitable[None]`: Close connection
    - `reconnect() -> Awaitable[None]`: Re-establish connection
  - **Message Handling**:
    - `send(message: Any) -> Awaitable[None]`: Send message
    - `subscribe(symbols: list) -> Awaitable[None]`: Subscribe to symbols
    - `unsubscribe(symbols: list) -> Awaitable[None]`: Unsubscribe
  - **State Management**:
    - `is_connected() -> bool`: Check connection status
    - `get_state() -> WebSocketState`: Get current state
  - **Lifecycle**:
    - `start() -> Awaitable[None]`: Start connection
    - `stop() -> Awaitable[None]`: Stop connection
    - Async context manager support (`async with`)

- **`MarketDataWebSocketClient`**: Specialized client for market data
  - Extends `WebSocketClient` with market-specific features
  - Built-in message parsing
  - Symbol subscription management
  - Tick data processing

- **`KiteWebSocketClient`**: Kite Connect WebSocket implementation
  - Kite-specific message handling
  - Authentication with API key
  - Automatic reconnection with authentication
  - Tick, LTP, order book subscriptions

- **`WebSocketError`**: Custom exception class
  - Error codes: CONNECTION_FAILED, AUTHENTICATION_FAILED, etc.

**Features:**
- Automatic reconnection with exponential backoff
- Heartbeat mechanism
- Message buffering during disconnection
- Connection state tracking
- Error handling and retry logic
- SSL/TLS support
- Rate limiting handling
- Connection validation

#### Storage (`storage.py`)
- **`TimescaleStorage`**: TimescaleDB storage handler
- **`PostgresStorage`**: PostgreSQL storage handler
- **`RedisCache`**: Redis caching layer

### 3. Risk Management (`src/risk/`)

#### Risk Engine (`engine.py`)
- Position sizing calculations
- Stop-loss mechanisms
- Margin requirements validation
- SEBI compliance checks
- Risk exposure monitoring

### 4. Strategy Engine (`src/strategy/`)

#### Base Classes (`base.py`)
- **`StrategyInterface`**: Abstract base class for strategies
  - **Properties**:
    - `strategy_id`: Unique identifier
    - `version`: Strategy version
    - `name`: Human-readable name
    - `description`: Strategy description
    - `author`: Strategy author
    - `is_active`: Activation status
  - **Methods**:
    - `on_tick(tick: dict) -> None`: Handle tick data
    - `on_order_update(update: dict) -> None`: Handle order updates
    - `start() -> None`: Start strategy
    - `stop() -> None`: Stop strategy
    - `validate_config(config: dict) -> bool`: Validate configuration

- **`StrategyFactory`**: Factory for creating strategy instances
- **`StrategyConfig`**: Configuration dataclass

### 5. Monitoring & Observability

#### Prometheus Metrics
- Order execution metrics
- Data pipeline metrics
- System health metrics
- Performance metrics

#### Grafana Dashboards
- Real-time monitoring
- Historical analysis
- Alert visualization

#### Health Checks
- Broker connectivity
- Database connectivity
- Cache connectivity
- System resource monitoring

---

## Installation

### Prerequisites
- Python 3.11 or higher
- Docker and Docker Compose
- PostgreSQL 14+
- TimescaleDB extension
- Redis 6+
- Git

### Quick Start

```bash
# Clone the repository
git clone https://github.com/npmvlKP/SBITB150626.git
cd SBITB150626

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp config/secrets.env.example config/secrets.env

# Edit configuration
nano config/secrets.env  # Update with your API keys
```

### Docker Deployment

```bash
# Start all services
docker-compose -f deployment/docker-compose.yml up -d

# Initialize database
docker exec -it sbitb-app python deployment/init_phase2.sql

# Run health check
docker exec -it sbitb-app python scripts/health_check.py
```

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/ -v

# Run linting
bandit -r src/
mypy src/
```

---

## Configuration

### Environment Variables (`config/secrets.env`)

```ini
# Broker API Keys
KITE_API_KEY=your_kite_api_key
KITE_ACCESS_TOKEN=your_kite_access_token
KITE_USER_ID=your_kite_user_id
ALICE_BLUE_API_KEY=your_alice_blue_api_key
ALICE_BLUE_USER_ID=your_alice_blue_user_id
FINVASIA_API_KEY=your_finvasia_api_key

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_bot
DB_USER=trading_user
DB_PASSWORD=your_db_password

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

# Application Settings
LOG_LEVEL=INFO
BATCH_SIZE=100
MAX_RECONNECT_ATTEMPTS=5
BASE_DELAY=1.0
MAX_DELAY=30.0
BACKOFF_FACTOR=2.0
```

### Settings (`config/settings.py`)

```python
class Settings:
    # Database
    DATABASE_URL: str = "postgresql://trading_user:password@localhost/trading_bot"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Broker
    DEFAULT_BROKER: str = "kite"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # WebSocket
    WS_MAX_RECONNECTS: int = 5
    WS_BASE_DELAY: float = 1.0
    WS_MAX_DELAY: float = 30.0
    WS_BACKOFF_FACTOR: float = 2.0

    # Event Log
    EVENT_LOG_BATCH_SIZE: int = 100
    EVENT_LOG_FLUSH_INTERVAL: float = 5.0
```

---

## Usage

### Basic Usage

```python
import asyncio
from src.brokers.kite import KiteBroker
from src.data.websocket import KiteWebSocketClient, MarketDataHandler

async def main():
    # Initialize broker
    broker = KiteBroker(
        api_key="your_api_key",
        access_token="your_access_token",
        user_id="your_user_id"
    )

    # Authenticate
    await broker.authenticate()

    # Get instruments
    instruments = await broker.get_instruments("NFO")
    print(f"Loaded {len(instruments)} instruments")

    # Place order
    order_params = {
        "variety": "regular",
        "exchange": "NFO",
        "tradingsymbol": "NIFTY24JUN25000CE",
        "transaction_type": "BUY",
        "quantity": 1,
        "price": 100.0,
        "product": "MIS"
    }
    order = await broker.place_order(order_params)
    print(f"Order placed: {order}")

    # Initialize WebSocket
    class MyHandler(MarketDataHandler):
        async def on_tick(self, tick):
            print(f"Tick: {tick}")

        async def on_connect(self):
            print("WebSocket connected")
            await self.subscribe(["NIFTY 50", "BANKNIFTY"])

    ws_client = KiteWebSocketClient(
        api_key="your_api_key",
        access_token="your_access_token",
        handler=MyHandler(),
        user_id="your_user_id"
    )

    await ws_client.connect()

    # Keep running
    await asyncio.sleep(3600)

    await ws_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

### Event Logging

```python
from datetime import datetime, UTC
import uuid
from src.data.event_log import (
    MarketEvent,
    EventCodec,
    EventLogWriter,
    CURRENT_SCHEMA_VERSION
)

# Create an event
event = MarketEvent(
    event_id=uuid.uuid4(),
    event_type="WS_TICK",
    event_time=datetime.now(UTC),
    schema_version=CURRENT_SCHEMA_VERSION,
    payload={"symbol": "NIFTY50", "ltp": 22000.50},
    source="kite_ws",
    ingest_id=uuid.uuid4(),
    epoch=1
)

# Encode event
encoded = EventCodec.encode(event)
print(f"Encoded: {encoded}")

# Decode event
decoded = EventCodec.decode(encoded)
print(f"Decoded: {decoded}")

# Use writer with buffer
writer = EventLogWriter(
    database_url="postgresql://user:pass@localhost/db",
    batch_size=10
)

async def log_events():
    async with writer:
        for _ in range(15):
            writer.buffer.append(event)
            # Auto-flush when batch_size reached
```

### WebSocket Client

```python
import asyncio
from src.data.websocket import (
    WebSocketClient,
    WebSocketState,
    ReconnectStrategy,
    MessageHandler
)

class MyMessageHandler(MessageHandler):
    async def on_message(self, message):
        print(f"Received: {message}")

    async def on_error(self, error):
        print(f"Error: {error}")

    async def on_connect(self):
        print("Connected!")
        await self.client.send({"type": "subscribe", "symbols": ["NIFTY50"]})

    async def on_disconnect(self):
        print("Disconnected")

async def run_websocket():
    handler = MyMessageHandler()
    client = WebSocketClient(
        url="wss://api.kite.trade",
        handler=handler,
        reconnect_strategy=ReconnectStrategy(
            max_attempts=5,
            base_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0
        )
    )

    try:
        await client.connect()
        await asyncio.sleep(3600)
    finally:
        await client.disconnect()

asyncio.run(run_websocket())
```

---

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_event_log.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run async tests
pytest tests/ -v -p asyncio

# Run interface tests
pytest tests/test_interfaces.py -v
```

### Test Structure

```bash
tests/
├── __init__.py
├── conftest.py              # Pytest fixtures
├── test_event_log.py        # Event log tests
├── test_interfaces.py       # Interface contract tests
└── unit/                    # Unit tests for individual components
```

### Key Test Cases

**Event Log Tests (`test_event_log.py`)**:
- MarketEvent dataclass validation
- EventCodec encode/decode round-trip
- Schema migration (v1 → v2)
- EventLogWriter buffer management
- Async context manager support

**Interface Tests (`test_interfaces.py`)**:
- BrokerInterface abstract method validation
- StrategyInterface property and method checks
- MarketDataProvider interface verification
- Parameter signature validation

---

## Deployment

### Docker Compose

```yaml
# deployment/docker-compose.yml
version: '3.8'

services:
  postgres:
    image: timescale/timescaledb:latest
    environment:
      POSTGRES_PASSWORD: password
      POSTGRES_USER: trading_user
      POSTGRES_DB: trading_bot
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:6
    command: redis-server --requirepass your_redis_password
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./deployment/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

  app:
    build: .
    environment:
      - DB_HOST=postgres
      - DB_PORT=5432
      - DB_NAME=trading_bot
      - DB_USER=trading_user
      - DB_PASSWORD=password
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - postgres
      - redis
    ports:
      - "8000:8000"
    volumes:
      - .:/app

volumes:
  postgres_data:
  redis_data:
  grafana_data:
```

### Deployment Scripts

```bash
# Build Docker images
./deployment/build.sh

# Start services
./deployment/deploy_and_test.sh

# Initialize Phase 2 schema
./deployment/apply_phase2.ps1  # Windows
./deployment/apply_phase2.sh    # Linux/Mac

# Backup TimescaleDB
./deployment/backup_timescaledb.sh
```

### Database Initialization

```sql
-- deployment/init_phase2.sql
-- Phase 2: F&O Data Pipeline + Greeks Implementation

-- Event log table
CREATE TABLE IF NOT EXISTS event_log (
    id SERIAL PRIMARY KEY,
    event_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    source VARCHAR(50) NOT NULL,
    ingest_id UUID,
    epoch INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create hypertable for time-series data
SELECT create_hypertable('event_log', 'event_time');

-- Market data table
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(10) NOT NULL,
    ltp DECIMAL(15, 2),
    open DECIMAL(15, 2),
    high DECIMAL(15, 2),
    low DECIMAL(15, 2),
    close DECIMAL(15, 2),
    volume BIGINT,
    oi BIGINT,
    oi_change BIGINT,
    timestamp TIMESTAMPTZ NOT NULL
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    broker VARCHAR(20) NOT NULL,
    variety VARCHAR(20) NOT NULL,
    exchange VARCHAR(10) NOT NULL,
    tradingsymbol VARCHAR(50) NOT NULL,
    transaction_type VARCHAR(10) NOT NULL,
    quantity INTEGER NOT NULL,
    price DECIMAL(15, 2),
    product VARCHAR(10),
    status VARCHAR(20),
    placed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    UNIQUE(broker, order_id)
);

-- Positions table
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    broker VARCHAR(20) NOT NULL,
    exchange VARCHAR(10) NOT NULL,
    tradingsymbol VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price DECIMAL(15, 2),
    ltp DECIMAL(15, 2),
    pnl DECIMAL(15, 2),
    UNIQUE(broker, exchange, tradingsymbol)
);

-- Greeks table (for F&O)
CREATE TABLE IF NOT EXISTS greeks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(10) NOT NULL,
    delta DECIMAL(10, 6),
    gamma DECIMAL(10, 6),
    theta DECIMAL(10, 6),
    vega DECIMAL(10, 6),
    rho DECIMAL(10, 6),
    iv DECIMAL(10, 4),
    timestamp TIMESTAMPTZ NOT NULL
);

-- Create indexes
CREATE INDEX idx_event_log_event_type ON event_log(event_type);
CREATE INDEX idx_event_log_event_time ON event_log(event_time);
CREATE INDEX idx_event_log_source ON event_log(source);
CREATE INDEX idx_market_data_symbol ON market_data(symbol);
CREATE INDEX idx_market_data_timestamp ON market_data(timestamp);
CREATE INDEX idx_orders_broker ON orders(broker);
CREATE INDEX idx_orders_status ON orders(status);
```

---

## Monitoring

### Prometheus Configuration

```yaml
# deployment/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'sbitb'
    static_configs:
      - targets: ['app:8000']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
```

### Health Check

```python
# scripts/health_check.py
import asyncio
import logging
from datetime import datetime
from src.brokers.kite import KiteBroker
from src.data.websocket import KiteWebSocketClient

class HealthChecker:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def check_broker_connection(self):
        """Check broker API connectivity."""
        try:
            broker = KiteBroker(
                api_key="your_api_key",
                access_token="your_access_token",
                user_id="your_user_id"
            )
            await broker.authenticate()
            return True, "Broker connection OK"
        except Exception as e:
            return False, f"Broker connection failed: {e}"

    async def check_websocket_connection(self):
        """Check WebSocket connectivity."""
        try:
            client = KiteWebSocketClient(
                api_key="your_api_key",
                access_token="your_access_token",
                user_id="your_user_id"
            )
            await client.connect()
            await client.disconnect()
            return True, "WebSocket connection OK"
        except Exception as e:
            return False, f"WebSocket connection failed: {e}"

    async def check_database_connection(self):
        """Check database connectivity."""
        try:
            # Implementation depends on your DB library
            return True, "Database connection OK"
        except Exception as e:
            return False, f"Database connection failed: {e}"

    async def run_all_checks(self):
        """Run all health checks."""
        checks = [
            ("Broker API", self.check_broker_connection),
            ("WebSocket", self.check_websocket_connection),
            ("Database", self.check_database_connection),
        ]

        results = {}
        for name, check in checks:
            try:
                success, message = await check()
                results[name] = {"status": "OK" if success else "FAIL", "message": message}
            except Exception as e:
                results[name] = {"status": "ERROR", "message": str(e)}

        return results

async def main():
    checker = HealthChecker()
    results = await checker.run_all_checks()

    print(f"\n=== Health Check Report - {datetime.now()} ===")
    for check_name, result in results.items():
        status = result["status"]
        message = result["message"]
        symbol = "✓" if status == "OK" else "✗"
        print(f"{symbol} {check_name}: {status} - {message}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Project Phases

The project is organized into 18 phases, each building upon the previous:

### Phase 0: Instructions
Base setup and project guidelines

### Phase 1: Base Technology Stack Setup
- Python environment
- Version control
- Project structure
- Basic tooling

### Phase 2: F&O Data Pipeline + Greeks Implementation ⭐ **CURRENT**
- WebSocket infrastructure
- Event logging system
- Market data processing
- Greeks calculation
- Database schema (Phase 2)

### Phase 3: Technical Analysis & Volatility Analysis Engine
- TA indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
- Volatility analysis (ATR, Standard Deviation)
- Pattern recognition

### Phase 4: Market Strength Engine
- Market breadth analysis
- Sector analysis
- Volume analysis
- Momentum indicators

### Phase 5: First Strategy — Rule-Based Options
- Basic options strategies
- Rule-based entry/exit
- Position sizing
- Risk management

### Phase 6: Backtesting Framework
- Historical data processing
- Strategy backtesting
- Performance metrics
- Optimization

### Phase 7: Options Strike Auto-Selection + Adaptive Trailing Stop Loss
- Strike selection algorithms
- Adaptive stop-loss
- Dynamic position management

### Phase 8: Sentiment Analysis Pipeline
- News sentiment analysis
- Social media monitoring
- Sentiment scoring

### Phase 9: RAG Knowledge Engine
- Retrieval-Augmented Generation
- Market knowledge base
- Decision support

### Phase 10: Risk Management & SEBI Compliance Layer
- Comprehensive risk management
- SEBI compliance checks
- Regulatory reporting

### Phase 11: Signal Orchestration
- Signal aggregation
- Signal prioritization
- Trade execution logic

### Phase 12: Paper Trading
- Simulated trading
- Performance tracking
- Strategy validation

### Phase 13: Cloud Deployment to Oracle Cloud Mumbai
- Oracle Cloud Infrastructure
- Container orchestration
- Scaling and load balancing

### Phase 14: Live Trading — Minimal Capital
- Live trading with minimal capital
- Risk-controlled execution
- Performance monitoring

### Phase 15: MCX Commodity Extension
- MCX integration
- Commodity trading
- Multi-asset support

### Phase 16: Multi-Broker Redundancy
- Broker failover
- Load balancing
- Redundancy management

### Phase 17: DRL Agent
- Deep Reinforcement Learning
- Adaptive strategies
- Continuous learning

### Phase 18: Continuous Improvement
- Monitoring and analytics
- Performance optimization
- Feature enhancements

---

## Contributing

### Development Guidelines
1. Follow PEP 8 style guide
2. Write type hints for all functions
3. Include docstrings for all public methods
4. Add tests for new features
5. Run linting and type checking before committing

### Git Workflow
```bash
# Create feature branch
git checkout -b feature/your-feature

# Make changes
git add .
git commit -m "Add your feature"

# Push to remote
git push origin feature/your-feature

# Create pull request
gh pr create
```

### Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort

  - repo: https://github.com/pycqa/mypy
    rev: v1.4.1
    hooks:
      - id: mypy
```

---

## License

This project is proprietary and confidential. All rights reserved.

---

## Documentation Files

- [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) - Detailed installation instructions
- [VERIFICATION_GUIDE.md](VERIFICATION_GUIDE.md) - Verification procedures
- [HEALTH_CHECK_PROTOCOL.md](HEALTH_CHECK_PROTOCOL.md) - Health check protocols
- [SBITB-150626-Plan/](SBITB-150626-Plan/) - Complete project planning documents

---

## Support

For issues or questions, please refer to the project documentation or create an issue in the repository.

---

**Project Status**: Phase 2 - F&O Data Pipeline + Greeks Implementation
**Last Updated**: June 2026
**Version**: 1.0.0
