"""Phase 3 Dependency Installation Verification Script.

Verifies all Phase 3 dependencies are correctly installed and TA-Lib
function signatures match the corrections table.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import sys


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
        # Try module_name first, then common PyPI name variants
        version = "unknown"
        # Special case: talib C extension uses "TA-Lib" as PyPI package name
        metadata_names = [module_name, module_name.replace("_", "-")]
        if module_name == "talib":
            metadata_names.append("TA-Lib")
        for name_attempt in metadata_names:
            try:
                version = importlib.metadata.metadata(name_attempt).get("Version", "unknown")
                break
            except Exception:
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

    print("\n" + "=" * 60)
    if exit_code == 0:
        print("VERDICT: ALL GATES PASS")
    else:
        print("VERDICT: SOME GATES FAILED")
    print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
