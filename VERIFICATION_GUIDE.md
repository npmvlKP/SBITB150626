# SBITB-150626 Python Verification Scripts Guide

## Overview

This project now includes individual Python verification scripts to replace the PowerShell script. Each script performs specific health checks and provides comprehensive output with clear pass/fail indicators and remediation instructions.

## Verification Scripts

### 1. `verify_environment.py`
Checks Python version, pip, virtual environment, Git, and Docker setup.

**Run:**
```bash
python verify_environment.py
```

**What it checks:**
- Python 3.11+ installed
- pip available
- SBITB150626 virtual environment exists and is active
- Git installed
- Docker installed (optional)

---

### 2. `verify_structure.py`
Validates project structure, required files, directories, and modules.

**Run:**
```bash
python verify_structure.py
```

**What it checks:**
- Required files: pyproject.toml, .gitignore
- Required directories: src/, tests/, config/, deployment/, scripts/
- Source modules: risk/, brokers/, data/, strategy/
- Configuration files: settings.py, secrets.env.example

---

### 3. `verify_dependencies.py`
Checks if required Python packages and development tools are installed.

**Run:**
```bash
python verify_dependencies.py
```

**What it checks:**
- Core dependencies: pytest, structlog, pydantic, pydantic-settings, httpx, pandas, numpy
- Development tools: ruff, mypy, bandit, pip-audit

**Fix missing dependencies:**
```bash
# Install core dependencies
pip install pytest structlog pydantic pydantic-settings httpx pandas numpy

# Install development tools
pip install ruff mypy bandit pip-audit

# Or install everything at once
pip install pytest structlog pydantic pydantic-settings httpx pandas numpy ruff mypy bandit pip-audit
```

---

### 4. `verify_code_quality.py`
Runs ruff linter and format checks.

**Run:**
```bash
python verify_code_quality.py
```

**What it checks:**
- Ruff linting (code quality issues)
- Ruff formatting (code style)

**Fix code quality issues:**
```bash
# Auto-fix linting issues
ruff check --fix src/ tests/

# Auto-format code
ruff format src/ tests/

# Check again
ruff check src/ tests/
```

---

### 5. `verify_tests.py`
Runs pytest test suite and validates results.

**Run:**
```bash
python verify_tests.py
```

**What it checks:**
- All tests execute successfully
- No test failures or errors
- Test coverage (if available)

**Run tests manually:**
```bash
# Run all tests
python -m pytest tests/ -v --tb=short --strict-markers

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
python -m pytest tests/risk/test_kill_switch.py -v

# Run with detailed traceback
python -m pytest tests/ -v --tb=long
```

---

### 6. `verify_git.py`
Checks git repository status, commit history, and remote configuration.

**Run:**
```bash
python verify_git.py
```

**What it checks:**
- Git repository initialized
- Working directory clean (no uncommitted changes)
- Commit history available
- Remote repository configured

---

### 7. `verify_build_system.py`
Validates pyproject.toml and package configuration.

**Run:**
```bash
python verify_build_system.py
```

**What it checks:**
- pyproject.toml exists
- TOML syntax is valid
- Project metadata is present

---

### 8. `verify_all.py` (Master Script)
Runs all verification scripts sequentially and provides comprehensive summary.

**Run:**
```bash
python verify_all.py
```

**What it does:**
- Executes all 7 verification scripts in order
- Captures all output
- Provides comprehensive summary table
- Shows overall project health status
- Offers remediation steps if failures occur

---

## Prerequisites

### Virtual Environment Setup

**IMPORTANT: The virtual environment is named `SBITB150626` (NOT `.venv`)**

```bash
# Navigate to project directory
cd g:\OC\SBITB-150626

# Activate virtual environment (Windows PowerShell)
.\SBITB150626\Scripts\Activate.ps1

# Verify activation (prompt should show (SBITB150626) prefix)
(SBITB150626) PS g:\OC\SBITB-150626>

# Verify Python version
python --version
# Expected: Python 3.11 or higher
```

### Install Dependencies

```bash
# Activate virtual environment first
.\SBITB150626\Scripts\Activate.ps1

# Install all required packages
pip install pytest structlog pydantic pydantic-settings httpx pandas numpy ruff mypy

# Verify installation
python verify_dependencies.py
```

---

## Execution Workflow

### Initial Setup (First Time)

```bash
# 1. Navigate to project
cd g:\OC\SBITB-150626

# 2. Activate virtual environment
.\SBITB150626\Scripts\Activate.ps1

# 3. Install dependencies
pip install pytest structlog pydantic pydantic-settings httpx pandas numpy ruff mypy

# 4. Run comprehensive verification
python verify_all.py
```

### Daily Development Workflow

```bash
# 1. Activate virtual environment
.\SBITB150626\Scripts\Activate.ps1

# 2. Quick health check (environment only)
python verify_environment.py

# 3. Run tests
python verify_tests.py

# 4. Check code quality
python verify_code_quality.py

# Or run everything at once
python verify_all.py
```

### Pre-Commit Workflow

```bash
# 1. Activate virtual environment
.\SBITB150626\Scripts\Activate.ps1

# 2. Run all checks
python verify_all.py

# 3. If all pass, commit changes
git add .
git commit -m "Your commit message"
git push origin main
```

### Troubleshooting Workflow

```bash
# 1. Run individual scripts to identify issues
python verify_dependencies.py
python verify_code_quality.py
python verify_tests.py

# 2. Fix identified issues
pip install <missing_package>
ruff check --fix src/ tests/
ruff format src/ tests/

# 3. Verify fixes
python verify_all.py
```

---

## Common Issues and Solutions

### Issue: "pytest not installed"

**Solution:**
```bash
pip install pytest
```

### Issue: "Ruff not installed"

**Solution:**
```bash
pip install ruff
```

### Issue: "Code formatting issues found"

**Solution:**
```bash
ruff format src/ tests/
```

### Issue: "Tests failed"

**Solution:**
```bash
# Run with detailed output
python -m pytest tests/ -v --tb=long

# Run specific failing test
python -m pytest tests/risk/test_kill_switch.py::TestKillSwitch::test_activate -v
```

### Issue: "Virtual environment not active"

**Solution:**
```bash
.\SBITB150626\Scripts\Activate.ps1
```

### Issue: "pip install -e .[dev] fails"

**Solution:**
```bash
# Install packages individually
pip install pytest structlog pydantic pydantic-settings httpx pandas numpy ruff mypy
```

---

## Output Interpretation

### Pass Indicators
- ✓ PASS: Check succeeded
- ✅ ALL CHECKS PASSED: Overall success

### Fail Indicators
- ✗ FAIL: Check failed
- ⚠ WARNING: Non-critical issue
- ❌ SOME CHECKS FAILED: Overall failure

### Summary Format

Each script ends with a comprehensive summary:

```
========================================
VERIFICATION SUMMARY
========================================

Total Checks: 25
  Passed:   25
  Failed:   0

Detailed Results:
  ✓ PASS: Python Version
  ✓ PASS: pip
  ✓ PASS: Virtual Environment
  ✓ PASS: Git
  ✓ PASS: Docker (optional)

========================================
✓ ALL CHECKS PASSED
========================================
```

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Verification

on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install pytest structlog pydantic pydantic-settings httpx pandas numpy ruff mypy
      - name: Run verification
        run: python verify_all.py
```

---

## Best Practices

1. **Run verification before committing**: Always run `python verify_all.py` before committing code
2. **Fix warnings promptly**: Address warnings before they become failures
3. **Keep dependencies updated**: Regularly update packages and re-run verification
4. **Test in clean environment**: Periodically test in a fresh virtual environment
5. **Review failed checks**: Read verification output carefully to understand issues
6. **Document custom checks**: Add custom verification scripts for project-specific needs

---

## Troubleshooting Quick Reference

| Symptom | Solution |
|---------|----------|
| Script not found | Check you're in the project directory |
| Permission denied | Run with elevated permissions |
| Python not found | Ensure Python is in PATH |
| Module not found | Install missing dependencies |
| Tests timeout | Increase timeout or check for infinite loops |
| Git errors | Check git installation and repository status |

---

## Additional Resources

- **Project Documentation**: See `SBITB-150626-Plan/` directory
- **Configuration**: See `config/settings.py`
- **Test Examples**: See `tests/` directory
- **Source Code**: See `src/` directory

---

## Support

For issues or questions:
1. Check the output of individual verification scripts
2. Review the troubleshooting section above
3. Consult the project documentation in `SBITB-150626-Plan/`
4. Run `python verify_all.py` for comprehensive diagnostics

---

## Version History

- **v1.0** (2025-06-15): Initial Python verification scripts
  - Created 8 individual verification scripts
  - Added comprehensive error handling
  - Included detailed output and remediation steps
  - Replaced PowerShell script with Python alternatives

---

**Last Updated**: 2025-06-15
**Python Version**: 3.11+
**Virtual Environment**: SBITB150626
**Status**: Active
