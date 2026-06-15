"""Tests for src/risk/kill_switch.py."""

import pytest

from src.risk.kill_switch import KillSwitch, KillSwitchLevel


class TestKillSwitch:
    """Tests for KillSwitch class."""

    def test_kill_switch_initial_state(self, kill_switch: KillSwitch) -> None:
        """New KillSwitch -> INACTIVE."""
        assert kill_switch.is_order_allowed() is True
        state = kill_switch.get_state()
        assert state["current_level"] == "inactive"

    @pytest.mark.asyncio
    async def test_activate_kill(self, kill_switch: KillSwitch) -> None:
        """Activate KILL -> level == KILL, is_order_allowed() == False."""
        event = await kill_switch.activate(
            level=KillSwitchLevel.KILL,
            source="test",
            reason="Test kill",
        )
        assert event.level == KillSwitchLevel.KILL
        assert event.trigger_source == "test"
        assert event.previous_level == KillSwitchLevel.INACTIVE
        assert kill_switch.is_order_allowed() is False
        state = kill_switch.get_state()
        assert state["current_level"] == "kill"

    @pytest.mark.asyncio
    async def test_activate_pause(self, kill_switch: KillSwitch) -> None:
        """Activate PAUSE -> is_order_allowed() == False."""
        await kill_switch.activate(
            level=KillSwitchLevel.PAUSE,
            source="test",
            reason="Test pause",
        )
        assert kill_switch.is_order_allowed() is False

    @pytest.mark.asyncio
    async def test_activate_throttle(self, kill_switch: KillSwitch) -> None:
        """Activate THROTTLE -> is_order_allowed() == True, rate reduced."""
        await kill_switch.activate(
            level=KillSwitchLevel.THROTTLE,
            source="test",
            reason="Test throttle",
        )
        assert kill_switch.is_order_allowed() is True
        rate = kill_switch.get_throttle_rate(3.0)
        assert rate == pytest.approx(0.3)  # 10% of 3

    @pytest.mark.asyncio
    async def test_deactivate_requires_manual(self, kill_switch: KillSwitch) -> None:
        """After KILL, cannot auto-resume."""
        await kill_switch.activate(
            level=KillSwitchLevel.KILL,
            source="test",
            reason="Test",
        )
        with pytest.raises(RuntimeError, match="REQUIRE_MANUAL_RE_ENABLE"):
            await kill_switch.deactivate("test", "auto resume")

    @pytest.mark.asyncio
    async def test_manual_deactivate(self, kill_switch: KillSwitch) -> None:
        """Explicit deactivate after KILL -> INACTIVE."""
        await kill_switch.activate(
            level=KillSwitchLevel.KILL,
            source="test",
            reason="Test",
        )
        # Manually trigger deactivate by temporarily setting require_manual_re_enable=False
        kill_switch._settings.REQUIRE_MANUAL_RE_ENABLE = False
        event = await kill_switch.deactivate("test", "Manual re-enable")
        kill_switch._settings.REQUIRE_MANUAL_RE_ENABLE = True
        assert event.level == KillSwitchLevel.INACTIVE
        assert kill_switch.is_order_allowed() is True

    @pytest.mark.asyncio
    async def test_kill_switch_event_logged(self, kill_switch: KillSwitch) -> None:
        """Activate produces KillSwitchEvent in history."""
        await kill_switch.activate(
            level=KillSwitchLevel.KILL,
            source="test_logger",
            reason="Test event",
        )
        state = kill_switch.get_state()
        history = state["activation_history"]
        assert len(history) == 1
        assert history[0]["source"] == "test_logger"
        assert history[0]["level"] == "kill"

    @pytest.mark.asyncio
    async def test_double_kill(self, kill_switch: KillSwitch) -> None:
        """Activate KILL twice -> second is no-op."""
        await kill_switch.activate(
            level=KillSwitchLevel.KILL,
            source="test",
            reason="First",
        )
        event2 = await kill_switch.activate(
            level=KillSwitchLevel.KILL,
            source="test",
            reason="Second (no-op)",
        )
        # Should return event for the second call too (no-op returns same-level event)
        assert event2.level == KillSwitchLevel.KILL
        state = kill_switch.get_state()
        assert len(state["activation_history"]) == 1

    @pytest.mark.asyncio
    async def test_escalation(self, kill_switch: KillSwitch) -> None:
        """THROTTLE -> PAUSE -> KILL escalation works."""
        await kill_switch.activate(
            level=KillSwitchLevel.THROTTLE,
            source="test",
            reason="Throttle",
        )
        assert kill_switch.get_state()["current_level"] == "throttle"
        assert kill_switch.is_order_allowed() is True

        await kill_switch.activate(
            level=KillSwitchLevel.PAUSE,
            source="test",
            reason="Escalate to pause",
        )
        assert kill_switch.get_state()["current_level"] == "pause"
        assert kill_switch.is_order_allowed() is False

        await kill_switch.activate(
            level=KillSwitchLevel.KILL,
            source="test",
            reason="Escalate to kill",
        )
        assert kill_switch.get_state()["current_level"] == "kill"
        assert kill_switch.is_order_allowed() is False

    @pytest.mark.asyncio
    async def test_get_throttle_rate_kill(self) -> None:
        """THROTTLE returns 0 for rate when at KILL."""
        await self._activate_and_check(KillSwitchLevel.KILL, expected_rate=0.0)

    @pytest.mark.asyncio
    async def test_get_throttle_rate_inactive(self) -> None:
        """INACTIVE returns full rate."""
        await self._activate_and_check(KillSwitchLevel.INACTIVE, expected_rate=3.0)

    async def _activate_and_check(self, level: KillSwitchLevel, expected_rate: float) -> None:
        """Helper to activate level and check throttle rate."""
        from config.settings import KillSwitchSettings
        from src.risk.kill_switch import KillSwitch

        settings = KillSwitchSettings()
        ks = KillSwitch(settings)
        await ks.activate(level, "test", "test")
        rate = ks.get_throttle_rate(3.0)
        assert rate == pytest.approx(expected_rate)
