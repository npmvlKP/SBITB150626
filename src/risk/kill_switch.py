"""Kill switch — emergency halt with 3 activation paths.

Per MiFID II Art. 17, NIST RS.RP-1, ISO A.8.26.

Activation paths:
  1. Keyboard: Ctrl+Shift+K (via pynput)
  2. Telegram: /kill command
  3. REST API: POST /kill-switch

After KILL/PAUSE, REQUIRE_MANUAL_RE_ENABLE=True prevents auto-resume.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from config.settings import KillSwitchSettings
    from src.risk.audit import AuditLogger

logger = structlog.get_logger(__name__)


class KillSwitchLevel(Enum):
    """Kill switch escalation levels.

    INACTIVE  → Normal operation
    THROTTLE  → Reduced order rate (10% of normal)
    PAUSE     → No new orders, existing held
    KILL      → No new orders + cancel all existing
    """

    INACTIVE = "inactive"
    THROTTLE = "throttle"
    PAUSE = "pause"
    KILL = "kill"


@dataclass
class KillSwitchEvent:
    """Record of kill switch state change."""

    timestamp: datetime
    level: KillSwitchLevel
    trigger_source: str
    reason: str
    previous_level: KillSwitchLevel


class KillSwitch:
    """Thread-safe kill switch with 3 activation paths.

    Args:
        settings: KillSwitchSettings configuration
        audit_logger: AuditLogger for audit trail events
    """

    def __init__(self, settings: KillSwitchSettings, audit_logger: AuditLogger | None = None) -> None:
        self._settings = settings
        self._audit_logger = audit_logger
        self._current_level: KillSwitchLevel = KillSwitchLevel.INACTIVE
        self._activation_history: list[KillSwitchEvent] = []
        self._lock: asyncio.Lock | None = None  # Lazily initialized in async context
        self._last_change_time: datetime = datetime.utcnow()

        logger.info(
            "kill_switch_initialized",
            require_manual_re_enable=settings.REQUIRE_MANUAL_RE_ENABLE,
            throttle_rate_pct=float(settings.THROTTLE_RATE_PCT),
            activation_paths=settings.ACTIVATION_PATHS,
        )

    @property
    def _async_lock(self) -> asyncio.Lock:
        """Lazily initialize the asyncio lock (must be created within an event loop)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def activate(self, level: KillSwitchLevel, source: str, reason: str) -> KillSwitchEvent:
        """Activate or escalate kill switch level.

        Args:
            level: Target kill switch level
            source: Trigger source ("keyboard", "telegram", "rest_api", "auto_*")
            reason: Human-readable reason

        Returns:
            KillSwitchEvent record
        """
        async with self._async_lock:
            previous_level = self._current_level

            if self._current_level == level:
                logger.debug("kill_switch_already_at_level", level=level.value, source=source)
                return KillSwitchEvent(
                    timestamp=datetime.utcnow(),
                    level=level,
                    trigger_source=source,
                    reason=reason,
                    previous_level=previous_level,
                )

            self._current_level = level
            self._last_change_time = datetime.utcnow()

            event = KillSwitchEvent(
                timestamp=datetime.utcnow(),
                level=level,
                trigger_source=source,
                reason=reason,
                previous_level=previous_level,
            )
            self._activation_history.append(event)

            if len(self._activation_history) > 100:
                self._activation_history = self._activation_history[-100:]

            logger.critical(
                "kill_switch_activated",
                level=level.value,
                source=source,
                reason=reason,
                previous_level=previous_level.value,
            )

            if level == KillSwitchLevel.KILL:
                await self._cancel_all_orders()

            return event

    async def deactivate(self, source: str, reason: str) -> KillSwitchEvent:
        """Deactivate kill switch — requires manual re-enable.

        Args:
            source: Caller identifier
            reason: Reason for deactivation

        Returns:
            KillSwitchEvent record

        Raises:
            RuntimeError: If REQUIRE_MANUAL_RE_ENABLE is True and called automatically
        """
        if not self._settings.REQUIRE_MANUAL_RE_ENABLE:
            async with self._async_lock:
                previous_level = self._current_level
                self._current_level = KillSwitchLevel.INACTIVE
                self._last_change_time = datetime.utcnow()

                event = KillSwitchEvent(
                    timestamp=datetime.utcnow(),
                    level=KillSwitchLevel.INACTIVE,
                    trigger_source=source,
                    reason=reason,
                    previous_level=previous_level,
                )
                self._activation_history.append(event)

                logger.info(
                    "kill_switch_deactivated",
                    source=source,
                    reason=reason,
                    previous_level=previous_level.value,
                )
                return event

        raise RuntimeError("Auto-resume not permitted — REQUIRE_MANUAL_RE_ENABLE is True")

    def is_order_allowed(self) -> bool:
        """Check if new orders are permitted at current level.

        Returns:
            True for INACTIVE/THROTTLE, False for PAUSE/KILL
        """
        return self._current_level in (
            KillSwitchLevel.INACTIVE,
            KillSwitchLevel.THROTTLE,
        )

    def get_throttle_rate(self, max_orders_per_second: float = 3.0) -> float:
        """Get allowed order rate based on current level.

        Args:
            max_orders_per_second: Base rate from settings

        Returns:
            Effective rate: full rate for INACTIVE, THROTTLE_RATE_PCT for THROTTLE,
            0 for PAUSE/KILL
        """
        if self._current_level == KillSwitchLevel.THROTTLE:
            return float(self._settings.THROTTLE_RATE_PCT) * max_orders_per_second
        if self._current_level in (KillSwitchLevel.PAUSE, KillSwitchLevel.KILL):
            return 0.0
        return max_orders_per_second

    def get_state(self) -> dict:
        """Return current kill switch state for monitoring.

        Returns:
            Dict with current level, last 10 events, uptime
        """
        return {
            "current_level": self._current_level.value,
            "activation_history": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "level": e.level.value,
                    "source": e.trigger_source,
                    "reason": e.reason,
                }
                for e in self._activation_history[-10:]
            ],
            "uptime_since_last_change_seconds": (datetime.utcnow() - self._last_change_time).total_seconds(),
            "require_manual_re_enable": self._settings.REQUIRE_MANUAL_RE_ENABLE,
        }

    async def _cancel_all_orders(self) -> None:
        """Cancel all open orders — stub for Phase 3 broker integration."""
        logger.warning("kill_switch_cancel_all_orders_stub", note="broker integration in Phase 3")


class KillSwitchAPI:
    """REST API handler for kill switch activation — skeleton for Phase 3."""

    def __init__(self, kill_switch: KillSwitch) -> None:
        self._kill_switch = kill_switch

    async def handle_kill_request(self, request: dict) -> dict:
        """Handle POST /kill-switch request.

        Args:
            request: Request body with optional 'level' and 'reason'

        Returns:
            Response dict with status
        """
        level_str = request.get("level", "kill")
        reason = request.get("reason", "REST API kill request")

        try:
            level = KillSwitchLevel(level_str.lower())
        except ValueError:
            level = KillSwitchLevel.KILL

        event = await self._kill_switch.activate(level=level, source="rest_api", reason=reason)

        return {
            "status": "ok",
            "level": event.level.value,
            "timestamp": event.timestamp.isoformat(),
        }


class KillSwitchTelegramHandler:
    """Telegram handler for /kill command — skeleton for Phase 3."""

    def __init__(self, kill_switch: KillSwitch) -> None:
        self._kill_switch = kill_switch

    async def handle_kill_command(self, update: dict) -> None:
        """Handle /kill Telegram command.

        Args:
            update: Telegram update dict
        """
        event = await self._kill_switch.activate(
            level=KillSwitchLevel.KILL,
            source="telegram",
            reason=f"Telegram command from {update.get('chat_id', 'unknown')}",
        )
        logger.info("telegram_kill_activated", event=event)


def register_keyboard_kill_switch(ks: KillSwitch) -> None:
    """Register Ctrl+Shift+K global hotkey using pynput.

    On Windows, registers a low-level keyboard hook.

    Args:
        ks: KillSwitch instance to activate

    Note:
        Uses pynput for cross-platform keyboard monitoring.
        Must be called from main thread.
    """
    try:
        from pynput import keyboard

        def on_activate_kill() -> None:
            """Callback on Ctrl+Shift+K detection."""
            # Fire-and-forget: kill switch activation must not block keyboard hook
            asyncio.create_task(  # noqa: RUF006
                ks.activate(
                    level=KillSwitchLevel.KILL,
                    source="keyboard",
                    reason="Manual Ctrl+Shift+K activation",
                )
            )

        with keyboard.GlobalHotKeys({"<ctrl>+<shift>+k": on_activate_kill}) as h:
            logger.info("keyboard_kill_switch_registered", hotkey="Ctrl+Shift+K")
            h.join()

    except ImportError:
        logger.warning(
            "keyboard_kill_switch_not_available",
            reason="pynput not installed",
            install="pip install pynput",
        )
    except Exception as e:
        logger.error("keyboard_kill_switch_registration_failed", error=str(e))
