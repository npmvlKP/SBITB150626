#!/usr/bin/env python3
"""
SBITB-150626 Dependencies Verification
Checks if required Python packages are installed
"""

import sys
import subprocess

def check_core_dependencies():
    """Check if core dependencies are installed."""
    print("=" * 60)
    print("CORE DEPENDENCIES CHECK")
    print("=" * 60)
    
    core_deps = [
        "pytest",
        "structlog",
        "pydantic",
        "pydantic_settings",
        "httpx",
        "pandas",
        "numpy",
    ]
    
    results = {}
    for dep in core_deps:
        try:
            __import__(dep)
            print(f"✓ PASS: {dep}")
            results[dep] = True
        except ImportError:
            print(f"✗ FAIL: {dep} (not installed)")
            results[dep] = False
    
    return all(results.values()), results

def check_dev_tools():
    """Check if development tools are installed."""
    print("\n" + "=" * 60)
    print("DEVELOPMENT TOOLS CHECK")
    print("=" * 60)
    
    dev_tools = [
        "ruff",
        "mypy",
        "bandit",
        "pip-audit",
    ]
    
    results = {}
    for tool in dev_tools:
        try:
            result = subprocess.run(
                [tool, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"✓ PASS: {tool}")
                print(f"  Version: {result.stdout.strip()}")
                results[tool] = True
            else:
                print(f"⚠ WARNING: {tool} (not in PATH)")
                results[tool] = False
        except FileNotFoundError:
            print(f"⚠ WARNING: {tool} (not installed)")
            results[tool] = False
        except subprocess.TimeoutExpired:
            print(f"⚠ WARNING: {tool} (timeout)")
            results[tool] = False
    
    return all(results.values()), results

def main():
    """Run all dependency checks."""
    print("\n" + "=" * 60)
    print("SBITB-150626 DEPENDENCIES VERIFICATION")
    print("=" * 60)
    
    all_results = {}
    
    # Run all checks
    core_pass, core_results = check_core_dependencies()
    all_results["Core Dependencies"] = (core_pass, core_results)
    
    dev_pass, dev_results = check_dev_tools()
    all_results["Development Tools"] = (dev_pass, dev_results)
    
    # Summary
    print("\n" + "=" * 60)
    print("DEPENDENCIES VERIFICATION SUMMARY")
    print("=" * 60)
    
    total_checks = 0
    total_passed = 0
    
    for category, (passed, results) in all_results.items():
        category_total = len(results)
        category_passed = sum(1 for v in results.values() if v)
        
        print(f"\n{category}:")
        print(f"  Passed: {category_passed}/{category_total}")
        
        for item, result in results.items():
            status = "✓" if result else "✗"
            print(f"    {status} {item}")
        
        total_checks += category_total
        total_passed += category_passed
    
    print("\n" + "=" * 60)
    print(f"OVERALL: {total_passed}/{total_checks} dependencies found")
    print("=" * 60)
    
    if core_pass:
        print("✓ ALL CORE DEPENDENCIES INSTALLED")
        print("Core dependencies are available. Development tools are optional.")
        
        if not dev_pass:
            print("\n⚠ Some development tools are missing:")
            missing = [tool for tool, result in dev_results.items() if not result]
            print(f"  Missing: {', '.join(missing)}")
            print("  Install with: pip install -e .[dev]")
        
        return 0
    else:
        print("✗ SOME CORE DEPENDENCIES MISSING")
        print("Please install missing core dependencies:")
        missing = [dep for dep, result in core_results.items() if not result]
        print(f"  Missing: {', '.join(missing)}")
        print("  Install with: pip install -e .")
        return 1

if __name__ == "__main__":
    sys.exit(main())