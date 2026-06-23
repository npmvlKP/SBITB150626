"""Phase 3 Dependency Installation Verification Script.

Verifies all Phase 3 dependencies are correctly installed and TA-Lib
function signatures match the corrections table.

PowerShell escape-trap notes (Windows 11):
  - The ``ta`` package does NOT expose ``__version__`` on its module.
    Always use ``importlib.metadata.version("ta")`` instead of ``ta.__version__``.
  - ``pip-audit`` is invoked as ``python -m pip_audit`` (underscore),
    NOT as ``pip-audit.exe`` (hyphen).
  - ``pip`` must be invoked as ``python -m pip``, NOT as
    ``.venv\\Scripts\\pip.exe`` — PowerShell double-quotes strip the
    backslash before ``.venv``, corrupting the path.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import subprocess
import sys

# Known PyPI distribution names that differ from the importable module name.
_MODULE_TO_DIST: dict[str, str] = {
    "talib": "TA-Lib",
    "ta": "ta",
    "scipy": "scipy",
    "flowrisk": "flowrisk",
}


def check_import(module_name: str, attr: str | None = None) -> tuple[bool, str]:
    """Check if a module can be imported and optionally verify an attribute."""
    try:
        mod = __import__(module_name)
        if attr:
            # For submodule attrs like scipy.signal.detrend, import the submodule
            parts = module_name.split(".")
            current = mod
            for part in parts[1:]:
                current = getattr(current, part)
            getattr(current, attr)
        # Prefer importlib.metadata for version (works even when __version__ is absent)
        version = "unknown"
        dist_name = _MODULE_TO_DIST.get(module_name, module_name)
        # Try exact dist name, then module name, then hyphen/underscore variants
        candidates = [dist_name, module_name, module_name.replace("_", "-")]
        for name_attempt in candidates:
            try:
                version = importlib.metadata.version(name_attempt)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
        # Fallback: try __version__ attribute on the module
        if version == "unknown" and hasattr(mod, "__version__"):
            version = str(mod.__version__)
        return True, version
    except ImportError as e:
        return False, str(e)
    except AttributeError as e:
        return False, str(e)


def verify_talib_signatures() -> dict[str, bool]:
    """Verify TA-Lib function default parameters match corrections table."""
    import talib

    results: dict[str, bool] = {}

    expected_defaults: dict[str, dict[str, int | float]] = {
        "BBANDS": {"timeperiod": 5, "nbdevup": 2.0, "nbdevdn": 2.0},
        "EMA": {"timeperiod": 30},
        "CCI": {"timeperiod": 14},
        "RSI": {"timeperiod": 14},
        "MACD": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9},
        "ADX": {"timeperiod": 14},
        "ATR": {"timeperiod": 14},
        "MFI": {"timeperiod": 14},
    }

    for func_name, expected in expected_defaults.items():
        func = getattr(talib, func_name)
        doc = func.__doc__ or ""
        all_match = True
        for param_name, expected_val in expected.items():
            search_str = f"{param_name}: {expected_val}"
            if search_str not in doc:
                all_match = False
                break
        results[func_name] = all_match

    obv_sig = inspect.signature(talib.OBV)
    has_no_timeperiod = "timeperiod" not in str(obv_sig)
    results["OBV"] = has_no_timeperiod

    return results


def main() -> int:
    """Run all Phase 3 dependency verification checks."""
    exit_code = 0

    print("=" * 60)
    print("PHASE 3 DEPENDENCY VERIFICATION")
    print("=" * 60)

    core_deps = [
        ("talib", None, "TA-Lib"),
        ("ta", None, "ta (pure-Python fallback)"),
        ("scipy", None, "scipy"),
        ("scipy.signal", "detrend", "scipy.signal.detrend"),
    ]

    print("\n--- Core Dependencies ---")
    for module, attr, label in core_deps:
        ok, ver = check_import(module, attr)
        status = "[PASS]" if ok else "[FAIL]"
        print(f"  {label}: {status} (version: {ver})")
        if not ok:
            exit_code = 1

    print("\n--- Optional Dependencies ---")
    ok, ver = check_import("flowrisk")
    status = "[PASS]" if ok else "[WARN] NOT AVAILABLE (fallback will be used)"
    print(f"  flowrisk: {status} (version: {ver})")

    print("\n--- TA-Lib Function Signature Verification ---")
    sig_results = verify_talib_signatures()
    for func_name, passed in sig_results.items():
        status = "[CONFIRMED]" if passed else "[MISMATCH]"
        print(f"  {func_name}: {status}")
        if not passed:
            exit_code = 1

    print("\n--- Tooling Gates ---")

    # Gate: ta must NOT be accessed via ta.__version__ (the attribute does not exist)
    try:
        import ta as _ta

        _ta_version = getattr(_ta, "__version__", None)
        if _ta_version is None:
            print("  ta.__version__: [PASS] Attribute absent — use importlib.metadata.version('ta')")
        else:
            print(f"  ta.__version__: [WARN] Unexpectedly present as {_ta_version}")
    except ImportError:
        print("  ta.__version__: [FAIL] Cannot import ta")
        exit_code = 1

    # Gate: pip-audit must be invocable via `python -m pip_audit`
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            ver = result.stdout.strip().split()[-1] if result.stdout.strip() else "unknown"
            print(f"  pip-audit (python -m pip_audit): [PASS] (version: {ver})")
        else:
            print(f"  pip-audit (python -m pip_audit): [FAIL] {result.stderr.strip()}")
            exit_code = 1
    except Exception as e:
        print(f"  pip-audit (python -m pip_audit): [FAIL] {e}")
        exit_code = 1

    # Gate: pip must be invocable via `python -m pip` (NOT pip.exe — PowerShell
    # corrupts the path by stripping the backslash before .venv)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            ver = result.stdout.strip().split()[1] if result.stdout.strip() else "unknown"
            print(f"  pip (python -m pip): [PASS] (version: {ver})")
        else:
            print(f"  pip (python -m pip): [FAIL] {result.stderr.strip()}")
            exit_code = 1
    except Exception as e:
        print(f"  pip (python -m pip): [FAIL] {e}")
        exit_code = 1

    print("\n" + "=" * 60)
    if exit_code == 0:
        print("VERDICT: ALL GATES PASS")
    else:
        print("VERDICT: SOME GATES FAILED")
    print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
