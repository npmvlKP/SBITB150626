# SBITB-150626 Project Health Verification Protocol
## SEBI-Compliant Indian Algorithmic Trading Bot for NSE + MCX

---

### **WHAT: Verification Protocol Overview**

This protocol provides a comprehensive health check system for the SBITB-150626 algorithmic trading project. The verification script validates all critical aspects of the project including:

- **Environment**: Python 3.11+ runtime, Git version control, Docker (optional)
- **Structure**: Project directory integrity, required files and modules
- **Dependencies**: Core Python packages and development tools
- **Code Quality**: Ruff linter checks for code style and potential issues
- **Testing**: Full pytest suite execution with 62+ tests
- **Repository**: Git status, commit history, and remote connectivity
- **Build System**: pyproject.toml configuration validation

---

### **WHERE: File Locations**

#### **Primary Verification Script**
```
g:\OC\SBITB-150626\verify-project-health.ps1
```

#### **Project Root Directory**
```
g:\OC\SBITB-150626\
```

#### **Key Directories Checked**
- `src/` - Source code modules (risk, brokers, data, strategy)
- `tests/` - Comprehensive test suite
- `config/` - Configuration and settings
- `deployment/` - Docker and deployment artifacts

#### **Key Configuration Files**
- `pyproject.toml` - Project metadata and dependencies
- `.gitignore` - Git ignore rules
- `.pre-commit-config.yaml` - Pre-commit hooks

---

### **WHEN: Execution Timing**

#### **Recommended Execution Times**

1. **Initial Setup**: After cloning the repository or installing dependencies
2. **Pre-Commit**: Before committing changes to git
3. **Post-Merge**: After pulling or merging changes from remote
4. **Pre-Deployment**: Before deploying to staging or production
5. **Daily Maintenance**: As part of daily operational health checks
6. **Troubleshooting**: When encountering unexpected behavior

#### **Quick vs Full Mode**

- **Quick Mode**: For rapid checks (skips full test suite, ~5 seconds)
- **Full Mode**: Comprehensive validation (runs all tests, ~30-60 seconds)

---

### **HOW: Windows 11 PowerShell Execution Methodology**

#### **Prerequisites**

Ensure Windows 11 PowerShell is available:
```powershell
# Check PowerShell version
$PSVersionTable.PSVersion
# Should be 5.1 or higher
```

#### **Virtual Environment Setup (Required First Step)**

Before running health checks, ensure the virtual environment is created:

```powershell
# Navigate to project directory
cd g:\OC\SBITB-150626

# Create virtual environment named SBITB150626 (if not exists)
python -m venv SBITB150626

# Activate virtual environment
.\SBITB150626\Scripts\Activate.ps1

# Install dependencies (if not already installed)
pip install -e .[dev]
```

#### **Method 1: Direct Execution (Recommended)**

**Open PowerShell as Administrator and execute:**

```powershell
# Navigate to project directory
cd g:\OC\SBITB-150626

# Activate virtual environment (IMPORTANT - must do this first!)
.\SBITB150626\Scripts\Activate.ps1

# Run full health check
.\verify-project-health.ps1

# Or run in quick mode (skips full test suite)
.\verify-project-health.ps1 -Quick
```

#### **Method 2: Execution Policy Handling**

If you encounter "execution policy" errors:

```powershell
# Allow script execution for current session
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Activate virtual environment
.\SBITB150626\Scripts\Activate.ps1

# Then run the script
.\verify-project-health.ps1
```

#### **Method 3: Command Line One-Liner**

Execute from any PowerShell location:

```powershell
# Full check (with virtual environment activation)
cd g:\OC\SBITB-150626; .\SBITB150626\Scripts\Activate.ps1; .\verify-project-health.ps1

# Quick check
cd g:\OC\SBITB-150626; .\SBITB150626\Scripts\Activate.ps1; .\verify-project-health.ps1 -Quick
```

#### **Method 4: Windows Terminal**

Using Windows Terminal (recommended for better experience):

1. **Open Windows Terminal** (Ctrl+Shift+T)
2. **Select PowerShell tab** (or create new)
3. **Execute commands**:
   ```powershell
   cd g:\OC\SBITB-150626
   .\SBITB150626\Scripts\Activate.ps1
   .\verify-project-health.ps1
   ```

#### **CRITICAL EXECUTION WARNINGS**

⚠️ **You MUST activate the virtual environment before running health checks!**

**Correct Order:**
1. Navigate to project directory: `cd g:\OC\SBITB-150626`
2. Activate virtual environment: `.\SBITB150626\Scripts\Activate.ps1`
3. Run verification script: `.\verify-project-health.ps1`

**Incorrect Order (Will cause errors):**
- Running `.\verify-project-health.ps1` WITHOUT activating `SBITB150626` virtual environment
- This will use system Python which may not have required dependencies installed

**Verification of Virtual Environment:**
After activation, your PowerShell prompt should show `(SBITB150626)` prefix:
```powershell
(SBITB150626) PS g:\OC\SBITB-150626>
```

---

### **Expected Output Interpretation**

#### **Healthy Project Output**
```
========================================
 HEALTH CHECK SUMMARY
========================================

Total Checks: 45
  Passed:   45
  Failed:   0
  Skipped:  0

STATUS: ALL CHECKS PASSED - Project is healthy!
```

#### **Color Coding**
- 🟢 **Green**: Passed checks
- 🔴 **Red**: Failed checks (requires attention)
- 🟡 **Yellow**: Skipped checks or optional components

---

### **Troubleshooting Common Issues**

#### **Issue: Python Not Found**
```powershell
# Solution: Add Python to PATH or install Python
# Download from: https://python.org/downloads/
# Ensure "Add to PATH" is checked during installation
```

#### **Issue: Pip Not Found**
```powershell
# Solution: Reinstall Python or ensure pip is in PATH
python -m ensurepip --upgrade
```

#### **Issue: Git Not Found**
```powershell
# Solution: Install Git for Windows
# Download from: https://git-scm.com/download/win
```

#### **Issue: Ruff Not Installed**
```powershell
# Solution: Install development dependencies
pip install -e .[dev]
```

#### **Issue: Tests Failing**
```powershell
# Run tests with detailed output
python -m pytest tests/ -v --tb=long

# Run specific test module
python -m pytest tests/risk/test_kill_switch.py -v

# Run with coverage to see what's tested
python -m pytest tests/ --cov=src --cov-report=term-missing
```

---

### **Quick Reference Commands**

#### **Manual Verification Steps**

```powershell
# 1. Check Python version
python --version

# 2. Run full test suite
python -m pytest tests/ -v --tb=short --strict-markers

# 3. Run tests with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing

# 4. Run ruff linter
ruff check src/ tests/

# 5. Format code with ruff
ruff format src/ tests/

# 6. Run mypy type checking
mypy src/

# 7. Install all dependencies
pip install -e .[dev]

# 8. Git status
git status

# 9. View recent commits
git log --oneline -5
```

---

### **Script Parameters**

#### **Available Switches**

```powershell
# Quick mode: Skip full test suite (fast, ~5 seconds)
.\verify-project-health.ps1 -Quick

# Verbose mode: Show additional details
.\verify-project-health.ps1 -Verbose

# Install missing dependencies
.\verify-project-health.ps1 -InstallMissing

# Combine switches
.\verify-project-health.ps1 -Quick -Verbose
```

---

### **Integration with CI/CD**

#### **GitHub Actions Example**

```yaml
name: Health Check

on: [push, pull_request]

jobs:
  verify:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -e .[dev]
      - name: Run health check
        run: .\verify-project-health.ps1
        shell: pwsh
```

---

### **Exit Codes**

- **0**: All checks passed
- **1-N**: Number of failed checks

For scripting:
```powershell
.\verify-project-health.ps1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Project is healthy!"
} else {
    Write-Host "Project has $LASTEXITCODE issues!"
    exit $LASTEXITCODE
}
```

---

### **Contact & Support**

For issues or questions:
- **Project Repository**: https://github.com/npmvlKP/SBITB150626
- **Documentation**: See `SBITB-150626-Plan/` directory
- **Latest Commit**: `1afbf5c` - Initial SBITB150626 project setup

---

### **Verification Checklist**

Before proceeding to development or deployment:

- [ ] Python 3.11+ installed and accessible
- [ ] All core dependencies installed
- [ ] All 62+ tests passing
- [ ] Ruff linting shows no errors
- [ ] Git working directory is clean (or changes are intentional)
- [ ] Remote repository is configured
- [ ] pyproject.toml is valid TOML
- [ ] All required directories exist
- [ ] All required files present

---

### **Last Verified**

- **Date**: 2025-06-15
- **Status**: ✅ All checks passed (62 tests)
- **Commit**: 1afbf5c - feat: Initial SBITB150626 project setup

---

**End of Verification Protocol**