"""Locust load testing for Phase 2 infrastructure.

Run with: locust -f tests/load/locustfile.py --host=http://localhost:8000

Or headless mode:
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
           --users=100 --spawn-rate=10 --run-time=60s --headless
"""

from decimal import Decimal
from typing import Any
from uuid import uuid4

from locust import HttpUser, between, task

# ============================================================================
# User 1: Market Data User — high-frequency requests
# ============================================================================


class MarketDataUser(HttpUser):
    """Simulates market data polling (quote requests)."""

    wait_time = between(0.5, 1.5)  # 0.5-1.5s between requests

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._symbols = ["NIFTY", "BANKNIFTY"]
        self._token = str(uuid4())

    @task(10)
    def get_quote(self) -> None:
        """Fetch current quote for random symbol."""
        symbol = self._symbols[self._rand_int() % len(self._symbols)]
        self.client.get(
            f"/api/v1/quote/{symbol}",
            name="/api/v1/quote/[symbol]",
            headers={"X-Request-ID": str(uuid4())},
        )

    @task(5)
    def get_option_chain(self) -> None:
        """Fetch option chain for symbol."""
        symbol = self._symbols[self._rand_int() % len(self._symbols)]
        self.client.get(
            f"/api/v1/options/chain/{symbol}",
            name="/api/v1/options/chain/[symbol]",
            params={"expiry": "2026-06-26"},
            headers={"X-Request-ID": str(uuid4())},
        )

    @task(2)
    def get_greeks(self) -> None:
        """Fetch Greeks for ATM option."""
        symbol = self._symbols[self._rand_int() % len(self._symbols)]
        self.client.get(
            f"/api/v1/greeks/{symbol}",
            name="/api/v1/greeks/[symbol]",
            params={"expiry": "2026-06-26", "strike": "25000"},
            headers={"X-Request-ID": str(uuid4())},
        )

    def _rand_int(self) -> int:
        """Generate pseudo-random integer."""
        import hashlib

        return int(hashlib.md5(f"{self._token}{uuid4()}".encode()).hexdigest()[:8], 16)


# ============================================================================
# User 2: Order Management User — order lifecycle requests
# ============================================================================


class OrderManagementUser(HttpUser):
    """Simulates order placement and management."""

    wait_time = between(2.0, 5.0)  # 2-5s between requests

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._order_id: str | None = None
        self._token = str(uuid4())

    @task(5)
    def place_order(self) -> None:
        """Place a new limit order."""
        payload = {
            "symbol": "NIFTY",
            "quantity": 50,
            "price": str(Decimal("25000.00")),
            "order_type": "LIMIT",
            "side": "BUY",
        }
        response = self.client.post(
            "/api/v1/orders",
            json=payload,
            headers={
                "X-Request-ID": str(uuid4()),
                "Content-Type": "application/json",
            },
            name="/api/v1/orders [POST]",
        )
        if response.status_code == 201:
            data = response.json()
            self._order_id = data.get("order_id")

    @task(3)
    def get_order_status(self) -> None:
        """Get order status by ID."""
        if self._order_id:
            self.client.get(
                f"/api/v1/orders/{self._order_id}",
                name="/api/v1/orders/[id]",
                headers={"X-Request-ID": str(uuid4())},
            )

    @task(2)
    def cancel_order(self) -> None:
        """Cancel an existing order."""
        if self._order_id:
            self.client.delete(
                f"/api/v1/orders/{self._order_id}",
                name="/api/v1/orders/[id] [DELETE]",
                headers={"X-Request-ID": str(uuid4())},
            )
            self._order_id = None

    @task(1)
    def list_orders(self) -> None:
        """List all open orders."""
        self.client.get(
            "/api/v1/orders",
            name="/api/v1/orders [LIST]",
            params={"status": "OPEN"},
            headers={"X-Request-ID": str(uuid4())},
        )


# ============================================================================
# User 3: Analytics User — heavy aggregation queries
# ============================================================================


class AnalyticsUser(HttpUser):
    """Simulates analytics dashboard queries."""

    wait_time = between(5.0, 15.0)  # 5-15s between requests

    @task(3)
    def get_portfolio_summary(self) -> None:
        """Fetch portfolio summary with positions."""
        self.client.get(
            "/api/v1/analytics/portfolio",
            name="/api/v1/analytics/portfolio",
            headers={"X-Request-ID": str(uuid4())},
        )

    @task(2)
    def get_risk_metrics(self) -> None:
        """Fetch VaR and risk metrics."""
        self.client.get(
            "/api/v1/analytics/risk",
            name="/api/v1/analytics/risk",
            params={"confidence": "0.99", "lookback": "30"},
            headers={"X-Request-ID": str(uuid4())},
        )

    @task(1)
    def get_performance_report(self) -> None:
        """Fetch performance metrics."""
        self.client.get(
            "/api/v1/analytics/performance",
            name="/api/v1/analytics/performance",
            params={
                "start_date": "2026-06-01",
                "end_date": "2026-06-20",
            },
            headers={"X-Request-ID": str(uuid4())},
        )


# ============================================================================
# User 4: Historical Data User — large data queries
# ============================================================================


class HistoricalDataUser(HttpUser):
    """Simulates historical data retrieval."""

    wait_time = between(10.0, 30.0)  # 10-30s between requests

    @task(3)
    def get_bhavcopy(self) -> None:
        """Download daily Bhavcopy."""
        self.client.get(
            "/api/v1/data/bhavcopy",
            name="/api/v1/data/bhavcopy",
            params={
                "date": "2026-06-20",
                "segment": "NSE_FO",
            },
            headers={"X-Request-ID": str(uuid4())},
        )

    @task(2)
    def get_historical_prices(self) -> None:
        """Fetch historical OHLCV data."""
        self.client.get(
            "/api/v1/data/historical",
            name="/api/v1/data/historical",
            params={
                "symbol": "NIFTY",
                "interval": "1d",
                "from": "2026-05-01",
                "to": "2026-06-20",
            },
            headers={"X-Request-ID": str(uuid4())},
        )

    @task(1)
    def get_greeks_history(self) -> None:
        """Fetch historical Greeks snapshots."""
        self.client.get(
            "/api/v1/data/greeks",
            name="/api/v1/data/greeks",
            params={
                "symbol": "NIFTY",
                "from": "2026-06-01",
                "to": "2026-06-20",
            },
            headers={"X-Request-ID": str(uuid4())},
        )


# ============================================================================
# User 5: WebSocket Stress User — connection churn
# ============================================================================


class WebSocketStressUser(HttpUser):
    """Simulates rapid WebSocket connect/disconnect cycles."""

    wait_time = between(1.0, 3.0)  # 1-3s between cycles

    @task
    def connect_and_subscribe(self) -> None:
        """Connect to WebSocket and subscribe to instrument."""
        import base64
        import json
        import time

        # Generate auth token
        auth_data = {
            "api_key": "test_key",
            "timestamp": int(time.time()),
        }
        auth_token = base64.b64encode(json.dumps(auth_data).encode()).decode()

        ws_url = self.host.replace("http", "ws") + "/ws/market"
        headers = {"Authorization": f"Bearer {auth_token}"}

        with self.client.websocket_connect(ws_url, headers=headers) as ws:
            # Subscribe to tick data
            ws.send(
                json.dumps(
                    {
                        "type": "subscribe",
                        "instruments": ["NIFTY", "BANKNIFTY"],
                        "mode": "full",
                    }
                )
            )

            # Receive a few ticks
            for _ in range(3):
                try:
                    ws.receive(timeout=5)
                except Exception:
                    break


# ============================================================================
# User 6: Benchmark User — mixed workload
# ============================================================================


class BenchmarkUser(HttpUser):
    """Mixed workload simulating realistic trading session."""

    wait_time = between(1.0, 3.0)

    @task(6)
    def quick_quote(self) -> None:
        """Quick quote check."""
        self.client.get(
            "/api/v1/quote/NIFTY",
            name="/api/v1/quote/[symbol]",
            headers={"X-Request-ID": str(uuid4())},
        )

    @task(3)
    def place_and_check_order(self) -> None:
        """Place order then immediately check status."""
        payload = {
            "symbol": "NIFTY",
            "quantity": 25,
            "price": str(Decimal("25100.00")),
            "order_type": "LIMIT",
            "side": "BUY",
        }
        response = self.client.post(
            "/api/v1/orders",
            json=payload,
            headers={"X-Request-ID": str(uuid4())},
            name="/api/v1/orders [POST]",
        )
        if response.status_code == 201:
            data = response.json()
            order_id = data.get("order_id")
            if order_id:
                self.client.get(
                    f"/api/v1/orders/{order_id}",
                    name="/api/v1/orders/[id]",
                    headers={"X-Request-ID": str(uuid4())},
                )

    @task(2)
    def check_portfolio(self) -> None:
        """Quick portfolio check."""
        self.client.get(
            "/api/v1/analytics/portfolio",
            name="/api/v1/analytics/portfolio",
            headers={"X-Request-ID": str(uuid4())},
        )

    @task(1)
    def health_check(self) -> None:
        """Health check."""
        self.client.get(
            "/health",
            name="/health",
            headers={"X-Request-ID": str(uuid4())},
        )
