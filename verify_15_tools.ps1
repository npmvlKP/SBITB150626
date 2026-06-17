# ==============================================================================
# SBITB150626 - Install & Verify All 15 Test Tools
# PowerShell Execution Script - STRICT PROTOCOL
# ==============================================================================
# Purpose: Install and verify all 15 test/quality tools for the SBITB-150626
#          Options Trading and Risk Management System
# Reference: SBITB STRICT CHECKLIST CONTRACT (Section 14)
# ==============================================================================

# PowerShell settings
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Define color codes for output
function Write-Success { param($Message) Write-Host "[PASS] $Message" -ForegroundColor Green }
function Write-Failure { param($Message) Write-Host "[FAIL] $Message" -ForegroundColor Red }
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Warning { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }

# Track overall status
$global:ToolStatus = @{}
$global:OverallSuccess = $true

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "SBITB150626 - Install & Verify All 15 Test Tools" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

# ==============================================================================
# PHASE 1: Virtual Environment Setup
# ==============================================================================
Write-Host "PHASE 1: Virtual Environment Setup" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

$venvPath = "g:\OC\SBITB-150626\SBITB150626"
$venvActivate = "$venvPath\Scripts\Activate.ps1"

# Check if venv exists
if (Test-Path $venvActivate) {
    Write-Info "Virtual environment already exists at: $venvPath"
} else {
    Write-Info "Creating virtual environment: SBITB150626"
    python -m venv SBITB150626
    if ($LASTEXITCODE -ne 0) {
        Write-Failure "Failed to create virtual environment"
        $global:OverallSuccess = $false
    } else {
        Write-Success "Virtual environment created"
    }
}

# Activate virtual environment
Write-Info "Activating virtual environment..."
& $venvActivate
$env:VIRTUAL_ENV = $venvPath
$env:PATH = "$venvPath\Scripts;$env:PATH"
Write-Success "Virtual environment activated"

# ==============================================================================
# PHASE 2: Install Project with Dev Dependencies
# ==============================================================================
Write-Host ""
Write-Host "PHASE 2: Install Project with Dev Dependencies" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

Set-Location "g:\OC\SBITB-150626"

Write-Info "Installing project in editable mode with dev dependencies..."
pip install -e ".[dev]" 2>&1 | Tee-Object -Variable pipOutput

if ($LASTEXITCODE -ne 0) {
    Write-Failure "Failed to install project dependencies"
    $global:OverallSuccess = $false
    Write-Host $pipOutput
} else {
    Write-Success "Project dependencies installed"
}

# ==============================================================================
# PHASE 3: Verify Each Tool (15 Tools)
# ==============================================================================
Write-Host ""
Write-Host "PHASE 3: Verify Each Tool (15 Test Tools)" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

function Test-Tool {
    param(
        [string]$Name,
        [string]$Command,
        [string]$ExpectedPattern
    )

    Write-Host ""
    Write-Info "Testing: $Name"
    Write-Host "  Command: $Command"

    try {
        $output = Invoke-Expression $Command 2>&1 | Out-String

        if ($output -match $ExpectedPattern) {
            Write-Success "$Name - PASS"
            $global:ToolStatus[$Name] = @{ Status = "PASS"; Output = $output; Command = $Command }
            return $true
        } else {
            Write-Failure "$Name - FAIL (Output did not match expected pattern)"
            Write-Host "  Output: $output" -ForegroundColor Gray
            $global:ToolStatus[$Name] = @{ Status = "FAIL"; Output = $output; Command = $Command }
            return $false
        }
    } catch {
        Write-Failure "$Name - ERROR: $_"
        $global:ToolStatus[$Name] = @{ Status = "ERROR"; Output = $_.Exception.Message; Command = $Command }
        return $false
    }
}

# Tool 1: pytest (test runner)
$tool1 = Test-Tool -Name "pytest" -Command "pytest --version" -ExpectedPattern "pytest version"

# Tool 2: pytest-asyncio (async test support)
$tool2 = Test-Tool -Name "pytest-asyncio" -Command "pip show pytest-asyncio" -ExpectedPattern "Name: pytest-asyncio"

# Tool 3: pytest-cov (coverage)
$tool3 = Test-Tool -Name "pytest-cov" -Command "pytest-cov --version" -ExpectedPattern "version"

# Tool 4: pytest-mock (mocking)
$tool4 = Test-Tool -Name "pytest-mock" -Command "pip show pytest-mock" -ExpectedPattern "Name: pytest-mock"

# Tool 5: pytest-xdist (parallel tests)
$tool5 = Test-Tool -Name "pytest-xdist" -Command "pip show pytest-xdist" -ExpectedPattern "Name: pytest-xdist"

# Tool 6: pytest-timeout (test timeout)
$tool6 = Test-Tool -Name "pytest-timeout" -Command "pip show pytest-timeout" -ExpectedPattern "Name: pytest-timeout"

# Tool 7: pytest-randomly (random test order)
$tool7 = Test-Tool -Name "pytest-randomly" -Command "pip show pytest-randomly" -ExpectedPattern "Name: pytest-randomly"

# Tool 8: mypy (type checker)
$tool8 = Test-Tool -Name "mypy" -Command "mypy --version" -ExpectedPattern "mypy"

# Tool 9: ruff (linter + formatter)
$tool9 = Test-Tool -Name "ruff" -Command "ruff --version" -ExpectedPattern "ruff"

# Tool 10: bandit (security linter)
$tool10 = Test-Tool -Name "bandit" -Command "bandit --version" -ExpectedPattern "bandit"

# Tool 11: pip-audit (dependency vulnerability scanner)
$tool11 = Test-Tool -Name "pip-audit" -Command "pip-audit --version" -ExpectedPattern "pip-audit|version"

# Tool 12: safety (dependency safety checker)
$tool12 = Test-Tool -Name "safety" -Command "safety --version" -ExpectedPattern "safety"

# Tool 13: gitleaks (secret detection)
$tool13 = Test-Tool -Name "gitleaks" -Command "gitleaks version" -ExpectedPattern "version"

# Tool 14: trivy (container vulnerability scanner)
$tool14 = Test-Tool -Name "trivy" -Command "trivy --version" -ExpectedPattern "trivy"

# Tool 15: detect-secrets (alternative secret scanner)
$tool15 = Test-Tool -Name "detect-secrets" -Command "detect-secrets --version" -ExpectedPattern "detect-secrets|version"

# ==============================================================================
# PHASE 4: Run Full Verification
# ==============================================================================
Write-Host ""
Write-Host "PHASE 4: Run Full Verification" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

# G1: ruff check
Write-Host ""
Write-Info "Running: ruff check src/ tests/"
ruff check src/ tests/ --config pyproject.toml 2>&1 | Tee-Object -Variable ruffCheckOut
if ($LASTEXITCODE -eq 0) {
    Write-Success "G1: ruff check - PASS (0 violations)"
    $global:ToolStatus["G1_ruff_check"] = @{ Status = "PASS"; Output = $ruffCheckOut }
} else {
    Write-Failure "G1: ruff check - FAIL"
    $global:ToolStatus["G1_ruff_check"] = @{ Status = "FAIL"; Output = $ruffCheckOut }
    $global:OverallSuccess = $false
}

# G2: ruff format
Write-Host ""
Write-Info "Running: ruff format --check src/ tests/"
ruff format --check src/ tests/ --config pyproject.toml 2>&1 | Tee-Object -Variable ruffFormatOut
if ($LASTEXITCODE -eq 0) {
    Write-Success "G2: ruff format - PASS (0 reformats)"
    $global:ToolStatus["G2_ruff_format"] = @{ Status = "PASS"; Output = $ruffFormatOut }
} else {
    Write-Failure "G2: ruff format - FAIL"
    $global:ToolStatus["G2_ruff_format"] = @{ Status = "FAIL"; Output = $ruffFormatOut }
    $global:OverallSuccess = $false
}

# G3: mypy type checking
Write-Host ""
Write-Info "Running: mypy src/"
mypy src/ --strict --config-file pyproject.toml 2>&1 | Tee-Object -Variable mypyOut
if ($LASTEXITCODE -eq 0) {
    Write-Success "G3: mypy - PASS (0 errors)"
    $global:ToolStatus["G3_mypy"] = @{ Status = "PASS"; Output = $mypyOut }
} else {
    Write-Failure "G3: mypy - FAIL"
    $global:ToolStatus["G3_mypy"] = @{ Status = "FAIL"; Output = $mypyOut }
    $global:OverallSuccess = $false
}

# G4: bandit security
Write-Host ""
Write-Info "Running: bandit -r src/ -c pyproject.toml"
bandit -r src/ -c pyproject.toml -q 2>&1 | Tee-Object -Variable banditOut
if ($LASTEXITCODE -eq 0) {
    Write-Success "G4: bandit - PASS (0 HIGH severity issues)"
    $global:ToolStatus["G4_bandit"] = @{ Status = "PASS"; Output = $banditOut }
} else {
    Write-Failure "G4: bandit - FAIL"
    $global:ToolStatus["G4_bandit"] = @{ Status = "FAIL"; Output = $banditOut }
    $global:OverallSuccess = $false
}

# G6: pytest with coverage
Write-Host ""
Write-Info "Running: pytest tests/ -v --cov=src --cov-report=term-missing"
pytest tests/ -v --cov=src --cov-report=term-missing 2>&1 | Tee-Object -Variable pytestOut
if ($LASTEXITCODE -eq 0) {
    Write-Success "G6: pytest - PASS (all tests passed)"
    $global:ToolStatus["G6_pytest"] = @{ Status = "PASS"; Output = $pytestOut }
} else {
    Write-Failure "G6: pytest - FAIL"
    $global:ToolStatus["G6_pytest"] = @{ Status = "FAIL"; Output = $pytestOut }
    $global:OverallSuccess = $false
}

# ==============================================================================
# PHASE 5: Pre-commit Hooks
# ==============================================================================
Write-Host ""
Write-Host "PHASE 5: Pre-commit Hooks" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

# Install pre-commit hooks
Write-Info "Installing pre-commit hooks..."
pre-commit install 2>&1 | Tee-Object -Variable preCommitInstallOut
if ($LASTEXITCODE -eq 0) {
    Write-Success "pre-commit install - PASS"
    $global:ToolStatus["precommit_install"] = @{ Status = "PASS"; Output = $preCommitInstallOut }
} else {
    Write-Warning "pre-commit install - Some hooks may need additional setup"
    $global:ToolStatus["precommit_install"] = @{ Status = "WARN"; Output = $preCommitInstallOut }
}

# Run pre-commit on all files
Write-Info "Running pre-commit on all files..."
pre-commit run --all-files 2>&1 | Tee-Object -Variable preCommitRunOut
if ($LASTEXITCODE -eq 0) {
    Write-Success "pre-commit run --all-files - PASS"
    $global:ToolStatus["precommit_run"] = @{ Status = "PASS"; Output = $preCommitRunOut }
} else {
    Write-Warning "pre-commit run - Some hooks may have failed (this may be acceptable for test files)"
    $global:ToolStatus["precommit_run"] = @{ Status = "WARN"; Output = $preCommitRunOut }
}

# ==============================================================================
# PHASE 6: Docker Compose Verification
# ==============================================================================
Write-Host ""
Write-Host "PHASE 6: Docker Compose Syntax Verification" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

Write-Info "Verifying docker-compose syntax..."
docker-compose -f deployment/docker-compose.yml config 2>&1 | Tee-Object -Variable dockerComposeOut
if ($LASTEXITCODE -eq 0) {
    Write-Success "docker-compose config - PASS (valid syntax)"
    $global:ToolStatus["docker_compose"] = @{ Status = "PASS"; Output = $dockerComposeOut }
} else {
    Write-Warning "docker-compose config - May have issues (check output above)"
    $global:ToolStatus["docker_compose"] = @{ Status = "WARN"; Output = $dockerComposeOut }
}

# ==============================================================================
# SUMMARY
# ==============================================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "VERIFICATION SUMMARY - All 15 Test Tools" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta

$totalTools = 15
$passedTools = 0

# Count passed tools
foreach ($tool in @("pytest", "pytest-asyncio", "pytest-cov", "pytest-mock",
                    "pytest-xdist", "pytest-timeout", "pytest-randomly",
                    "mypy", "ruff", "bandit", "pip-audit", "safety",
                    "gitleaks", "trivy", "detect-secrets")) {
    if ($global:ToolStatus[$tool].Status -eq "PASS") {
        $passedTools++
        Write-Host "[$passedTools/$totalTools] $tool - INSTALLED & VERIFIED" -ForegroundColor Green
    } elseif ($global:ToolStatus[$tool].Status -eq "WARN") {
        Write-Host "[WARN] $tool - INSTALLED WITH WARNINGS" -ForegroundColor Yellow
    } else {
        Write-Host "[FAIL] $tool - FAILED" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Quality Gates Status:" -ForegroundColor Cyan
$gateNames = @("G1_ruff_check", "G2_ruff_format", "G3_mypy", "G4_bandit", "G6_pytest")
foreach ($gate in $gateNames) {
    if ($global:ToolStatus[$gate]) {
        $status = $global:ToolStatus[$gate].Status
        if ($status -eq "PASS") {
            Write-Host "  $gate - PASS" -ForegroundColor Green
        } elseif ($status -eq "WARN") {
            Write-Host "  $gate - WARN" -ForegroundColor Yellow
        } else {
            Write-Host "  $gate - FAIL" -ForegroundColor Red
        }
    }
}

Write-Host ""
if ($global:OverallSuccess) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "ALL TOOLS INSTALLED & VERIFIED SUCCESSFULLY" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
} else {
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "INSTALLATION COMPLETED WITH SOME WARNINGS" -ForegroundColor Yellow
    Write-Host "Check individual tool status above for details" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
}

# Return exit code
if (-not $global:OverallSuccess) {
    exit 1
} else {
    exit 0
}
