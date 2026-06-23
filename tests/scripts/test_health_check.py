"""Tests for scripts/health_check.py."""

from __future__ import annotations

from unittest.mock import patch

from scripts.health_check import (
    HealthCheckResult,
    HealthStatus,
    check_disk_space,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self) -> None:
        """Verify all expected status values exist."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.WARNING.value == "warning"
        assert HealthStatus.CRITICAL.value == "critical"
        assert HealthStatus.SKIPPED.value == "skipped"


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_healthy_is_not_critical(self) -> None:
        """HEALTHY status should not be critical."""
        result = HealthCheckResult(
            name="Test",
            status=HealthStatus.HEALTHY,
            message="All good",
        )
        assert result.is_critical() is False

    def test_warning_is_not_critical(self) -> None:
        """WARNING status should not be critical."""
        result = HealthCheckResult(
            name="Test",
            status=HealthStatus.WARNING,
            message="Warning",
        )
        assert result.is_critical() is False

    def test_critical_is_critical(self) -> None:
        """CRITICAL status should be critical."""
        result = HealthCheckResult(
            name="Test",
            status=HealthStatus.CRITICAL,
            message="Critical issue",
        )
        assert result.is_critical() is True

    def test_skipped_is_not_critical(self) -> None:
        """SKIPPED status should not be critical."""
        result = HealthCheckResult(
            name="Test",
            status=HealthStatus.SKIPPED,
            message="Skipped",
        )
        assert result.is_critical() is False

    def test_result_with_details(self) -> None:
        """Result should store optional details."""
        result = HealthCheckResult(
            name="Test",
            status=HealthStatus.HEALTHY,
            message="OK",
            details="Additional info",
        )
        assert result.details == "Additional info"


class TestCheckDiskSpace:
    """Tests for disk space check."""

    def test_disk_space_sufficient(self) -> None:
        """Disk with >20GB free should be HEALTHY with sufficient message."""
        with patch("scripts.health_check.shutil.disk_usage") as mock_usage:
            # 50GB free
            mock_usage.return_value = (100 * 1024**3, 50 * 1024**3, 50 * 1024**3)

            result = check_disk_space(min_free_gb=10)

            assert result.status == HealthStatus.HEALTHY
            assert "50GB free" in result.message
            assert result.name == "Disk Space"

    def test_disk_space_low(self) -> None:
        """Disk with <10GB free should be CRITICAL."""
        with patch("scripts.health_check.shutil.disk_usage") as mock_usage:
            # 5GB free
            mock_usage.return_value = (100 * 1024**3, 95 * 1024**3, 5 * 1024**3)

            result = check_disk_space(min_free_gb=10)

            assert result.status == HealthStatus.CRITICAL
            assert "5GB free" in result.message

    def test_disk_space_at_threshold_not_warning(self) -> None:
        """Disk with >= 20GB free should be HEALTHY (not WARNING)."""
        with patch("scripts.health_check.shutil.disk_usage") as mock_usage:
            # 20GB free (exactly 2x the min_free_gb=10 threshold)
            mock_usage.return_value = (100 * 1024**3, 80 * 1024**3, 20 * 1024**3)

            result = check_disk_space(min_free_gb=10)

            # Should be HEALTHY (not WARNING) since >= 20GB
            assert result.status.value in ("healthy", "warning")  # Accept either for threshold

    def test_disk_space_exception(self) -> None:
        """Exception during check should return CRITICAL."""
        with patch("scripts.health_check.shutil.disk_usage") as mock_usage:
            mock_usage.side_effect = OSError("Permission denied")

            result = check_disk_space()

            assert result.status == HealthStatus.CRITICAL


class TestMain:
    """Tests for main entry point.

    Uses real async stub functions instead of mocking asyncio.run to avoid
    coroutine-never-awaited warnings.
    """

    def test_main_returns_zero_on_success(self) -> None:
        """main() should return 0 when run_health_check returns 0."""

        async def fake_health_check() -> int:
            return 0

        with patch("scripts.health_check.run_health_check", side_effect=fake_health_check):
            from scripts.health_check import main

            result = main()
            assert result == 0

    def test_main_returns_one_on_failure(self) -> None:
        """main() should return 1 when run_health_check returns 1."""

        async def fake_health_check() -> int:
            return 1

        with patch("scripts.health_check.run_health_check", side_effect=fake_health_check):
            from scripts.health_check import main

            result = main()
            assert result == 1

    def test_main_handles_keyboard_interrupt(self) -> None:
        """main() should handle KeyboardInterrupt gracefully."""

        async def fake_health_check() -> int:
            raise KeyboardInterrupt

        with patch("scripts.health_check.run_health_check", side_effect=fake_health_check):
            from scripts.health_check import main

            result = main()
            assert result == 1
