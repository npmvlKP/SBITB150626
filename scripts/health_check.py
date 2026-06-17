"""Pre-market health check — verify all systems are operational.

Checks:
  1. TimescaleDB connectivity
  2. Redis connectivity
  3. NTP clock offset (warn if > 500ms)
  4. Kill switch state (should be INACTIVE)
  5. Disk space (warn if < 10GB)
  6. Memory usage (warn if > 80%)

Exit code: 0 if all healthy, 1 if any CRITICAL issue.

Per MiFID II Art. 17, NIST RS.RP-1, ISO A.8.26 for kill switch.
Per SEBI: 5+ year retention (we retain 7 years).
"""

from __future__ import annotations

import asyncio
import io
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


def _setup_windows_utf8() -> None:
    """Set UTF-8 encoding for Windows console output.

    This ensures special characters (check marks, warnings) display correctly
    on Windows terminals that default to 'charmap' encoding.
    """
    if sys.platform == "win32":
        # Reconfigure stdout/stderr to use UTF-8 encoding
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


class HealthStatus(Enum):
    """Health check status levels."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    SKIPPED = "skipped"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    status: HealthStatus
    message: str
    details: str | None = None

    def is_critical(self) -> bool:
        """Check if this result represents a critical failure."""
        return self.status == HealthStatus.CRITICAL


def _get_ist_timestamp() -> str:
    """Get current timestamp in IST timezone.

    Returns:
        ISO format timestamp string with IST timezone
    """
    ist = timezone(datetime.now().astimezone().utcoffset())  # type: ignore[arg-type]
    return datetime.now(ist).strftime("%Y-%m-%dT%H:%M:%S %Z")


async def check_db_connectivity() -> HealthCheckResult:
    """Check TimescaleDB connectivity.

    Returns:
        HealthCheckResult with connectivity status
    """
    try:
        import asyncpg

        try:
            conn = await asyncio.wait_for(
                asyncpg.connect(
                    host="localhost",
                    port=5432,
                    user="trading",
                    password="password",
                    database="trading_bot",
                    timeout=5,
                ),
                timeout=10,
            )
            await conn.close()
            return HealthCheckResult(
                name="TimescaleDB",
                status=HealthStatus.HEALTHY,
                message="Connected successfully",
                details="postgresql://localhost:5432/trading_bot",
            )
        except asyncpg.InvalidCatalogNameError:
            # Database doesn't exist - skip gracefully
            return HealthCheckResult(
                name="TimescaleDB",
                status=HealthStatus.SKIPPED,
                message="Database not configured",
                details="TimescaleDB is optional for Phase 0",
            )
    except ImportError:
        return HealthCheckResult(
            name="TimescaleDB",
            status=HealthStatus.SKIPPED,
            message="asyncpg not installed",
            details="pip install asyncpg for database connectivity",
        )
    except Exception as e:  # noqa: BLE001
        return HealthCheckResult(
            name="TimescaleDB",
            status=HealthStatus.SKIPPED,
            message=f"Not running or unavailable: {type(e).__name__}",
            details="TimescaleDB is optional - continuing without it",
        )


async def check_redis_connectivity() -> HealthCheckResult:
    """Check Redis connectivity.

    Returns:
        HealthCheckResult with connectivity status
    """
    try:
        import redis.asyncio as redis

        try:
            client = redis.from_url(
                "redis://localhost:6379/0",
                socket_connect_timeout=5,
            )
            await asyncio.wait_for(client.ping(), timeout=10)
            await client.aclose()
            return HealthCheckResult(
                name="Redis",
                status=HealthStatus.HEALTHY,
                message="Connected successfully",
                details="redis://localhost:6379/0",
            )
        except Exception as e:
            return HealthCheckResult(
                name="Redis",
                status=HealthStatus.SKIPPED,
                message=f"Not running: {type(e).__name__}",
                details="Redis is optional for Phase 0",
            )
    except ImportError:
        return HealthCheckResult(
            name="Redis",
            status=HealthStatus.SKIPPED,
            message="redis package not installed",
            details="pip install redis for caching support",
        )


async def check_ntp_clock(max_offset_ms: int = 500) -> HealthCheckResult:
    """Check NTP clock offset against configured server.

    Args:
        max_offset_ms: Maximum allowed offset in milliseconds

    Returns:
        HealthCheckResult with NTP offset status
    """
    try:
        import ntplib

        settings = {"NTP_SERVER": "in.pool.ntp.org", "MAX_NTP_OFFSET_MS": max_offset_ms}
        client = ntplib.NTPClient()
        response = client.request(settings["NTP_SERVER"], timeout=5)
        offset_ms = response.offset * 1000

        status = HealthStatus.HEALTHY
        message = "Clock synchronized"

        if abs(offset_ms) > settings["MAX_NTP_OFFSET_MS"]:
            status = HealthStatus.WARNING
            message = "Clock drift detected"
            logger.warning(
                "ntp_clock_drift",
                offset_ms=offset_ms,
                max_allowed=settings["MAX_NTP_OFFSET_MS"],
            )

        return HealthCheckResult(
            name="NTP Clock",
            status=status,
            message=message,
            details=f"Offset: {offset_ms:.1f}ms (max: +/-{settings['MAX_NTP_OFFSET_MS']}ms)",
        )
    except ImportError:
        return HealthCheckResult(
            name="NTP Clock",
            status=HealthStatus.WARNING,
            message="ntplib not installed - cannot verify clock sync",
            details="pip install ntplib for NTP checks",
        )
    except Exception as e:  # noqa: BLE001
        return HealthCheckResult(
            name="NTP Clock",
            status=HealthStatus.WARNING,
            message=f"NTP server unavailable: {type(e).__name__}",
            details="Clock may drift from IST time - manual verification recommended",
        )


def check_kill_switch_state() -> HealthCheckResult:
    """Check kill switch state is INACTIVE.

    Returns:
        HealthCheckResult with kill switch status
    """
    try:
        from config.settings import KillSwitchSettings
        from src.risk.kill_switch import KillSwitch, KillSwitchLevel

        settings = KillSwitchSettings()
        ks = KillSwitch(settings)
        state = ks.get_state()
        current_level = state["current_level"]

        if current_level == KillSwitchLevel.INACTIVE.value:
            return HealthCheckResult(
                name="Kill Switch",
                status=HealthStatus.HEALTHY,
                message="System armed and ready",
                details=f"Level: {current_level.upper()}",
            )
        return HealthCheckResult(
            name="Kill Switch",
            status=HealthStatus.CRITICAL,
            message=f"Kill switch is ACTIVE: {current_level.upper()}",
            details="Trading halted - investigate immediately",
        )
    except Exception as e:  # noqa: BLE001
        return HealthCheckResult(
            name="Kill Switch",
            status=HealthStatus.CRITICAL,
            message=f"Cannot verify kill switch: {type(e).__name__}",
            details="Safe state assumed - manual verification required",
        )


def check_disk_space(min_free_gb: int = 10) -> HealthCheckResult:
    """Check available disk space.

    Args:
        min_free_gb: Minimum required free space in GB

    Returns:
        HealthCheckResult with disk space status
    """
    try:
        _total, _used, free = shutil.disk_usage("/")
        free_gb = free // (2**30)

        if free_gb < min_free_gb:
            return HealthCheckResult(
                name="Disk Space",
                status=HealthStatus.CRITICAL,
                message=f"Low disk space: {free_gb}GB free",
                details=f"Minimum required: {min_free_gb}GB",
            )

        status = HealthStatus.HEALTHY
        message = f"Sufficient space: {free_gb}GB free"

        if free_gb < min_free_gb * 2:
            status = HealthStatus.WARNING
            message = f"Limited disk space: {free_gb}GB free"

        return HealthCheckResult(
            name="Disk Space",
            status=status,
            message=message,
            details=f"Total: {_total // (2**30)}GB, Used: {_used // (2**30)}GB, Free: {free_gb}GB",
        )
    except Exception as e:  # noqa: BLE001
        return HealthCheckResult(
            name="Disk Space",
            status=HealthStatus.CRITICAL,
            message=f"Cannot check disk space: {type(e).__name__}",
            details="Manual verification required",
        )


def check_memory_usage(warn_threshold: float = 80.0) -> HealthCheckResult:
    """Check system memory usage.

    Args:
        warn_threshold: Warning threshold percentage

    Returns:
        HealthCheckResult with memory usage status
    """
    try:
        import psutil

        mem = psutil.virtual_memory()
        used_pct = mem.percent
        available_gb = mem.available / (2**30)
        total_gb = mem.total / (2**30)

        if used_pct > warn_threshold:
            return HealthCheckResult(
                name="Memory",
                status=HealthStatus.WARNING,
                message=f"High memory usage: {used_pct:.1f}%",
                details=f"Available: {available_gb:.1f}GB / {total_gb:.1f}GB total",
            )

        return HealthCheckResult(
            name="Memory",
            status=HealthStatus.HEALTHY,
            message=f"Memory usage OK: {used_pct:.1f}%",
            details=f"Available: {available_gb:.1f}GB / {total_gb:.1f}GB total",
        )
    except ImportError:
        return HealthCheckResult(
            name="Memory",
            status=HealthStatus.SKIPPED,
            message="psutil not installed",
            details="pip install psutil for memory monitoring",
        )
    except Exception as e:  # noqa: BLE001
        return HealthCheckResult(
            name="Memory",
            status=HealthStatus.WARNING,
            message=f"Cannot check memory: {type(e).__name__}",
            details="Manual verification recommended",
        )


async def run_health_check() -> int:
    """Run all health checks and print structured report.

    Returns:
        Exit code: 0 if all healthy, 1 if any CRITICAL issue
    """
    console_available = False
    try:
        import rich.console  # noqa: F401
    except ImportError:
        logger.warning("rich_not_installed_using_console_output")
    else:
        console_available = True

    # Run sync checks (they execute immediately)
    sync_results = [
        check_disk_space(min_free_gb=10),
        check_memory_usage(warn_threshold=80.0),
        check_kill_switch_state(),
    ]

    # Run async checks concurrently
    async_results = await asyncio.gather(
        check_ntp_clock(max_offset_ms=500),
        check_db_connectivity(),
        check_redis_connectivity(),
        return_exceptions=True,  # Don't let one failure crash everything
    )

    # Combine all results
    processed_results: list[HealthCheckResult] = []

    # Add sync results (already executed)
    for result in sync_results:
        if isinstance(result, HealthCheckResult):
            processed_results.append(result)
        else:
            # Handle unexpected types
            processed_results.append(
                HealthCheckResult(
                    name="Unknown",
                    status=HealthStatus.CRITICAL,
                    message=f"Unexpected result type: {type(result).__name__}",
                )
            )

    # Add async results (already awaited by gather)
    for result in async_results:
        if isinstance(result, HealthCheckResult):
            processed_results.append(result)
        elif isinstance(result, Exception):
            # Log exception from gather but don't crash
            logger.warning(
                "health_check_async_exception",
                error=str(result),
                error_type=type(result).__name__,
            )
            processed_results.append(
                HealthCheckResult(
                    name="Async Check",
                    status=HealthStatus.WARNING,
                    message=f"Check failed: {type(result).__name__}",
                    details=str(result),
                )
            )
        else:
            processed_results.append(
                HealthCheckResult(
                    name="Unknown",
                    status=HealthStatus.CRITICAL,
                    message=f"Unexpected result type: {type(result).__name__}",
                )
            )

    # Count critical issues
    critical_count = sum(1 for r in processed_results if r.is_critical())

    if console_available:
        _print_rich_report(processed_results, critical_count)
    else:
        _print_console_report(processed_results, critical_count)

    if critical_count > 0:
        logger.error("health_check_critical_issues", count=critical_count)
        return 1

    logger.info("health_check_all_passed", checks=len(processed_results))
    return 0


def _print_rich_report(results: list[HealthCheckResult], critical_count: int) -> None:
    """Print formatted report using rich library.

    Args:
        results: List of health check results
        critical_count: Number of critical issues
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print()
    console.print("[bold blue]============================================================[/bold blue]")
    console.print("[bold blue]          SBITB-150626 Health Check Report                  [/bold blue]")
    console.print("[bold blue]============================================================[/bold blue]")
    console.print(f"Timestamp : {_get_ist_timestamp()}")
    console.print(f"Checks    : {len(results)} total")
    console.print()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Check", style="cyan", width=18)
    table.add_column("Status", style="bold", width=12)
    table.add_column("Details", style="dim")

    for result in results:
        status_icon = _get_status_icon(result.status)
        table.add_row(
            result.name,
            f"{status_icon} {result.status.value.upper()}",
            result.details or result.message,
        )

    console.print(table)
    console.print()

    # Summary
    if critical_count > 0:
        console.print(f"[bold red]WARNING: {critical_count} critical issue(s) found - DO NOT TRADE[/bold red]")
        console.print("[yellow]Fix all critical issues before proceeding.[/yellow]")
    else:
        console.print("[bold green]OK: All checks passed - System ready for trading[/bold green]")

    console.print()


def _print_console_report(results: list[HealthCheckResult], critical_count: int) -> None:
    """Print report to stdout without rich library.

    Args:
        results: List of health check results
        critical_count: Number of critical issues
    """
    print("\n" + "=" * 60)
    print("          SBITB-150626 Health Check Report")
    print("=" * 60)
    print(f"Timestamp : {_get_ist_timestamp()}")
    print(f"Checks    : {len(results)} total")
    print()

    for result in results:
        icon = _get_status_icon_console(result.status)
        print(f"[{result.status.value.upper():9}] {icon} {result.name}")
        print(f"            {result.details or result.message}")
        print()

    if critical_count > 0:
        print(f"WARNING: {critical_count} critical issue(s) found - DO NOT TRADE")
    else:
        print("OK: All checks passed - System ready")
    print()


def _get_status_color(status: HealthStatus) -> str:
    """Get rich color for status.

    Args:
        status: HealthStatus enum value

    Returns:
        Rich color string
    """
    colors = {
        HealthStatus.HEALTHY: "green",
        HealthStatus.WARNING: "yellow",
        HealthStatus.CRITICAL: "red",
        HealthStatus.SKIPPED: "dim",
    }
    return colors.get(status, "white")


def _get_status_icon(status: HealthStatus) -> str:
    """Get icon for status (for rich console output).

    Args:
        status: HealthStatus enum value

    Returns:
        Status icon character
    """
    icons = {
        HealthStatus.HEALTHY: "[OK]",
        HealthStatus.WARNING: "[WARN]",
        HealthStatus.CRITICAL: "[FAIL]",
        HealthStatus.SKIPPED: "[SKIP]",
    }
    return icons.get(status, "?")


def _get_status_icon_console(status: HealthStatus) -> str:
    """Get ASCII icon for status (for plain console output on Windows).

    Args:
        status: HealthStatus enum value

    Returns:
        ASCII status icon
    """
    icons = {
        HealthStatus.HEALTHY: "[OK]",
        HealthStatus.WARNING: "[WARN]",
        HealthStatus.CRITICAL: "[FAIL]",
        HealthStatus.SKIPPED: "[SKIP]",
    }
    return icons.get(status, "?")


def main() -> int:
    """Entry point for health check script.

    Returns:
        Exit code matching run_health_check result
    """
    try:
        return asyncio.run(run_health_check())
    except KeyboardInterrupt:
        print("\nHealth check interrupted by user.")
        return 1
    except Exception as e:
        logger.critical("health_check_unexpected_error", error=str(e), error_type=type(e).__name__)
        print(f"\nFATAL: Health check failed unexpectedly: {e}")
        return 1


if __name__ == "__main__":
    # Setup UTF-8 encoding on Windows BEFORE any other imports/output
    _setup_windows_utf8()
    sys.exit(main())
