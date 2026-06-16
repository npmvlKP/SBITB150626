#!/usr/bin/env python3
"""SBITB-150626 Build System Verification Validates pyproject.toml and package
configuration."""

import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def check_pyproject_toml():
    """Check if pyproject.toml exists."""
    print("=" * 60)
    print("PYPROJECT.TOML CHECK")
    print("=" * 60)

    pyproject_path = Path("pyproject.toml")

    if pyproject_path.exists() and pyproject_path.is_file():
        print("✓ PASS: pyproject.toml exists")
        return True
    else:
        print("✗ FAIL: pyproject.toml not found")
        return False


def validate_toml_syntax():
    """Validate TOML syntax of pyproject.toml."""
    print("\n" + "=" * 60)
    print("TOML SYNTAX VALIDATION")
    print("=" * 60)

    try:
        import tomllib
    except ImportError:
        # Python < 3.11, use tomli
        try:
            import tomli as tomllib
        except ImportError:
            print("⚠ WARNING: TOML parser not installed")
            print("  Install with: pip install tomli")
            return False

    try:
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        print("✓ PASS: pyproject.toml is valid TOML")

        # Show project metadata
        if "project" in data:
            print("\nProject Metadata:")
            project = data["project"]
            if "name" in project:
                print(f"  Name: {project['name']}")
            if "version" in project:
                print(f"  Version: {project['version']}")
            if "description" in project:
                print(f"  Description: {project['description']}")

        return True
    except Exception as e:
        print(f"✗ FAIL: TOML parsing failed - {e}")
        return False


def main():
    """Run build system checks."""
    print("\n" + "=" * 60)
    print("SBITB-150626 BUILD SYSTEM VERIFICATION")
    print("=" * 60)

    all_results = {}

    # Run all checks
    file_pass = check_pyproject_toml()
    all_results["pyproject.toml exists"] = file_pass

    if file_pass:
        syntax_pass = validate_toml_syntax()
        all_results["TOML syntax valid"] = syntax_pass
    else:
        print("\n⚠ Skipping TOML validation - file not found")
        return 1

    # Summary
    print("\n" + "=" * 60)
    print("BUILD SYSTEM VERIFICATION SUMMARY")
    print("=" * 60)

    for check, result in all_results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {check}")

    print("\n" + "=" * 60)

    if all(all_results.values()):
        print("✓ ALL BUILD SYSTEM CHECKS PASSED")
        print("Build configuration is valid.")
        return 0
    else:
        print("✗ SOME BUILD SYSTEM CHECKS FAILED")
        print("Review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
