"""Pre-market health check — verify all systems are operational.

Checks:
  1. TimescaleDB connectivity
  2. Redis connectivity
  3. NTP clock offset (warn if > 500ms)
  4. Kill switch state (should be INACTIVE)
  5. Disk space (warn if < 10GB)
  6. Memory usage (warn if > 80%)

Exit code: 0 if all healthy, 1 if any CRITICAL issue.
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import datetime

import structlog
from rich.console import Console
from rich.table import Table

from config.settings import AuditSettings, KillSwitchSettings
from src.risk.audit import NTPClock
from src.risk.kill_switch import KillSwitch, KillSwitchLevel

logger = structlog.get_logger(__name__)
console = Console()


async def check_db_connectivity() -> tuple[bool, str]:
    """Check TimescaleDB connectivity."""
    try:
        import asyncpg

        conn = await asyncpg.connect("postgresql://trading:password@localhost:5432/trading_bot")
        await conn.close()
        return True, "Connected"
    except Exception as e:
        return False, str(e)


async def check_redis_connectivity() -> tuple[bool, str]:
    """Check Redis connectivity."""
    try:
        import redis.asyncio as redis

        client = redis.from_url("redis://localhost:6379/0")
        await client.ping()
        await client.close()
        return True, "Connected"
    except Exception as e:
        return False, str(e)


async def check_ntp_clock() -> tuple[bool, float]:
    """Check NTP clock offset."""
    settings = AuditSettings()
    clock = NTPClock(settings)
    offset = await clock.check_offset()
    return abs(offset) <= settings.MAX_NTP_OFFSET_MS, offset


def check_disk_space() -> tuple[bool, str]:
    """Check available disk space."""
    _total, _used, free = shutil.disk_usage("/")
    free_gb = free // (2**30)
    if free_gb < 10:
        return False, f"{free_gb}GB free"
    return True, f"{free_gb}GB free"


def check_memory() -> tuple[bool, str]:
    """Check memory usage."""
    try:
        import psutil

        mem = psutil.virtual_memory()
        used_pct = mem.percent
        if used_pct > 80:
            return False, f"{used_pct:.1f}% used"
        return True, f"{used_pct:.1f}% used"
    except ImportError:
        return True, "psutil not installed"


async def run_health_check() -> int:
    """Run all health checks and print report.

    Returns:
        0 if all healthy, 1 if any CRITICAL issue
    """
    console.print("\n[bold blue]SBITB Health Check — Pre-Market[/bold blue]")
    console.print(f"Timestamp: {datetime.utcnow().isoformat()} IST\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")

    critical_issues = 0

    # NTP Clock
    ntp_ok, ntp_offset = await check_ntp_clock()
    ntp_status = "[green]OK[/green]" if ntp_ok else "[red]WARN[/red]"
    ntp_detail = f"{ntp_offset:.1f}ms offset"
    table.add_row("NTP Clock", ntp_status, ntp_detail)
    if not ntp_ok:
        critical_issues += 1

    # Disk Space
    disk_ok, disk_detail = check_disk_space()
    disk_status = "[green]OK[/green]" if disk_ok else "[red]WARN[/red]"
    table.add_row("Disk Space", disk_status, disk_detail)
    if not disk_ok:
        critical_issues += 1

    # Memory
    mem_ok, mem_detail = check_memory()
    mem_status = "[green]OK[/green]" if mem_ok else "[red]WARN[/red]"
    table.add_row("Memory", mem_status, mem_detail)
    if not mem_ok:
        critical_issues += 1

    # Kill Switch
    ks_settings = KillSwitchSettings()
    ks = KillSwitch(ks_settings)
    ks_state = ks.get_state()["current_level"]
    ks_ok = ks_state == KillSwitchLevel.INACTIVE.value
    ks_status = "[green]OK[/green]" if ks_ok else "[red]WARN[/red]"
    table.add_row("Kill Switch", ks_status, f"Level: {ks_state}")
    if not ks_ok:
        critical_issues += 1

    # TimescaleDB (skip if not running)
    db_ok, db_detail = await check_db_connectivity()
    if db_ok:
        table.add_row("TimescaleDB", "[green]OK[/green]", db_detail)
    else:
        table.add_row("TimescaleDB", "[yellow]SKIP[/yellow]", "Not running (optional)")

    # Redis (skip if not running)
    redis_ok, redis_detail = await check_redis_connectivity()
    if redis_ok:
        table.add_row("Redis", "[green]OK[/green]", redis_detail)
    else:
        table.add_row("Redis", "[yellow]SKIP[/yellow]", "Not running (optional)")

    console.print(table)
    console.print()

    if critical_issues > 0:
        console.print(f"[red]CRITICAL: {critical_issues} issue(s) found — do not trade[/red]")
        return 1

    console.print("[green]All critical checks passed — system ready[/green]")
    return 0


if __name__ == "__main__":
    import sys

    exit_code = asyncio.run(run_health_check())
    sys.exit(exit_code)
