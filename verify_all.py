#!/usr/bin/env python3
"""SBITB-150626 Master Verification Script Runs all verification scripts and
provides comprehensive summary."""

import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def run_verification_script(script_name):
    """Run a single verification script and capture its output."""
    script_path = Path(script_name)

    if not script_path.exists():
        print(f"✗ FAIL: {script_name} not found")
        return False, f"Script not found: {script_name}"

    try:
        result = subprocess.run([sys.executable, str(script_path)], capture_output=True, text=True, timeout=300)

        return result.returncode == 0, result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        print(f"✗ FAIL: {script_name} timed out")
        return False, f"Script timed out: {script_name}"
    except Exception as e:
        print(f"✗ FAIL: {script_name} failed - {e}")
        return False, str(e)


def print_separator():
    """Print a visual separator."""
    print("\n" + "=" * 80)
    print("=" * 80 + "\n")


def main():
    """Run all verification scripts."""
    print_separator()
    print("SBITB-150626 COMPREHENSIVE HEALTH VERIFICATION")
    print("Master Script - Running All Verification Checks")
    print_separator()

    # List of verification scripts to run
    verification_scripts = [
        "verify_environment.py",
        "verify_structure.py",
        "verify_dependencies.py",
        "verify_code_quality.py",
        "verify_tests.py",
        "verify_git.py",
        "verify_build_system.py",
    ]

    # Results storage
    results = {}
    outputs = {}

    # Run each verification script
    for script in verification_scripts:
        print(f"\n>>> Running {script}...")
        print("-" * 80)

        success, output = run_verification_script(script)
        results[script] = success
        outputs[script] = output

        # Print the output
        print(output)

        if success:
            print(f"\n✓ {script} completed successfully")
        else:
            print(f"\n✗ {script} failed")

        print_separator()

    # Comprehensive Summary
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + " " * 15 + "COMPREHENSIVE VERIFICATION SUMMARY" + " " * 27 + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝\n")

    # Table header
    print(f"{'Verification Script':<35} {'Status':<10} {'Details'}")
    print("-" * 80)

    # Table content
    passed = 0
    failed = 0

    for script, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        details = "All checks passed" if success else "Check output above for details"

        print(f"{script:<35} {status:<10} {details}")

        if success:
            passed += 1
        else:
            failed += 1

    print("-" * 80)
    print(f"{'Total':<35} {passed + failed:<10} {passed} passed, {failed} failed")
    print("=" * 80 + "\n")

    # Overall assessment
    if failed == 0:
        print("✅ ALL VERIFICATION CHECKS PASSED ✅")
        print("\n🎉 The SBITB-150626 project is healthy and ready for development!")
        print("\nNext Steps:")
        print("  1. Review the project roadmap in SBITB-150626-Plan/")
        print("  2. Begin implementing Phase 1: Base Technology Stack Setup")
        print("  3. Commit your changes regularly")
        print("  4. Run these verification scripts before major commits")
        return 0
    else:
        print("❌ SOME VERIFICATION CHECKS FAILED ❌")
        print(f"\n⚠️  {failed} verification script(s) failed. Please review the errors above.")
        print("\nCommon fixes:")
        print("  • Missing dependencies: pip install -e .[dev]")
        print("  • Code quality issues: ruff check --fix src/ tests/")
        print("  • Test failures: python -m pytest tests/ -v --tb=long")
        print("  • Format issues: ruff format src/ tests/")
        print("\nRe-run individual scripts for detailed debugging:")
        for script, success in results.items():
            if not success:
                print(f"  python {script}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
