# Phase 0: Sequential AI-Agent Instructions — Compliance Framework + Project Scaffolding

> **Duration:** ~5 days | **Output:** `SBITB-150626/` with all Phase 0 files, all 15 test tools passing
> **Environment:** Windows 11 + Python 3.11+ + Docker (WSL2 backend)
> **Reference Docs:** `G:\OC\02June26\SEBI_Algo_Trading_Regulation_Research.md` + `G:\OC\02June26\COMPLIANCE_SECURITY_MAPPING.md`

---

## Critical Corrections Applied

1. **500ms resting time is NOT a SEBI mandate** — was proposed in 2016 discussion paper, dropped in 2018 circular (SEBI/HO/MRD/DP/CIR/P/2018/62). No constant, no reference, no DO NOT rule for this.
2. **Algo ID tagging is BROKER's responsibility** — per SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013, the exchange provides the unique algo ID; the broker tags orders server-side. Our `tag` field in Kite API is for our own audit trail/attribution, NOT for exchange-mandated algo ID tagging.
3. **OPS threshold = 10** per NSE/INVG/67858 (May 5, 2025) — below this, no registration needed; above, must register algo with exchange through broker.
4. **Zerodha has NO sandbox/test environment** — paper trading mode logs orders but doesn't send.
5. **Bracket Orders disabled on Zerodha since 2021** — trailing stop must be implemented in bot logic + SL-M orders.

---

## Instruction 1 — Initialize Project Structure + Git

Create the following directory tree under `G:\OC\SBITB-150626`:

```
G:\OC\SBITB-090626\
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml
├── config/
│   ├── __init__.py
│   ├── settings.py          # Risk limits, broker configs, segment params
│   └── secrets.env.example   # Template — NEVER commit actual secrets.env
├── src/
│   ├── __init__.py
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── manager.py       # Pre-trade risk check pipeline
│   │   ├── kill_switch.py   # Emergency halt — 3 activation paths
│   │   ├── compliance.py    # SEBI compliance enforcement constants
│   │   └── audit.py         # 7-year audit trail with SHA-256 checksums
│   ├── brokers/
│   │   ├── __init__.py
│   │   └── base.py          # Abstract broker interface
│   ├── data/
│   │   ├── __init__.py
│   │   └── providers.py     # Market data provider interface
│   └── strategy/
│       ├── __init__.py
│       └── base.py          # Abstract strategy interface
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── risk/
│       ├── __init__.py
│       ├── test_manager.py
│       ├── test_kill_switch.py
│       ├── test_compliance.py
│       └── test_audit.py
├── deployment/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── .env.docker.example
│   ├── init.sql
│   └── prometheus.yml
└── scripts/
    ├── daily_reconcile.py   # EOD reconciliation skeleton
    └── health_check.py      # Pre-market health check skeleton
```

Initialize a git repo in `git@github.com:npmvlKP/SBITB.09June26.git   [OR] https://github.com/npmvlKP/SBITB.09June26.git`.

`.gitignore` must include:
```
__pycache__/
*.pyc
.venv/
.env
secrets.env
*.egg-info/
dist/
build/
.mypy_cache/
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage
*.cover
.cosmic-ray*
node_modules/
.DS_Store
*.log
.trivy-cache/
.gitleaks/
```

**CRITICAL:** `secrets.env` must NEVER be committed. Only `secrets.env.example`.

---

## Instruction 2 — `pyproject.toml` with All Tool Configs

Create `pyproject.toml` with:

```toml
[project]
name = "indian-trading-bot"
version = "0.1.0"
description = "SEBI-compliant Indian algorithmic trading bot for NSE + MCX"
requires-python = ">=3.11"
dependencies = [
    "kiteconnect>=5.0",
    "pandas>=2.1",
    "numpy>=1.26",
    "structlog>=23.2",
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "httpx>=0.25",
    "redis>=5.0",
    "psycopg[binary]>=3.1",
    "vollib>=0.1",
    "QuantLib>=1.32",
    "cryptography>=41.0",
    "apscheduler>=3.10",
    "python-telegram-bot>=20.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "pytest-mock>=3.12",
    "pytest-xdist>=3.5",
    "pytest-timeout>=2.2",
    "pytest-randomly>=3.15",
    "mypy>=1.8",
    "ruff>=0.5",
    "bandit[toml]>=1.7",
    "pip-audit>=0.7",
    "safety>=3.0",
    "pre-commit>=3.6",
    "gitleaks>=8.18",
    "trivy>=0.50",
    "detect-secrets>=1.4",
    "vulture>=2.11",
    "pydocstyle>=6.3",
    "debugpy>=1.8",
    "rich>=13.7",
]

[tool.ruff]
target-version = "py311"
line-length = 120
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "SIM", "TCH", "RUF"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["src", "config"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_generics = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["kiteconnect.*", "vollib.*", "QuantLib.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short --strict-markers"
markers = [
    "slow: slow tests",
    "integration: requires broker API connection",
    "paper_trade: paper trading mode tests",
]
filterwarnings = ["error"]

[tool.coverage.run]
source = ["src"]
branch = true
omit = ["tests/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true

[tool.bandit]
targets = ["src"]
skips = ["B101"]

[tool.vulture]
min_confidence = 80
paths = ["src", "tests"]

[tool.pydocstyle]
convention = "google"
add-ignore = ["D100", "D104", "D105", "D107"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## Instruction 3 — `config/settings.py` with Compliance Constants

Create `config/settings.py` with Pydantic BaseSettings classes:

### 3.1 ComplianceSettings — SEBI-verified constants

```python
MAX_ORDERS_PER_SECOND: int = 3           # Self-imposed (< Zerodha's 10 OPS; below SEBI/NSE 10 OPS registration threshold per NSE/INVG/67858)
MAX_ORDERS_PER_MINUTE: int = 60          # Self-imposed (< Zerodha's 400/min)
MAX_ORDERS_PER_DAY: int = 500            # Self-imposed (< Zerodha's 5000/day)
SEBI_OPS_REGISTRATION_THRESHOLD: int = 10 # Per NSE/INVG/67858 May 5 2025; above this = must register algo with exchange
TRADING_START_IST: time(9, 15)           # NSE regular session
TRADING_END_IST: time(15, 30)            # NSE regular session close
MCX_TRADING_START_IST: time(9, 0)        # MCX morning session
MCX_TRADING_END_MORNING_IST: time(14, 30) # MCX morning close
MCX_TRADING_START_EVENING_IST: time(17, 0) # MCX evening session
MCX_TRADING_END_EVENING_IST: time(23, 30) # MCX evening close
ALLOWED_SEGMENTS: list = ["NSE", "MCX"]
ALLOWED_NSE_INSTRUMENTS: list = ["NIFTY", "BANKNIFTY"]   # Options only initially
ALLOWED_MCX_INSTRUMENTS: list = ["GOLD", "SILVER", "CRUDEOIL"]
ALGO_TAG_FORMAT: str = "{strategy_id}:{version}"  # Kite API `tag` field; max 20 chars; per FIX EP297
SEBI_ALGO_CIRCULAR: str = "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013"
NSE_ATF_CIRCULAR: str = "NSE/INVG/67858"
# NOTE: NO 500ms resting time constant — was proposed in 2016 discussion paper
# but NEVER mandated per SEBI/HO/MRD/DP/CIR/P/2018/62
```

### 3.2 RiskSettings

```python
MAX_ORDER_VALUE_PER_TRADE: Decimal = Decimal("200000")      # Rs 2L per order
MAX_POSITION_NOTIONAL_PER_SYMBOL: Decimal = Decimal("500000") # Rs 5L per symbol
MAX_TOTAL_EXPOSURE: Decimal = Decimal("2000000")             # Rs 20L total
MARGIN_UTILIZATION_THRESHOLD: Decimal = Decimal("0.80")      # Alert at 80%
MARGIN_UTILIZATION_KILL: Decimal = Decimal("0.95")           # Kill switch at 95%
DAILY_LOSS_LIMIT: Decimal = Decimal("50000")                 # Rs 50K daily loss
ORDER_REJECTION_THRESHOLD: int = 10                          # 10 rejections in 1 min = kill
CIRCUIT_LIMIT_PCT: Decimal = Decimal("0.05")                 # +/-5% from LTP
```

### 3.3 KillSwitchSettings

```python
THROTTLE_RATE_PCT: Decimal = Decimal("0.10")    # 10% of normal rate
REQUIRE_MANUAL_RE_ENABLE: bool = True            # Never auto-resume after kill
ACTIVATION_PATHS: list = ["keyboard", "telegram", "rest_api"]  # Ctrl+Shift+K, /kill, POST /kill-switch
```

Kill switch levels (enum): `INACTIVE | THROTTLE | PAUSE | KILL`

Per MiFID II Art. 17, NIST RS.RP-1, ISO A.8.26.

### 3.4 AuditSettings

```python
RETENTION_YEARS: int = 7                       # SEBI requires 5+; we retain 7
CHECKSUM_ALGORITHM: str = "sha256"              # Consistent with Kite auth checksum
NTP_SERVER: str = "in.pool.ntp.org"             # IST NTP server
MAX_NTP_OFFSET_MS: int = 500                    # Alert if clock drift > 500ms
```

### 3.5 BrokerSettings (per-broker)

```python
# Zerodha
ZERODHA_API_RATE_QUOTES: int = 1                # req/sec per Zerodha docs
ZERODHA_API_RATE_HISTORICAL: int = 3            # req/sec
ZERODHA_API_RATE_ORDERS: int = 10               # req/sec (exchange-level; our self-imposed is 3)
ZERODHA_WS_MAX_CONNECTIONS: int = 3
ZERODHA_WS_MAX_INSTRUMENTS: int = 9000          # 3000 per connection x 3
ZERODHA_SESSION_EXPIRY_IST: time(6, 0)          # access_token expires daily at 6 AM IST
ZERODHA_MARKET_PROTECTION: Decimal = Decimal("-1")  # Auto LPP per Kite API
ZERODHA_MONTHLY_FEE: int = 500                  # Rs 500/month
ZERODHA_TAG_MAX_LENGTH: int = 20                # Alphanumeric, per Kite API docs
ZERODHA_NO_SANDBOX: bool = True                 # No test environment available
```

All settings must use `pydantic-settings` with `env_prefix` for override via env vars. Use `Field()` with validation, e.g., `MAX_ORDERS_PER_SECOND` must be > 0 and <= 10. Add `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`.

---

## Instruction 4 — `config/secrets.env.example`

```
# NEVER commit secrets.env — copy this to secrets.env and fill in real values

# Zerodha Kite Connect
ZERODHA_API_KEY=your_api_key_here
ZERODHA_API_SECRET=your_api_secret_here
ZERODHA_ACCESS_TOKEN=                    # Generated daily via OAuth flow; DO NOT persist
ZERODHA_TOTP_SECRET=                    # Optional: for automated daily re-auth (USE AT OWN RISK per Zerodha ToS)

# Angel One (Fallback broker — not yet active)
ANGEL_ONE_API_KEY=
ANGEL_ONE_API_SECRET=
ANGEL_ONE_CLIENT_CODE=
ANGEL_ONE_PASSWORD=
ANGEL_ONE_TOTP_SECRET=

# Dhan (Depth data provider — not yet active)
DHAN_CLIENT_ID=
DHAN_ACCESS_TOKEN=

# Telegram Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Database
TIMESCALEDB_URL=postgresql://trading:password@localhost:5432/trading_bot
TIMESCALEDB_PASSWORD=

# Redis
REDIS_URL=redis://localhost:6379/0

# Encryption
ENCRYPTION_KEY=                         # AES-256-GCM key; generate with:
                                        # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Instruction 5 — `src/risk/compliance.py`

### Requirements

1. **Enum ComplianceLevel:** `UNREGISTERED | REGISTERED`
   - Based on NSE/INVG/67858: <=10 OPS = UNREGISTERED; >10 OPS = REGISTERED

2. **Enum Segments:** `NSE | MCX`

3. **Enum TradingSession:** `PRE_MARKET | REGULAR | POST_MARKET | CLOSED`

4. **Function `get_trading_session(segment: Segments, now: datetime) -> TradingSession`**
   - For NSE: 9:00-9:15 PRE_MARKET, 9:15-15:30 REGULAR, 15:30-15:40 POST_MARKET, else CLOSED
   - For MCX: Use MCX-specific session times from ComplianceSettings

5. **Function `is_order_allowed(session: TradingSession) -> bool`**
   - Only REGULAR session allows orders

6. **Function `check_ops_threshold(current_ops: float, settings: ComplianceSettings) -> ComplianceLevel`**
   - If current_ops <= SEBI_OPS_REGISTRATION_THRESHOLD: return UNREGISTERED
   - Else: return REGISTERED (and log WARNING that registration is required per SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013)

7. **Function `validate_symbol(symbol: str, segment: Segments, settings: ComplianceSettings) -> bool`**
   - Check symbol is in ALLOWED_NSE_INSTRUMENTS or ALLOWED_MCX_INSTRUMENTS

8. **Function `format_algo_tag(strategy_id: str, version: str, max_length: int = 20) -> str`**
   - Format as `"{strategy_id}:{version}"`, truncate to max_length
   - **NOTE:** This is for the Kite API `tag` field (our own audit trail), NOT for exchange algo ID tagging
   - Per SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013: exchange algo ID tagging is BROKER's responsibility
   - We tag orders for our own attribution/audit — the broker handles exchange-mandated algo ID

9. **Constant `SEBI_CIRCULAR_REFERENCES: dict`** mapping each compliance rule to its SEBI circular number
   - `"ops_threshold": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 + NSE/INVG/67858"`
   - `"algo_tagging": "SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 (broker responsibility)"`
   - `"pre_trade_risk": "CIR/MRD/DP/09/2012"`
   - **DO NOT include any reference to "500ms resting time"** — it was never mandated

All functions must be fully type-hinted. Use `structlog` for logging. Add docstrings referencing the specific SEBI circular for each compliance rule.

---

## Instruction 6 — `src/risk/kill_switch.py`

### Requirements

1. **Enum KillSwitchLevel:** `INACTIVE | THROTTLE | PAUSE | KILL`

2. **Dataclass KillSwitchEvent:**
   - `timestamp: datetime`
   - `level: KillSwitchLevel`
   - `trigger_source: str` # "keyboard" | "telegram" | "rest_api" | "auto_margin" | "auto_rejections" | "auto_loss"
   - `reason: str`
   - `previous_level: KillSwitchLevel`

3. **Class KillSwitch:**
   - `__init__(self, settings: KillSwitchSettings, audit_logger)`
   - State: `_current_level: KillSwitchLevel = INACTIVE`
   - State: `_activation_history: list[KillSwitchEvent]`
   - State: `_lock: asyncio.Lock` (thread-safe level changes)

   Methods:
   - `activate(self, level: KillSwitchLevel, source: str, reason: str) -> KillSwitchEvent`
     - Log activation with structlog (CRITICAL level)
     - If KILL: must call `cancel_all_orders()` (stub for now — broker integration in Phase 3)
     - If PAUSE: just prevent new orders
     - If THROTTLE: reduce order rate to `THROTTLE_RATE_PCT`
     - `REQUIRE_MANUAL_RE_ENABLE`: after KILL or PAUSE, require explicit re-enable call
     - Per MiFID II Art. 17, NIST RS.RP-1, ISO A.8.26
   - `deactivate(self, source: str, reason: str) -> KillSwitchEvent`
     - Only allowed if `REQUIRE_MANUAL_RE_ENABLE` and called explicitly
     - Log deactivation
     - Reset to INACTIVE
   - `is_order_allowed(self) -> bool`
     - INACTIVE: True
     - THROTTLE: True but at reduced rate (check against throttle threshold)
     - PAUSE: False (no new orders)
     - KILL: False (no new orders + all cancelled)
   - `get_throttle_rate(self) -> float`
     - If THROTTLE: return `THROTTLE_RATE_PCT x MAX_ORDERS_PER_SECOND`
     - Else: return `MAX_ORDERS_PER_SECOND`
   - `get_state(self) -> dict`
     - Return current level, activation history (last 10), uptime since last change

4. **Keyboard activation handler:**
   - Function `register_keyboard_kill_switch(ks: KillSwitch) -> None`
   - Use `keyboard` library or `pynput` to register Ctrl+Shift+K -> `ks.activate(KILL, "keyboard", "Manual Ctrl+Shift+K")`
   - Log: "Keyboard kill switch registered — press Ctrl+Shift+K to activate"

5. **REST API activation handler (skeleton):**
   - Class `KillSwitchAPI`:
     - `async def handle_kill_request(self, request) -> Response`
     - POST /kill-switch -> activate KILL

6. **Telegram activation handler (skeleton):**
   - Class `KillSwitchTelegramHandler`:
     - `async def handle_kill_command(self, update) -> None`
     - `/kill` -> activate KILL

All methods must be fully type-hinted with async where appropriate. Use structlog for all logging. Every activation/deactivation must be logged as an audit event.

---

## Instruction 7 — `src/risk/manager.py`

### Requirements

1. **Enum RiskCheckResult:** `PASS | FAIL | THROTTLED | KILLED`

2. **Dataclass PreTradeCheckDetail:**
   - `check_name: str`
   - `result: RiskCheckResult`
   - `reason: str | None = None`
   - `sebi_reference: str | None = None`  # Circular number for audit trail

3. **Dataclass PreTradeCheckResult:**
   - `overall_result: RiskCheckResult`
   - `details: list[PreTradeCheckDetail]`
   - `timestamp: datetime`
   - `order_id: str | None = None`

4. **Class RiskManager:**
   - `__init__(self, settings: ComplianceSettings, risk_settings: RiskSettings, kill_switch: KillSwitch)`

   - `async def pre_trade_check(self, order: dict) -> PreTradeCheckResult`
     Run ALL 10 checks sequentially. If ANY fails, return FAIL with reason.

     Per MiFID II RTS 6, FIX Risk Controls, SEBI CIR/MRD/DP/09/2012:

     | Check | Name | Rule | SEBI/Standard Reference |
     |-------|------|------|------------------------|
     | 1 | Symbol Allowlist | order["symbol"] IN allowed symbols for the segment | ISO A.8.26 (application security requirements) |
     | 2 | Trading Hours | get_trading_session(segment, now) == REGULAR | SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 |
     | 3 | Max Order Value | order_value <= MAX_ORDER_VALUE_PER_TRADE | CIR/MRD/DP/09/2012 (quantity limits, exposure limits) |
     | 4 | Daily Order Count | daily_order_count < MAX_ORDERS_PER_DAY | Self-imposed best practice |
     | 5 | Rate Limit | current_rate <= MAX_ORDERS_PER_SECOND (token bucket) | MiFID II RTS 6, FIX Order Throttling, NSE/INVG/67858 |
     | 6 | Margin Available | available_margin >= required_margin (stub) | CIR/MRD/DP/09/2012 (pre-trade risk controls) |
     | 7 | Position Limit | projected_position <= MAX_POSITION_NOTIONAL_PER_SYMBOL | CIR/MRD/DP/09/2012 (exposure limits) |
     | 8 | Max Exposure | total_exposure <= MAX_TOTAL_EXPOSURE | CIR/MRD/DP/09/2012 (exposure limits at individual client level) |
     | 9 | Price Protection | abs(price - ltp) / ltp <= CIRCUIT_LIMIT_PCT | CIR/MRD/DP/09/2012 (price checks); Zerodha market_protection |
     | 10 | Kill Switch Status | kill_switch.is_order_allowed() == True | NIST RS.RP-1, MiFID II Art. 17, ISO A.8.26 |

   - `async def check_daily_loss(self, current_pnl: Decimal) -> KillSwitchLevel | None`
     - If current_pnl <= -DAILY_LOSS_LIMIT: return KILL

   - `async def check_margin_utilization(self, utilization: Decimal) -> KillSwitchLevel | None`
     - If utilization >= MARGIN_UTILIZATION_KILL: return KILL
     - If utilization >= MARGIN_UTILIZATION_THRESHOLD: return THROTTLE + alert

   - `async def check_rejection_rate(self, rejections_last_minute: int) -> KillSwitchLevel | None`
     - If rejections_last_minute >= ORDER_REJECTION_THRESHOLD: return KILL

5. **Class TokenBucketRateLimiter:**
   - `__init__(self, rate: float, capacity: int)`
   - `async def acquire(self) -> bool`  # Returns True if allowed, False if rate exceeded
   - Uses asyncio.Lock internally
   - Implementation: standard token bucket with refill

All methods fully type-hinted. Use structlog. Every check result logged as audit event.

---

## Instruction 8 — `src/risk/audit.py`

### Requirements

1. **Dataclass AuditEvent:**
   - `event_id: UUID`  # Auto-generated
   - `timestamp: datetime`  # timezone-aware (IST/UTC)
   - `event_type: str`  # "ORDER_PLACED", "ORDER_REJECTED", "KILL_SWITCH", etc.
   - `source: str`  # Module/component that generated the event
   - `details: dict`  # Flexible payload
   - `checksum: str`  # SHA-256 of all above fields
   - `ntp_offset_ms: float | None`  # Clock drift at time of event

2. **Class AuditLogger:**
   - `__init__(self, settings: AuditSettings)`
   - `async def log_event(self, event_type: str, source: str, details: dict) -> AuditEvent`
     - Generate event_id (uuid4)
     - Get timestamp from NTP-synchronized clock (or system clock with offset logging)
     - Compute SHA-256 checksum of: `event_id + timestamp.isoformat() + event_type + source + json(details, sort_keys=True)`
     - Log NTP offset (if available)
     - Write to append-only storage (for now: write to file + structlog; TimescaleDB in Phase 3)
     - Per MiFID II Art. 25(1): record keeping; ISO A.8.15: logging
     - Per SEBI: 5+ year retention; we retain 7 years
   - `async def verify_chain_integrity(self) -> bool`
     - Read last N events from storage
     - Recompute checksums and verify
     - Return False if any tampering detected
     - Per NIST AU-9: audit information protection
   - `async def query_events(self, event_type: str | None = None, start: datetime | None = None, end: datetime | None = None, limit: int = 100) -> list[AuditEvent]`
     - Query stored events with filters

3. **Class NTPClock:**
   - `async def get_time(self) -> datetime`
     - Return system time with NTP offset applied if available
   - `async def check_offset(self) -> float`
     - Query NTP server (in.pool.ntp.org)
     - Return offset in milliseconds
     - Alert via structlog if offset > MAX_NTP_OFFSET_MS
     - Per MiFID II: timestamp accuracy; NIST AU-3

4. **Audit event type constants:**
   - `ORDER_PLACED`, `ORDER_FILLED`, `ORDER_REJECTED`, `ORDER_CANCELLED`, `ORDER_MODIFIED`
   - `KILL_SWITCH_ACTIVATED`, `KILL_SWITCH_DEACTIVATED`
   - `RISK_CHECK_PASSED`, `RISK_CHECK_FAILED`
   - `MARGIN_ALERT`, `DAILY_LOSS_LIMIT`
   - `SESSION_START`, `SESSION_END`, `DAILY_RECONCILIATION`
   - `CONFIG_CHANGE`, `STRATEGY_DEPLOYED`, `STRATEGY_STOPPED`

All methods fully type-hinted, async. Use structlog for supplementary logging. SHA-256 checksum per event per Zerodha's own auth checksum approach and NIST AU-9.

---

## Instruction 9 — Docker Infrastructure

### 9.1 `deployment/docker-compose.yml`

```yaml
services:
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    container_name: trading_timescaledb
    environment:
      POSTGRES_USER: trading
      POSTGRES_PASSWORD: ${TIMESCALEDB_PASSWORD}
      POSTGRES_DB: trading_bot
    ports:
      - "5432:5432"
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trading"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: trading_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    container_name: trading_prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: trading_grafana
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  timescaledb_data:
  redis_data:
  prometheus_data:
  grafana_data:
```

### 9.2 `deployment/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY . .
CMD ["python", "-m", "src.main"]
```

### 9.3 `deployment/.env.docker.example`

```
TIMESCALEDB_PASSWORD=change_me_in_production
GRAFANA_PASSWORD=change_me_in_production
REDIS_URL=redis://redis:6379/0
TIMESCALEDB_URL=postgresql://trading:change_me@timescaledb:5432/trading_bot
```

### 9.4 `deployment/init.sql`

```sql
-- Audit trail hypertable (TimescaleDB)
CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    source VARCHAR(100) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    checksum VARCHAR(64) NOT NULL,
    ntp_offset_ms REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('audit_events', 'timestamp', if_not_exists => TRUE);

-- Retention policy: 7 years (SEBI requires 5+)
SELECT add_retention_policy('audit_events', INTERVAL '7 years', if_not_exists => TRUE);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_source ON audit_events (source);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events (timestamp DESC);

-- Prevent deletion (append-only)
CREATE OR REPLACE FUNCTION prevent_audit_deletion()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit events are append-only. Deletion not permitted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_audit_deletion
BEFORE DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_deletion();

-- Prevent updates (append-only)
CREATE OR REPLACE FUNCTION prevent_audit_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit events are append-only. Updates not permitted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_audit_update
BEFORE UPDATE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_update();
```

### 9.5 `deployment/prometheus.yml`

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'trading_bot'
    static_configs:
      - targets: ['host.docker.internal:8000']
```

---

## Instruction 10 — Pre-commit Configuration

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-merge-conflict
      - id: check-added-large-files
        args: ['--maxkb=500']
      - id: detect-private-key
      - id: no-commit-to-branch
        args: ['--branch', 'main']

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: ['--fix', '--exit-non-zero-on-fix']
      - id: ruff-format

  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.9
    hooks:
      - id: bandit
        args: ['-c', 'pyproject.toml']
        additional_dependencies: ['bandit[toml]']

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks

  - repo: https://github.com/PyCQA/docformatter
    rev: v1.7.5
    hooks:
      - id: docformatter
        args: ['--in-place', '--style', 'google']
```

---

## Instruction 11 — Abstract Broker + Strategy + Data Interfaces

### 11.1 `src/brokers/base.py`

Abstract class `BrokerInterface` with methods:
- `async def authenticate(self) -> str`  # Returns access_token
- `async def place_order(self, params: dict) -> dict`
- `async def cancel_order(self, order_id: str) -> dict`
- `async def cancel_all_orders(self) -> list[dict]`
- `async def get_positions(self) -> list[dict]`
- `async def get_margins(self) -> dict`
- `async def get_order_book(self) -> list[dict]`
- `async def get_instruments(self, segment: str) -> list[dict]`

Docstring: "Abstract broker interface. Concrete implementations: Zerodha (Phase 3), Angel One (Phase 14), Dhan (Phase 14)."

### 11.2 `src/strategy/base.py`

Abstract class `StrategyInterface` with methods:
- `async def on_tick(self, tick: dict) -> None`
- `async def on_order_update(self, update: dict) -> None`
- `async def start(self) -> None`
- `async def stop(self) -> None`
- `property strategy_id: str`
- `property version: str`

### 11.3 `src/data/providers.py`

Abstract class `MarketDataProvider` with methods:
- `async def get_quote(self, symbol: str) -> dict`
- `async def get_historical(self, symbol: str, from_date: date, to_date: date) -> pd.DataFrame`
- `async def subscribe(self, symbols: list[str], callback) -> None`

---

## Instruction 12 — Test Suite

### 12.1 `tests/conftest.py`

Shared fixtures:
- `fixture compliance_settings() -> ComplianceSettings` (with test values)
- `fixture risk_settings() -> RiskSettings`
- `fixture kill_switch_settings() -> KillSwitchSettings`
- `fixture audit_settings() -> AuditSettings`
- `fixture kill_switch(kill_switch_settings, audit_logger) -> KillSwitch`
- `fixture risk_manager(settings, risk_settings, kill_switch) -> RiskManager`
- `fixture audit_logger(audit_settings) -> AuditLogger`
- `fixture sample_order() -> dict`  # Valid NIFTY option order

### 12.2 `tests/risk/test_compliance.py`

- `test_get_trading_session_regular_hours`: 10:00 IST -> REGULAR
- `test_get_trading_session_closed`: 20:00 IST -> CLOSED
- `test_get_trading_session_mcx_evening`: 18:00 IST for MCX -> REGULAR
- `test_is_order_allowed_regular`: REGULAR -> True
- `test_is_order_allowed_closed`: CLOSED -> False
- `test_check_ops_threshold_below_10`: 5 OPS -> UNREGISTERED
- `test_check_ops_threshold_above_10`: 15 OPS -> REGISTERED (with warning log)
- `test_validate_symbol_nifty`: "NIFTY" in NSE -> True
- `test_validate_symbol_invalid`: "AAPL" in NSE -> False
- `test_format_algo_tag_normal`: ("MOMENTUM", "V3") -> "MOMENTUM:V3"
- `test_format_algo_tag_truncate`: long strategy_id + version -> truncated to 20 chars

### 12.3 `tests/risk/test_kill_switch.py`

- `test_kill_switch_initial_state`: new KillSwitch -> INACTIVE
- `test_activate_kill`: activate KILL -> level == KILL, is_order_allowed() == False
- `test_activate_pause`: activate PAUSE -> is_order_allowed() == False
- `test_activate_throttle`: activate THROTTLE -> is_order_allowed() == True, rate reduced
- `test_deactivate_requires_manual`: after KILL, cannot auto-resume; require_manual_re_enable == True
- `test_manual_deactivate`: explicit deactivate after KILL -> INACTIVE
- `test_kill_switch_event_logged`: activate produces KillSwitchEvent in history
- `test_double_kill`: activate KILL twice -> second is no-op (already KILL)
- `test_escalation`: THROTTLE -> PAUSE -> KILL escalation works

### 12.4 `tests/risk/test_manager.py`

- `test_pre_trade_check_pass`: valid order -> all 10 checks PASS
- `test_pre_trade_check_fail_symbol`: invalid symbol -> FAIL on check 1
- `test_pre_trade_check_fail_trading_hours`: order at 20:00 -> FAIL on check 2
- `test_pre_trade_check_fail_order_value`: order > Rs 2L -> FAIL on check 3
- `test_pre_trade_check_fail_daily_count`: daily count exceeded -> FAIL on check 4
- `test_pre_trade_check_fail_rate_limit`: too many orders/sec -> FAIL on check 5
- `test_pre_trade_check_fail_kill_switch`: KILL active -> FAIL on check 10
- `test_pre_trade_check_fail_price_protection`: price > 5% from LTP -> FAIL on check 9
- `test_check_daily_loss_exceeded`: P&L <= -50K -> returns KILL
- `test_check_margin_utilization_kill`: 96% -> returns KILL
- `test_check_margin_utilization_throttle`: 85% -> returns THROTTLE
- `test_check_rejection_rate`: 10 rejections/min -> returns KILL

### 12.5 `tests/risk/test_audit.py`

- `test_audit_event_creation`: log_event produces AuditEvent with all fields
- `test_audit_event_checksum`: checksum is valid SHA-256 of event fields
- `test_audit_event_timestamp_ist`: timestamp is timezone-aware
- `test_audit_event_append_only`: events are stored sequentially
- `test_verify_chain_integrity_valid`: fresh chain -> True
- `test_audit_event_types`: all defined event type constants are valid strings
- `test_ntp_clock_offset`: NTPClock returns float offset (mock NTP response)

All tests use `pytest` + `pytest-asyncio` + `pytest-mock`. Tests must pass with:

```bash
pytest tests/ -v --tb=short
```

---

## Instruction 13 — Scripts + Utilities

### 13.1 `scripts/health_check.py`

Async function that checks:
1. TimescaleDB connectivity (or skip if not running)
2. Redis connectivity (or skip if not running)
3. NTP clock offset (warn if > 500ms)
4. Kill switch state (should be INACTIVE)
5. Disk space (warn if < 10GB)
6. Memory usage (warn if > 80%)

Print structured health report using `rich`. Exit code: 0 if all healthy, 1 if any CRITICAL issue.

### 13.2 `scripts/daily_reconcile.py`

Skeleton function that will:
1. Fetch all orders from broker for the day
2. Compare against local audit trail
3. Flag any mismatches
4. Print reconciliation report

For Phase 0: just print "Reconciliation not yet implemented — broker API integration required (Phase 3)"

Per Zerodha API: order book is transient (daily); positions reset for intraday.
Per ISO A.8.15: daily reconciliation is a compliance requirement.

---

## Instruction 14 — Install + Verify All 15 Test Tools

Run these commands sequentially and verify each:

```powershell
# 1. Create virtual environment
python -m venv SBITB150626
SBITB150626\Scripts\activate

# 2. Install project with dev dependencies
pip install -e ".[dev]"

# 3. Verify each tool
pytest --version                    # (1) test runner
pip show pytest-asyncio            # (2) async test support
pytest-cov --version               # (3) coverage
pip show pytest-mock               # (4) mocking
pip show pytest-xdist              # (5) parallel tests
pip show pytest-timeout            # (6) test timeout
pip show pytest-randomly           # (7) random test order
mypy --version                     # (8) type checker
ruff --version                     # (9) linter + formatter
bandit --version                   # (10) security linter
pip-audit --version                # (11) dependency vulnerability scanner
safety --version                   # (12) dependency safety checker
gitleaks version                   # (13) secret detection
trivy --version                    # (14) container vulnerability scanner
detect-secrets --version           # (15) alternative secret scanner

# 4. Run full verification
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
bandit -c pyproject.toml -r src/
pytest tests/ -v --cov=src --cov-report=term-missing

# 5. Install pre-commit hooks
pre-commit install
pre-commit run --all-files

# 6. Verify docker-compose syntax
docker-compose -f deployment/docker-compose.yml config
```

If ANY tool fails to install or run, fix the issue before proceeding.

---

## Cross-Reference Validation

| Item | Status | Notes |
|------|--------|-------|
| 500ms resting time | **REMOVED** | No constant, no reference — confirmed never mandated per SEBI/HO/MRD/DP/CIR/P/2018/62 |
| Algo ID tagging | **CLARIFIED** | `format_algo_tag` is for Kite `tag` field (our audit); exchange algo ID = broker's job per SEBI Feb 2025 circular |
| OPS threshold | **VERIFIED** | 10 OPS per NSE/INVG/67858; self-impose 3 OPS |
| SEBI circular refs | **EVERY FUNCTION** | Each compliance rule references specific circular number |
| MiFID II / NIST / ISO | **INCLUDED** | Kill switch (Art. 17, RS.RP-1), Audit (Art. 25, A.8.15), Risk (CIR/MRD/DP/09/2012) |
| Zerodha constraints | **VERIFIED** | Rs 500/mo, no sandbox, 5-level depth, daily token, BO disabled, tag 20 chars |
| Audit trail | **APPEND-ONLY** | TimescaleDB hypertable with delete/update triggers; 7-year retention |
| Kill switch 3 paths | **IMPLEMENTED** | keyboard, Telegram, REST API |
| Pre-trade 10 checks | **IMPLEMENTED** | All 10 with SEBI circular references |
| Windows 11 compat | **VERIFIED** | All 15 tools native Windows; cosmic-ray/mutmut excluded |

---

## SEBI Circular Reference Card (for agent use)

| Topic | Circular | What it means for our code |
|-------|----------|---------------------------|
| Algo framework | CIR/MRD/DP/09/2012 | Pre-trade risk controls are mandatory (broker implements, we add client-side) |
| 500ms resting | PROPOSED 2016, DROPPED 2018 | **NOT IMPLEMENTED** — do NOT add any resting time check |
| OTR penalties | SEBI/HO/MRD/DP/CIR/P/2018/62 + updates | Apply to brokers; we keep self-imposed rate limits |
| Retail algo framework | SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 | <=10 OPS = no registration; >10 OPS = must register; broker tags orders |
| NSE implementation | NSE/INVG/67858 (May 5, 2025) | 10 OPS threshold; static IP; OAuth/2FA |
| AI/ML disclosure | SEBI/HO/MRD/DOP1/CIR/P/2024/13 | Disclosure-based; black-box needs RA registration (deferred to Phase 17) |
| MCX algo framework | SEBI/HO/CDMRD/DMP/CIR/P/2016/97 | Mirrors equity framework; MCX-specific circulars pending |
