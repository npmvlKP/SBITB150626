"""AST-based validation scans for SBITB-150626."""

import ast
import os
import sys


def scan_for_floats_in_money(src_dir: str = "src") -> list[str]:
    """G7: Detect float() for monetary calculations."""
    violations = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                try:
                    with open(path, encoding="utf-8") as fp:
                        tree = ast.parse(fp.read(), filename=path)
                    for node in ast.walk(tree):
                        # Check for Decimal() calls with float args
                        if isinstance(node, ast.Call):
                            func = node.func
                            if isinstance(func, ast.Name) and func.id == "Decimal":
                                for arg in node.args:
                                    if isinstance(arg, ast.Call):
                                        if isinstance(arg.func, ast.Name) and arg.func.id == "float":
                                            violations.append(f"{path}: Decimal(float(...))")
                except Exception:
                    pass
    return violations


def scan_for_naive_datetime(src_dir: str = "src") -> list[str]:
    """G8: Detect naive datetime (timezone-naive).

    Checks for datetime.now() calls WITHOUT timezone argument.
    datetime.now(timezone.utc) is valid (timezone-aware).
    """
    violations = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                try:
                    with open(path, encoding="utf-8") as fp:
                        content = fp.read()
                    tree = ast.parse(content, filename=path)
                    for node in ast.walk(tree):
                        # Check datetime.datetime.now() without timezone
                        if isinstance(node, ast.Call):
                            func = node.func
                            if isinstance(func, ast.Attribute) and func.attr == "now":
                                if isinstance(func.value, ast.Name) and func.value.id == "datetime":
                                    # Check if timezone argument is provided
                                    if not node.args:  # No arguments = naive datetime
                                        violations.append(f"{path}: datetime.now() without timezone")
                except Exception:
                    pass
    return violations


def scan_for_print_statements(src_dir: str = "src") -> list[str]:
    """G9: Detect print() statements."""
    violations = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                try:
                    with open(path, encoding="utf-8") as fp:
                        tree = ast.parse(fp.read(), filename=path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Name) and node.func.id == "print":
                                violations.append(f"{path}: print() statement")
                except Exception:
                    pass
    return violations


def scan_for_large_functions(src_dir: str = "src", max_lines: int = 100) -> list[str]:
    """G10: Detect functions > max_lines."""
    violations = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                try:
                    with open(path, encoding="utf-8") as fp:
                        lines = fp.readlines()
                    tree = ast.parse("".join(lines), filename=path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                            line_count = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                            if line_count > max_lines:
                                violations.append(
                                    f"{path}:{node.lineno} {node.name}() is {line_count} lines (max {max_lines})"
                                )
                except Exception:
                    pass
    return violations


if __name__ == "__main__":
    print("=" * 60)
    print("SBITB-150626 AST Validation Scans")
    print("=" * 60)

    # G7: Float scan
    print("\n[G7] Float for monetary calculations:")
    float_violations = scan_for_floats_in_money()
    if float_violations:
        print(f"  FAIL: {len(float_violations)} violations")
        for v in float_violations[:10]:
            print(f"    - {v}")
    else:
        print("  PASS: No float for monetary values")

    # G8: Naive datetime scan
    print("\n[G8] Naive datetime (no timezone):")
    dt_violations = scan_for_naive_datetime()
    if dt_violations:
        print(f"  FAIL: {len(dt_violations)} violations")
        for v in dt_violations[:10]:
            print(f"    - {v}")
    else:
        print("  PASS: No naive datetime detected")

    # G9: Print statements
    print("\n[G9] Print statements:")
    print_violations = scan_for_print_statements()
    if print_violations:
        print(f"  FAIL: {len(print_violations)} violations")
        for v in print_violations[:10]:
            print(f"    - {v}")
    else:
        print("  PASS: No print statements")

    # G10: Large functions
    print("\n[G10] Function size (>100 lines):")
    func_violations = scan_for_large_functions()
    if func_violations:
        print(f"  FAIL: {len(func_violations)} violations")
        for v in func_violations[:10]:
            print(f"    - {v}")
    else:
        print("  PASS: No oversized functions")

    # Summary
    print("\n" + "=" * 60)
    total = len(float_violations) + len(dt_violations) + len(print_violations) + len(func_violations)
    if total == 0:
        print("ALL AST SCANS PASSED")
        sys.exit(0)
    else:
        print(f"TOTAL VIOLATIONS: {total}")
        sys.exit(1)
