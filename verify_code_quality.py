#!/usr/bin/env python3
"""SBITB-150626 Code Quality Verification Runs ruff linter and format
checks."""

import subprocess
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def run_ruff_check():
    """Run ruff linter on source code."""
    print("=" * 60)
    print("RUFF LINTER CHECK")
    print("=" * 60)

    try:
        result = subprocess.run(["ruff", "check", "src/", "tests/"], capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            print("✓ PASS: Ruff linting - No issues found")
            print(f"  Output: {result.stdout.strip()}")
            return True, ""
        else:
            print("✗ FAIL: Ruff linting found issues")
            print("\nIssues found:")
            print(result.stdout)

            # Parse errors
            errors = parse_ruff_output(result.stdout)
            return False, errors
    except FileNotFoundError:
        print("✗ FAIL: Ruff not installed")
        print("  Install with: pip install ruff")
        return False, "Ruff not installed"
    except subprocess.TimeoutExpired:
        print("✗ FAIL: Ruff check timed out")
        return False, "Ruff check timed out"
    except Exception as e:
        print(f"✗ FAIL: Ruff check failed - {e}")
        return False, str(e)


def parse_ruff_output(output):
    """Parse ruff output to extract error details."""
    errors = []
    for line in output.split("\n"):
        if "-->" in line or line.strip():
            errors.append(line)
    return "\n".join(errors)


def run_ruff_format_check():
    """Check if code is properly formatted with ruff."""
    print("\n" + "=" * 60)
    print("RUFF FORMAT CHECK")
    print("=" * 60)

    try:
        result = subprocess.run(
            ["ruff", "format", "src/", "tests/", "--check"], capture_output=True, text=True, timeout=60
        )

        if result.returncode == 0:
            print("✓ PASS: Code is properly formatted")
            return True
        else:
            print("⚠ WARNING: Code formatting issues found")
            print("  Fix with: ruff format src/ tests/")
            print("\nFiles that need formatting:")
            print(result.stdout)
            return False
    except FileNotFoundError:
        print("⚠ WARNING: Ruff not installed (skipping format check)")
        return True  # Not critical
    except subprocess.TimeoutExpired:
        print("⚠ WARNING: Ruff format check timed out")
        return False
    except Exception as e:
        print(f"⚠ WARNING: Ruff format check failed - {e}")
        return False


def main():
    """Run all code quality checks."""
    print("\n" + "=" * 60)
    print("SBITB-150626 CODE QUALITY VERIFICATION")
    print("=" * 60)

    # Run ruff linter
    ruff_pass, ruff_errors = run_ruff_check()

    # Run ruff format check
    format_pass = run_ruff_format_check()

    # Summary
    print("\n" + "=" * 60)
    print("CODE QUALITY VERIFICATION SUMMARY")
    print("=" * 60)

    print(f"\nRuff Linter: {'✓ PASS' if ruff_pass else '✗ FAIL'}")
    print(f"Ruff Format: {'✓ PASS' if format_pass else '⚠ WARNING'}")

    print("\n" + "=" * 60)

    if ruff_pass and format_pass:
        print("✓ ALL CODE QUALITY CHECKS PASSED")
        print("Code meets quality standards.")
        return 0
    elif ruff_pass and not format_pass:
        print("⚠ CODE FORMATTING ISSUES FOUND")
        print("Fix with: ruff format src/ tests/")
        return 1
    else:
        print("✗ CODE QUALITY ISSUES FOUND")
        if ruff_errors:
            print("\nErrors to fix:")
            print(ruff_errors)
        print("\nRun 'ruff check src/ tests/' to see all issues.")
        print("Run 'ruff check --fix src/ tests/' to auto-fix.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
