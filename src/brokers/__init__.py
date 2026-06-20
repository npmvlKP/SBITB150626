"""Brokers package.

Abstract broker interface and concrete implementations for multi-broker support.

Concrete implementations:
    - KiteBroker: Zerodha KiteConnect (Phase 2)
    - AngelBroker: Angel One SmartAPI (Phase 16 stub)
    - DhanBroker: Dhan API (Phase 16 stub)
"""

from __future__ import annotations

from .angelone import AngelBroker
from .base import BrokerInterface, TickCallback
from .dhan import DhanBroker
from .zerodha import KiteBroker

__all__ = [
    "BrokerInterface",
    "TickCallback",
    "KiteBroker",
    "AngelBroker",
    "DhanBroker",
]
