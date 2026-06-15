#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SBITB-150626 Environment Verification
Checks Python version, pip, and virtual environment setup
"""

import sys
import subprocess
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_python_version():
    """Check if Python 3.11+ is installed."""
    print("=" * 60)
    print("PYTHON VERSION CHECK")
    print("=" * 60)
    
    version = sys.version_info
    print(f"Python Version: {sys.version}")
    
    if version.major == 3 and version.minor >= 11:
        print("✓ PASS: Python 3.11+ detected")
        return True
    else:
        print("✗ FAIL: Python 3.11+ required")
        print(f"  Current: {version.major}.{version.minor}.{version.micro}")
        return False

def check_pip():
    """Check if pip is available."""
    print("\n" + "=" * 60)
    print("PIP CHECK")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"✓ PASS: {result.stdout.strip()}")
            return True
        else:
            print("✗ FAIL: pip not available")
            return False
    except Exception as e:
        print(f"✗ FAIL: pip check failed - {e}")
        return False

def check_virtual_environment():
    """Check if virtual environment is active."""
    print("\n" + "=" * 60)
    print("VIRTUAL ENVIRONMENT CHECK")
    print("=" * 60)
    
    venv_path = Path("SBITB150626")
    
    if venv_path.exists() and venv_path.is_dir():
        print(f"✓ PASS: Virtual environment directory exists at {venv_path}")
        
        # Check if Scripts/python.exe exists
        python_exe = venv_path / "Scripts" / "python.exe"
        if python_exe.exists():
            print(f"✓ PASS: Python executable found at {python_exe}")
        else:
            print(f"✗ FAIL: Python executable not found at {python_exe}")
            return False
        
        # Check if venv is active (compare executables)
        current_exe = Path(sys.executable)
        if python_exe.samefile(current_exe):
            print("✓ PASS: Virtual environment is ACTIVE")
            print(f"  Current Python: {sys.executable}")
            return True
        else:
            print("⚠ WARNING: Virtual environment directory exists but NOT active")
            print(f"  Current Python: {sys.executable}")
            print(f"  Venv Python:    {python_exe}")
            print("  Activate with: .\\SBITB150626\\Scripts\\Activate.ps1")
            return False
    else:
        print(f"✗ FAIL: Virtual environment not found at {venv_path}")
        print("  Create with: python -m venv SBITB150626")
        return False

def check_git():
    """Check if Git is installed."""
    print("\n" + "=" * 60)
    print("GIT CHECK")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"✓ PASS: {result.stdout.strip()}")
            return True
        else:
            print("✗ FAIL: Git not found")
            return False
    except FileNotFoundError:
        print("✗ FAIL: Git not installed or not in PATH")
        return False
    except Exception as e:
        print(f"✗ FAIL: Git check failed - {e}")
        return False

def check_docker():
    """Check if Docker is installed (optional)."""
    print("\n" + "=" * 60)
    print("DOCKER CHECK (OPTIONAL)")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"✓ PASS: {result.stdout.strip()}")
            return True
        else:
            print("⚠ WARNING: Docker not found (optional for development)")
            return True
    except FileNotFoundError:
        print("⚠ WARNING: Docker not installed or not in PATH (optional)")
        return True
    except Exception as e:
        print(f"⚠ WARNING: Docker check failed - {e} (optional)")
        return True

def main():
    """Run all environment checks."""
    print("\n" + "=" * 60)
    print("SBITB-150626 ENVIRONMENT VERIFICATION")
    print("=" * 60)
    
    results = {
        "Python Version": check_python_version(),
        "pip": check_pip(),
        "Virtual Environment": check_virtual_environment(),
        "Git": check_git(),
        "Docker (optional)": check_docker()
    }
    
    # Summary
    print("\n" + "=" * 60)
    print("ENVIRONMENT VERIFICATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\nTotal Checks: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    
    print("\nDetailed Results:")
    for check, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {check}")
    
    print("\n" + "=" * 60)
    
    if all(results.values()):
        print("✓ ALL ENVIRONMENT CHECKS PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ SOME ENVIRONMENT CHECKS FAILED")
        print("Please review the errors above and fix them before proceeding.")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())