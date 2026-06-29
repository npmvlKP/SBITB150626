"""OpenAlgo-compatible NIFTY Options Strategy — Technical & Volume Analysis Engine.

This package is a standalone, self-hosted OpenAlgo Python strategy that runs
as an isolated subprocess inside the OpenAlgo platform (http://127.0.0.1:5000).

It replaces the heavy broker/data/storage stack (kiteconnect, psycopg, redis,
py_vollib, QuantLib, TA-Lib C library) with:
  - OpenAlgo unified SDK (`from openalgo import api`) for all broker/data operations
  - Pure-Python technical indicators (no TA-Lib C dependency)
  - OpenAlgo OptionGreeks API for Greeks (no py_vollib/QuantLib)

Environment variables (auto-injected by OpenAlgo):
  OPENALGO_API_KEY  — decrypted API key
  STRATEGY_ID       — unique strategy instance identifier
  OPENALGO_HOST     — internal host URL (http://127.0.0.1:5000)
  OPENALGO_WS_URL   — WebSocket URL (ws://127.0.0.1:8765)
"""

__version__ = "1.0.0"
