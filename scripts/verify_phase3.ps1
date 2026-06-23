<#
.SYNOPSIS
    Phase 3 Dependency Verification — PowerShell-safe wrapper

.DESCRIPTION
    PowerShell double-quotes strip the backslash before .venv in paths
    like .venv\Scripts\python.exe, causing CommandNotFoundException.

    This script ACTIVATES the venv first (avoiding path issues entirely)
    and then runs all Phase 3 verification checks.

    Alternatively, from an already-activated prompt:
        python scripts\verify_phase3_deps.py
        python -m pytest tests\ -x -q --tb=short
        python -m pip_audit
        python -m pip --version

.EXAMPLE
    .\scripts\verify_phase3.ps1
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# Activate venv — use Join-Path to avoid backslash-before-dot escaping
$ActivateScript = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $ActivateScript)) {
    Write-Error "Virtual environment not found at $ActivateScript. Run: python -m venv .venv"
    exit 1
}

Write-Host "Activating venv..." -ForegroundColor Cyan
& $ActivateScript

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  PHASE 3 DEPENDENCY VERIFICATION" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# --- Step 1: Run Python verification script ---
Write-Host "--- Step 1: Python Dependency Checks ---" -ForegroundColor Cyan
python scripts\verify_phase3_deps.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Phase 3 dependency verification FAILED (exit code $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host ""

# --- Step 2: pip-audit ---
Write-Host "--- Step 2: Security Audit ---" -ForegroundColor Cyan
python -m pip_audit
if ($LASTEXITCODE -ne 0) {
    Write-Warning "pip-audit returned exit code $LASTEXITCODE (may have findings)"
}

Write-Host ""

# --- Step 3: Run unit tests ---
Write-Host "--- Step 3: Unit Tests ---" -ForegroundColor Cyan
python -m pytest tests\ -x -q --tb=short 2>&1 | Out-String | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Some tests failed (exit code $LASTEXITCODE)"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  PHASE 3 VERIFICATION COMPLETE" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
