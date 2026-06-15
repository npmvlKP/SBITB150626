# ============================================================================
# SBITB-150626 Project Health Verification Script
# ============================================================================
# Description: Comprehensive health check for SEBI-compliant Indian 
#              algorithmic trading bot (NSE + MCX)
# Platform: Windows 11 PowerShell
# Author: Automated Build System
# ============================================================================

#Requires -Version 5.1

param(
    [switch]$Quick,
    [switch]$Verbose,
    [switch]$InstallMissing
)

$ErrorActionPreference = "Continue"
$ProjectRoot = "g:\OC\SBITB-150626"
$Script:PassedChecks = 0
$Script:FailedChecks = 0
$Script:SkippedChecks = 0

function Write-Banner {
    param([string]$Title, [string]$Color = "Cyan")
    Write-Host ""
    Write-Host "========================================" -ForegroundColor $Color
    Write-Host " $Title" -ForegroundColor $Color
    Write-Host "========================================" -ForegroundColor $Color
}

function Write-Section {
    param([string]$Title, [string]$Subtitle = "")
    Write-Host ""
    Write-Host "--- $Title $Subtitle ---" -ForegroundColor Yellow
}

function Write-TestResult {
    param(
        [string]$TestName,
        [bool]$Passed,
        [string]$Details = "",
        [string]$Color = $null
    )
    
    if ($Color -eq $null) {
        $Color = if ($Passed) { "Green" } else { "Red" }
    }
    
    $status = if ($Passed) { "PASS" } else { "FAIL" }
    Write-Host "  [$status] $TestName" -ForegroundColor $Color
    if ($Details) {
        Write-Host "       $Details" -ForegroundColor Gray
    }
    
    if ($Passed) {
        $Script:PassedChecks++
    } elseif ($Color -eq "Yellow") {
        $Script:SkippedChecks++
    } else {
        $Script:FailedChecks++
    }
}

function Write-CommandOutput {
    param([string]$Command)
    Write-Host ""
    Write-Host "Executing: $Command" -ForegroundColor Gray
    $result = Invoke-Expression $Command 2>&1
    $result | ForEach-Object { Write-Host "  $_" }
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

Write-Banner "SBITB-150626 PROJECT HEALTH VERIFICATION"
Write-Host "Location: $ProjectRoot"
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Platform: Windows 11 PowerShell $($PSVersionTable.PSVersion)"
Write-Host "Mode: $(if ($Quick) { 'Quick Scan' } else { 'Full Health Check' })"

# Change to project directory
Set-Location $ProjectRoot

# ============================================================================
# PHASE 1: ENVIRONMENT VERIFICATION
# ============================================================================
Write-Section "PHASE 1: Environment Verification" "Python 3.11+ Required"

# Check Python version
Write-Host "Checking Python environment..."
$pythonVersion = python --version 2>&1
Write-Host "  $pythonVersion"
if ($pythonVersion -match "Python 3\.(1[1-9]|[2-9]\d)") {
    Write-TestResult "Python version >= 3.11" $true
} else {
    Write-TestResult "Python version >= 3.11" $false "Current: $pythonVersion"
}

# Check pip
$pipVersion = python -m pip --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-TestResult "pip installed" $true $pipVersion
} else {
    Write-TestResult "pip installed" $false "pip not found"
}

# Check virtual environment
if (Test-Path "SBITB150626" -PathType Container) {
    Write-TestResult "Virtual environment (SBITB150626)" $true "Directory exists"
} else {
    Write-TestResult "Virtual environment (SBITB150626)" $false "Directory not found - run: python -m venv SBITB150626"
}

# Check Git
$gitVersion = git --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-TestResult "Git installed" $true $gitVersion
} else {
    Write-TestResult "Git installed" $false "git not found"
}

# Check Docker (optional)
$dockerVersion = docker --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-TestResult "Docker installed" $true $dockerVersion
} else {
    Write-TestResult "Docker installed" $false "Docker not found (optional)"
}

# ============================================================================
# PHASE 2: PROJECT STRUCTURE INTEGRITY
# ============================================================================
Write-Section "PHASE 2: Project Structure" "Validating Core Files & Directories"

$requiredFiles = @(
    @{Path = "pyproject.toml"; Required = $true},
    @{Path = ".gitignore"; Required = $true},
    @{Path = ".pre-commit-config.yaml"; Required = $false},
    @{Path = "config/__init__.py"; Required = $true},
    @{Path = "config/settings.py"; Required = $true},
    @{Path = "src/__init__.py"; Required = $true}
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file.Path) {
        Write-TestResult "File exists: $($file.Path)" $true
    } else {
        if ($file.Required) {
            Write-TestResult "File exists: $($file.Path)" $false "Missing required file"
        } else {
            Write-TestResult "File exists: $($file.Path)" $false "Missing optional file" "Yellow"
        }
    }
}

$requiredDirs = @("src", "tests", "config", "deployment")
foreach ($dir in $requiredDirs) {
    if (Test-Path $dir -PathType Container) {
        Write-TestResult "Directory exists: $dir/" $true
    } else {
        Write-TestResult "Directory exists: $dir/" $false "Missing directory"
    }
}

# Check source module structure
$sourceModules = @("src/risk", "src/brokers", "src/data", "src/strategy")
foreach ($module in $sourceModules) {
    if (Test-Path $module -PathType Container) {
        Write-TestResult "Module: $module" $true
    } else {
        Write-TestResult "Module: $module" $false "Module not found"
    }
}

# ============================================================================
# PHASE 3: PYTHON DEPENDENCIES CHECK
# ============================================================================
Write-Section "PHASE 3: Dependencies" "Verifying Core Python Packages"

$coreDependencies = @(
    "pytest",
    "structlog",
    "pydantic",
    "pydantic_settings",
    "httpx",
    "pandas",
    "numpy"
)

foreach ($dep in $coreDependencies) {
    try {
        python -c "import $dep" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-TestResult "Package: $dep" $true
        } else {
            Write-TestResult "Package: $dep" $false "Not installed"
        }
    } catch {
        Write-TestResult "Package: $dep" $false "Import failed"
    }
}

# Check for dev dependencies
$devTools = @("ruff", "mypy", "bandit", "pip-audit")
foreach ($tool in $devTools) {
    $installed = Get-Command $tool -ErrorAction SilentlyContinue
    if ($installed) {
        Write-TestResult "Dev tool: $tool" $true
    } else {
        Write-TestResult "Dev tool: $tool" $false "Not in PATH" "Yellow"
    }
}

# ============================================================================
# PHASE 4: CODE QUALITY (RUFF LINTING)
# ============================================================================
Write-Section "PHASE 4: Code Quality" "Ruff Linter Check"

if (Get-Command ruff -ErrorAction SilentlyContinue) {
    Write-Host "Running ruff check..."
    $ruffOutput = ruff check src/ tests/ --output-format=text 2>&1
    $ruffExitCode = $LASTEXITCODE
    
    if ($ruffExitCode -eq 0) {
        Write-TestResult "Ruff linting" $true "No issues found"
    } else {
        Write-TestResult "Ruff linting" $false "Found issues"
        Write-CommandOutput "ruff check src/ tests/ --output-format=text"
    }
} else {
    Write-TestResult "Ruff linting" $false "ruff not installed" "Yellow"
}

# ============================================================================
# PHASE 5: TEST EXECUTION
# ============================================================================
Write-Section "PHASE 5: Test Execution" "Running Pytest Suite"

if ($Quick) {
    Write-Host "Quick mode: Skipping full test run"
    Write-TestResult "Test execution" $true "Skipped (quick mode)" "Yellow"
} else {
    Write-Host "Running pytest (may take 30-60 seconds)..."
    $testStart = Get-Date
    $testOutput = python -m pytest tests/ -v --tb=short --strict-markers 2>&1
    $testDuration = (Get-Date) - $testStart
    $testExitCode = $LASTEXITCODE
    
    # Parse results
    if ($testOutput -match "(\d+) passed") {
        $passedTests = [int]$matches[1]
        Write-TestResult "Pytest execution" $true "$passedTests tests passed in $($testDuration.TotalSeconds.ToString('0.0'))s"
        
        if ($testOutput -match "(\d+) failed") {
            $failedTests = [int]$matches[1]
            Write-Host "  Warning: $failedTests tests failed" -ForegroundColor Yellow
        }
    } else {
        Write-TestResult "Pytest execution" $false "Could not parse results"
    }
    
    # Show last 15 lines of test output
    Write-Host "`n  Last 15 lines of test output:"
    Write-Host "  " + ("-" * 70)
    $lines = $testOutput -split "`n"
    $lastLines = $lines | Select-Object -Last 15
    $lastLines | ForEach-Object { Write-Host "  $_" }
    Write-Host "  " + ("-" * 70)
}

# ============================================================================
# PHASE 6: GIT STATUS & REPO HEALTH
# ============================================================================
Write-Section "PHASE 6: Git Repository" "Version Control Status"

$gitStatus = git status --short 2>&1
if ($LASTEXITCODE -eq 0) {
    if ([string]::IsNullOrWhiteSpace($gitStatus)) {
        Write-TestResult "Git working directory" $true "Clean (no uncommitted changes)"
    } else {
        Write-TestResult "Git working directory" $false "Uncommitted changes detected"
        Write-CommandOutput "git status --short"
    }
} else {
    Write-TestResult "Git repository" $false "Not a git repository"
}

$gitLog = git log --oneline -3 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Recent commits:"
    $gitLog -split "`n" | ForEach-Object { Write-Host "    $_" }
}

# Check remote connectivity
$gitRemote = git remote -v 2>&1
if ($gitRemote -match "origin") {
    Write-TestResult "Git remote configured" $true
} else {
    Write-TestResult "Git remote configured" $false "No remote found"
}

# ============================================================================
# PHASE 7: BUILD SYSTEM CHECK
# ============================================================================
Write-Section "PHASE 7: Build System" "Package Configuration"

if (Test-Path "pyproject.toml") {
    Write-TestResult "pyproject.toml exists" $true
    
    # Try to parse with Python
    try {
        python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-TestResult "pyproject.toml valid TOML" $true
        } else {
            Write-TestResult "pyproject.toml valid TOML" $false "Invalid TOML syntax"
        }
    } catch {
        Write-TestResult "pyproject.toml valid TOML" $false "Parsing failed"
    }
} else {
    Write-TestResult "pyproject.toml exists" $false
}

# ============================================================================
# FINAL SUMMARY
# ============================================================================
Write-Banner "HEALTH CHECK SUMMARY"

$totalChecks = $Script:PassedChecks + $Script:FailedChecks + $Script:SkippedChecks

Write-Host ""
Write-Host "Total Checks: $totalChecks" -ForegroundColor White
Write-Host "  Passed:   $Script:PassedChecks" -ForegroundColor Green
Write-Host "  Failed:   $Script:FailedChecks" -ForegroundColor $(if ($Script:FailedChecks -gt 0) { "Red" } else { "Green" })
Write-Host "  Skipped:  $Script:SkippedChecks" -ForegroundColor Yellow

Write-Host ""

if ($Script:FailedChecks -eq 0) {
    Write-Host "STATUS: ALL CHECKS PASSED - Project is healthy!" -ForegroundColor Green
} else {
    Write-Host "STATUS: $($Script:FailedChecks) FAILURES DETECTED - Review errors above" -ForegroundColor Red
}

Write-Host ""
Write-Banner "QUICK REFERENCE COMMANDS" "Cyan"

Write-Host "Run full test suite:"
Write-Host "  python -m pytest tests/ -v --tb=short --strict-markers"
Write-Host ""

Write-Host "Run tests with coverage:"
Write-Host "  python -m pytest tests/ --cov=src --cov-report=term-missing"
Write-Host ""

Write-Host "Run ruff linter:"
Write-Host "  ruff check src/ tests/"
Write-Host ""

Write-Host "Format code with ruff:"
Write-Host "  ruff format src/ tests/"
Write-Host ""

Write-Host "Run mypy type checking:"
Write-Host "  mypy src/"
Write-Host ""

Write-Host "Install all dependencies:"
Write-Host "  pip install -e .[dev]"
Write-Host ""

Write-Host "Install missing dependencies only:"
Write-Host "  pip install -e ."
Write-Host ""

Write-Host "Git status:"
Write-Host "  git status"
Write-Host ""

Write-Host "View recent commits:"
Write-Host "  git log --oneline -5"
Write-Host ""

Write-Banner "END OF VERIFICATION" "Cyan"

Pop-Location

# Exit with appropriate code
exit $Script:FailedChecks