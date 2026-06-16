#!/usr/bin/env python3
"""SBITB-150626 Test Suite Verification Runs pytest and validates test
results."""

import re
import subprocess
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def run_pytest():
    """Run pytest test suite."""
    print("=" * 60)
    print("PYTEST TEST SUITE EXECUTION")
    print("=" * 60)
    print("This may take 30-60 seconds...\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "--strict-markers"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Parse results
        output = result.stdout + result.stderr

        # Extract test results
        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)
        error_match = re.search(r"(\d+) error", output)
        skipped_match = re.search(r"(\d+) skipped", output)

        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        errors = int(error_match.group(1)) if error_match else 0
        skipped = int(skipped_match.group(1)) if skipped_match else 0

        total = passed + failed + errors + skipped

        print("\nTest Results:")
        print(f"  Total:  {total}")
        print(f"  Passed: {passed}")
        if failed > 0:
            print(f"  Failed: {failed}")
        if errors > 0:
            print(f"  Errors: {errors}")
        if skipped > 0:
            print(f"  Skipped: {skipped}")

        # Show last 20 lines of output
        print("\n" + "-" * 60)
        print("Last 20 lines of test output:")
        print("-" * 60)
        lines = output.split("\n")
        last_lines = lines[-20:] if len(lines) > 20 else lines
        for line in last_lines:
            print(line)
        print("-" * 60)

        if failed == 0 and errors == 0:
            print("\n✓ PASS: All tests passed")
            return True, passed, failed, errors, skipped
        else:
            print("\n✗ FAIL: Some tests failed")
            return False, passed, failed, errors, skipped

    except FileNotFoundError:
        print("✗ FAIL: pytest not installed")
        print("  Install with: pip install pytest")
        return False, 0, 0, 0, 0
    except subprocess.TimeoutExpired:
        print("✗ FAIL: pytest timed out")
        return False, 0, 0, 0, 0
    except Exception as e:
        print(f"✗ FAIL: pytest execution failed - {e}")
        return False, 0, 0, 0, 0


def main():
    """Run test verification."""
    print("\n" + "=" * 60)
    print("SBITB-150626 TEST SUITE VERIFICATION")
    print("=" * 60)

    # Run pytest
    success, passed, failed, errors, skipped = run_pytest()

    # Summary
    print("\n" + "=" * 60)
    print("TEST VERIFICATION SUMMARY")
    print("=" * 60)

    total = passed + failed + errors + skipped
    print(f"\nTotal Tests: {total}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Errors:  {errors}")
    print(f"  Skipped: {skipped}")

    print("\n" + "=" * 60)

    if success:
        print("✓ ALL TESTS PASSED")
        print(f"Successfully executed {passed} tests.")
        return 0
    else:
        print("✗ TEST EXECUTION FAILED")
        print(f"{failed + errors} tests failed or errored.")
        print("\nTo debug failing tests:")
        print("  python -m pytest tests/ -v --tb=long")
        print("\nTo run specific test file:")
        print("  python -m pytest tests/risk/test_kill_switch.py -v")
        return 1


if __name__ == "__main__":
    sys.exit(main())
