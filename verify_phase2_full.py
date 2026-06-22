#!/usr/bin/env python3
"""
Phase 2 Comprehensive Verification Script -- SBITB-150626

Runs all Tier 0, Tier 1, and Tier 2 verification gates and produces
a detailed report. Exit code 0 = all gates pass, 1 = one or more failures.

Usage:
    python verify_phase2_full.py                  # Full verification
    python verify_phase2_full.py --tier0          # Only Tier 0 (PR gate)
    python verify_phase2_full.py --skip-docker    # Skip Docker-dependent tests
    python verify_phase2_full.py --verbose        # Verbose output
    python verify_phase2_full.py --save-report    # Save markdown + JSON reports
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


# -- Data Structures ----------------------------------------------------------


@dataclass
class GateResult:
    """Single gate verification result."""

    name: str
    tier: int
    command: str
    passed: bool = False
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_sec: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class VerificationReport:
    """Full verification report."""

    timestamp: str = ""
    project_root: str = ""
    python_version: str = ""
    platform: str = ""
    gates: list[GateResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def passed_gates(self) -> list[GateResult]:
        return [g for g in self.gates if g.passed and not g.skipped]

    def failed_gates(self) -> list[GateResult]:
        return [g for g in self.gates if not g.passed and not g.skipped]

    def skipped_gates(self) -> list[GateResult]:
        return [g for g in self.gates if g.skipped]

    def all_passed(self) -> bool:
        return len(self.failed_gates()) == 0


# -- Helpers ------------------------------------------------------------------

ROOT = Path(__file__).parent.resolve()
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

STATUS_PASS = f"{GREEN}[PASS]{RESET}"
STATUS_FAIL = f"{RED}[FAIL]{RESET}"
STATUS_SKIP = f"{YELLOW}[SKIP]{RESET}"


def print_header(text: str) -> None:
    width = 72
    print(f"\n{BOLD}{BLUE}{'=' * width}{RESET}")
    print(f"{BOLD}{BLUE}  {text}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * width}{RESET}\n")


def run_command(
    cmd: str,
    timeout: int = 300,
    cwd: str | None = None,
) -> tuple[int, str, str, float]:
    """Run a shell command and return (exit_code, stdout, stderr, duration)."""
    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or str(ROOT),
        )
        duration = time.perf_counter() - start
        return result.returncode, result.stdout, result.stderr, duration
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - start
        return -1, "", f"Command timed out after {timeout}s", duration
    except Exception as e:
        duration = time.perf_counter() - start
        return -2, "", str(e), duration


def command_exists(cmd: str) -> bool:
    """Check if a command is available on PATH."""
    return shutil.which(cmd) is not None


def print_result(result: GateResult, verbose: bool = False) -> None:
    if result.skipped:
        print(f"  {STATUS_SKIP} ({result.skip_reason})")
    elif result.passed:
        print(f"  {STATUS_PASS} {result.name} ({result.duration_sec:.1f}s)")
    else:
        print(f"  {STATUS_FAIL} {result.name} ({result.duration_sec:.1f}s)")
        if verbose and result.stderr:
            print(f"    stderr: {RED}{result.stderr[:200]}{RESET}")


# -- Gate Definitions ---------------------------------------------------------


def gate_mypy(report: VerificationReport) -> GateResult:
    """mypy src/ --strict = 0 errors."""
    gate = GateResult(name="mypy --strict", tier=0, command="mypy src/ --strict")
    ec, out, err, dur = run_command(f'"{sys.executable}" -m mypy src/ --strict')
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:2000], err[:2000]
    gate.passed = ec == 0
    if gate.passed:
        gate.details["msg"] = "0 errors"
    return gate


def gate_ruff_check(report: VerificationReport) -> GateResult:
    """ruff check src/ tests/ = 0 errors."""
    gate = GateResult(name="ruff check", tier=0, command="ruff check src/ tests/")
    ec, out, err, dur = run_command("ruff check src/ tests/")
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:2000], err[:2000]
    gate.passed = ec == 0
    return gate


def gate_ruff_format(report: VerificationReport) -> GateResult:
    """ruff format --check = 0 files need formatting."""
    gate = GateResult(name="ruff format --check", tier=0, command="ruff format --check src/ tests/")
    ec, out, err, dur = run_command("ruff format --check src/ tests/")
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:2000], err[:2000]
    gate.passed = ec == 0
    for line in out.splitlines():
        if "files already formatted" in line:
            gate.details["files_formatted"] = line.strip()
    return gate


def gate_bandit(report: VerificationReport) -> GateResult:
    """bandit -c pyproject.toml -r src/ = 0 HIGH."""
    cmd = f'"{sys.executable}" -m bandit -lll -c pyproject.toml -r src/'
    gate = GateResult(name="bandit (no HIGH)", tier=0, command=cmd)
    ec, out, err, dur = run_command(cmd)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:3000], err[:2000]
    gate.passed = ec == 0
    for line in out.splitlines():
        if "High" in line and ":" in line:
            gate.details["severity_summary"] = line.strip()
    return gate


def gate_unit_coverage(report: VerificationReport) -> GateResult:
    """pytest tests/unit/ with coverage >= 80%."""
    cmd = f'"{sys.executable}" -m pytest tests/unit/ --cov=src --cov-branch --cov-fail-under=80 -q'
    gate = GateResult(name="unit tests + coverage >=80%", tier=0, command=cmd)
    ec, out, err, dur = run_command(cmd, timeout=300)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:3000], err[:3000]
    gate.passed = ec == 0
    for line in (out + err).splitlines():
        if "TOTAL" in line and "%" in line:
            gate.details["coverage_line"] = line.strip()
        if "passed" in line:
            gate.details["test_summary"] = line.strip()
    return gate


def gate_pip_audit(report: VerificationReport) -> GateResult:
    """pip-audit -r requirements.txt = 0 vulns."""
    cmd = f'"{sys.executable}" -m pip_audit -r requirements.txt --skip-editable'
    gate = GateResult(name="pip-audit (requirements.txt)", tier=0, command=cmd)
    ec, out, err, dur = run_command(cmd, timeout=120)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:3000], err[:2000]
    gate.passed = ec == 0
    for line in out.splitlines():
        if "vulnerabilities" in line.lower():
            gate.details["audit_summary"] = line.strip()
    return gate


def gate_gitleaks(report: VerificationReport) -> GateResult:
    """gitleaks detect = 0 secrets."""
    gate = GateResult(name="gitleaks (no secrets)", tier=0, command="gitleaks detect --source .")
    if not command_exists("gitleaks"):
        gate.skipped = True
        gate.skip_reason = "gitleaks not on PATH"
        return gate
    ec, out, err, dur = run_command("gitleaks detect --source . --no-git -v", timeout=60)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.passed = ec == 0
    return gate


def gate_property_tests(report: VerificationReport) -> GateResult:
    """pytest tests/property/ -v."""
    cmd = f'"{sys.executable}" -m pytest tests/property/ -v -q'
    gate = GateResult(name="property tests (Hypothesis)", tier=1, command=cmd)
    ec, out, err, dur = run_command(cmd, timeout=180)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:3000], err[:2000]
    gate.passed = ec == 0
    for line in out.splitlines():
        if "passed" in line:
            gate.details["test_summary"] = line.strip()
    return gate


def gate_benchmarks(report: VerificationReport) -> GateResult:
    """pytest tests/bench/ --benchmark-only."""
    cmd = f'"{sys.executable}" -m pytest tests/bench/ --benchmark-only -q'
    gate = GateResult(name="benchmarks (<10ms single)", tier=1, command=cmd)
    ec, out, err, dur = run_command(cmd, timeout=360)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout = out[:4000]
    gate.stderr = err[:2000]
    gate.passed = ec == 0
    return gate


def gate_integration(report: VerificationReport, skip_docker: bool = False) -> GateResult:
    """pytest tests/integration/."""
    cmd = f'"{sys.executable}" -m pytest tests/integration/ -v -q'
    gate = GateResult(name="integration tests", tier=1, command=cmd)
    if skip_docker:
        gate.skipped = True
        gate.skip_reason = "Docker skipped by user"
        return gate
    ec, out, err, dur = run_command(cmd, timeout=120)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:3000], err[:2000]
    gate.passed = ec == 0
    for line in out.splitlines():
        if "passed" in line:
            gate.details["test_summary"] = line.strip()
    return gate


def gate_kleppmann(report: VerificationReport) -> GateResult:
    """Kleppmann Ch.1-5 cross-reference validation."""
    gate = GateResult(name="Kleppmann Ch.1-5 validation", tier=1, command="python verify_phase2_kleppmann.py")
    ec, out, err, dur = run_command(f'"{sys.executable}" verify_phase2_kleppmann.py', timeout=60)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:3000], err[:2000]
    gate.passed = ec == 0
    return gate


def gate_pip_audit_detailed(report: VerificationReport) -> GateResult:
    """pip-audit with descriptions (Tier 2)."""
    cmd = f'"{sys.executable}" -m pip_audit -r requirements.txt --desc --skip-editable'
    gate = GateResult(name="pip-audit detailed", tier=2, command=cmd)
    ec, out, err, dur = run_command(cmd, timeout=180)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:5000], err[:2000]
    gate.passed = ec == 0
    return gate


def gate_sbom(report: VerificationReport) -> GateResult:
    """cyclonedx-bom SBOM generation (Tier 2)."""
    gate = GateResult(name="SBOM generation", tier=2, command="cyclonedx-bom -o sbom.json")
    if not command_exists("cyclonedx-bom"):
        gate.skipped = True
        gate.skip_reason = "cyclonedx-bom not installed"
        return gate
    ec, out, err, dur = run_command("cyclonedx-bom -o sbom.json", timeout=60)
    gate.exit_code, gate.duration_sec = ec, dur
    gate.passed = ec == 0
    return gate


def gate_trivy(report: VerificationReport) -> GateResult:
    """trivy fs . (Tier 2)."""
    gate = GateResult(name="trivy filesystem scan", tier=2, command="trivy fs .")
    if not command_exists("trivy"):
        gate.skipped = True
        gate.skip_reason = "trivy not on PATH"
        return gate
    ec, out, err, dur = run_command(
        "trivy fs . --severity CRITICAL --skip-dirs .venv,__pycache__,.git,node_modules", timeout=360
    )
    gate.exit_code, gate.duration_sec = ec, dur
    gate.stdout, gate.stderr = out[:3000], err[:2000]
    gate.passed = ec == 0
    return gate


# -- Report Generation --------------------------------------------------------


def generate_report(report: VerificationReport, verbose: bool = False) -> str:
    """Generate human-readable terminal report."""
    lines: list[str] = []

    lines.append(f"\n{BOLD}{'=' * 72}{RESET}")
    lines.append(f"{BOLD}  Phase 2 Verification Report -- SBITB-150626{RESET}")
    lines.append(f"{BOLD}{'=' * 72}{RESET}")
    lines.append(f"  Timestamp : {report.timestamp}")
    lines.append(f"  Root      : {report.project_root}")
    lines.append(f"  Python    : {report.python_version}")
    lines.append(f"  Platform  : {report.platform}")
    lines.append("")

    for tier_num, tier_name in [
        (0, "Tier 0 -- Every PR Gate (Mandatory)"),
        (1, "Tier 1 -- Property + Integration + Benchmarks"),
        (2, "Tier 2 -- Security (Pre-release)"),
    ]:
        tier_gates = [g for g in report.gates if g.tier == tier_num]
        if not tier_gates:
            continue
        lines.append(f"{BOLD}  {tier_name}{RESET}")
        lines.append(f"{'-' * 72}")
        for g in tier_gates:
            if g.skipped:
                status = STATUS_SKIP
            elif g.passed:
                status = STATUS_PASS
            else:
                status = STATUS_FAIL
            duration = f"{g.duration_sec:.1f}s" if g.duration_sec > 0 else "-"
            lines.append(f"  {status}  {g.name:<35} {duration:>8}")
            if verbose and g.stdout:
                lines.append(f"         stdout: {g.stdout[:200]}")
            if not g.passed and g.stderr:
                lines.append(f"         stderr: {RED}{g.stderr[:300]}{RESET}")
            if g.details:
                for k, v in g.details.items():
                    lines.append(f"         {k}: {v}")
            if g.skip_reason:
                lines.append(f"         reason: {g.skip_reason}")
        lines.append("")

    passed = len(report.passed_gates())
    failed = len(report.failed_gates())
    skipped = len(report.skipped_gates())
    total = len(report.gates)

    lines.append(f"{BOLD}{'=' * 72}{RESET}")
    lines.append(
        f"  SUMMARY: {GREEN}{passed} passed{RESET}, {RED}{failed} failed{RESET}, {YELLOW}{skipped} skipped{RESET} / {total} total"
    )
    if report.all_passed():
        lines.append(f"  {BOLD}{GREEN}PHASE 2 GATE: PASS{RESET}")
    else:
        lines.append(f"  {BOLD}{RED}PHASE 2 GATE: FAIL{RESET}")
    lines.append(f"{BOLD}{'=' * 72}{RESET}")

    return "\n".join(lines)


def generate_markdown_report(report: VerificationReport) -> str:
    """Generate markdown report for saving to file."""
    lines = [
        "# Phase 2 Verification Report -- SBITB-150626",
        "",
        f"**Timestamp:** {report.timestamp}  ",
        f"**Root:** {report.project_root}  ",
        f"**Python:** {report.python_version}  ",
        f"**Platform:** {report.platform}  ",
        "",
    ]

    for tier_num, tier_name in [
        (0, "Tier 0 -- Every PR Gate"),
        (1, "Tier 1 -- Extended"),
        (2, "Tier 2 -- Security"),
    ]:
        tier_gates = [g for g in report.gates if g.tier == tier_num]
        if not tier_gates:
            continue
        lines.append(f"## {tier_name}")
        lines.append("")
        lines.append("| Gate | Command | Status | Duration |")
        lines.append("|------|---------|--------|----------|")
        for g in tier_gates:
            status = "PASS" if g.passed else ("SKIP" if g.skipped else "FAIL")
            lines.append(f"| {g.name} | `{g.command[:50]}` | {status} | {g.duration_sec:.1f}s |")
        lines.append("")

    passed = len(report.passed_gates())
    failed = len(report.failed_gates())
    skipped = len(report.skipped_gates())

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Passed:** {passed}")
    lines.append(f"- **Failed:** {failed}")
    lines.append(f"- **Skipped:** {skipped}")
    lines.append("")
    if report.all_passed():
        lines.append("**PHASE 2 GATE: PASS**")
    else:
        lines.append("**PHASE 2 GATE: FAIL**")
    lines.append("")

    return "\n".join(lines)


# -- Main ---------------------------------------------------------------------


def run_gates(
    report: VerificationReport,
    gate_fns: list,
    verbose: bool = False,
) -> None:
    """Run a list of gate functions and append results to report."""
    for gate_fn in gate_fns:
        print(f"  Running: {gate_fn.__name__}...", end=" ", flush=True)
        result = gate_fn(report)
        report.gates.append(result)
        print_result(result, verbose)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 Verification Suite -- SBITB-150626")
    parser.add_argument("--tier0", action="store_true", help="Run only Tier 0 gates")
    parser.add_argument("--skip-docker", action="store_true", help="Skip Docker-dependent tests")
    parser.add_argument("--verbose", action="store_true", help="Show command output")
    parser.add_argument("--save-report", action="store_true", help="Save markdown report to file")
    args = parser.parse_args()

    report = VerificationReport(
        timestamp=datetime.now().isoformat(),
        project_root=str(ROOT),
        python_version=sys.version,
        platform=sys.platform,
    )

    print_header("Phase 2 Verification -- SBITB-150626")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Root:   {ROOT}")
    print(f"  Mode:   {'Tier 0 only' if args.tier0 else 'Full'}")
    print()

    # -- Tier 0 --
    print_header("Tier 0 -- Every PR Gate (Mandatory)")
    run_gates(
        report,
        [
            gate_mypy,
            gate_ruff_check,
            gate_ruff_format,
            gate_bandit,
            gate_unit_coverage,
            gate_pip_audit,
            gate_gitleaks,
        ],
        verbose=args.verbose,
    )

    if not args.tier0:
        # -- Tier 1 --
        print_header("Tier 1 -- Property + Integration + Benchmarks")
        run_gates(
            report,
            [
                gate_property_tests,
                gate_benchmarks,
                lambda r: gate_integration(r, skip_docker=args.skip_docker),
                gate_kleppmann,
            ],
            verbose=args.verbose,
        )

        # -- Tier 2 --
        print_header("Tier 2 -- Security (Pre-release)")
        run_gates(
            report,
            [
                gate_pip_audit_detailed,
                gate_sbom,
                gate_trivy,
            ],
            verbose=args.verbose,
        )

    # -- Report --
    report_text = generate_report(report, verbose=args.verbose)
    print(report_text)

    # Save markdown report
    if args.save_report:
        md_path = ROOT / "phase2_verification_report.md"
        md_path.write_text(generate_markdown_report(report), encoding="utf-8")
        print(f"\n  Markdown report saved to: {md_path}")

    # Save JSON report
    json_path = ROOT / "phase2_verification_report.json"
    json_data = {
        "timestamp": report.timestamp,
        "project_root": report.project_root,
        "python_version": report.python_version,
        "platform": report.platform,
        "gates": [
            {
                "name": g.name,
                "tier": g.tier,
                "command": g.command,
                "passed": g.passed,
                "skipped": g.skipped,
                "skip_reason": g.skip_reason,
                "exit_code": g.exit_code,
                "duration_sec": round(g.duration_sec, 2),
                "details": g.details,
                "stdout_last200": g.stdout[-200:] if g.stdout else "",
                "stderr_last200": g.stderr[-200:] if g.stderr else "",
            }
            for g in report.gates
        ],
        "summary": {
            "total": len(report.gates),
            "passed": len(report.passed_gates()),
            "failed": len(report.failed_gates()),
            "skipped": len(report.skipped_gates()),
            "all_passed": report.all_passed(),
        },
    }
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    print(f"  JSON report saved to: {json_path}")

    return 0 if report.all_passed() else 1


if __name__ == "__main__":
    sys.exit(main())
