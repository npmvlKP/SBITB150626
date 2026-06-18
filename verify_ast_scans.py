"""AST Scanner for SBITB-150626 - G7-G10 validation gates."""

import ast
from pathlib import Path


class ASTScanner:
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.results = {
            "G7_float_literals": [],
            "G8_naive_datetimes": [],
            "G9_print_statements": [],
            "G10_function_sizes": [],
        }

    def scan(self):
        """Run all AST scans on Python files."""
        for py_file in self.root_dir.rglob("*.py"):
            # Skip test files, venv, and build artifacts
            if self._should_skip(py_file):
                continue
            try:
                with open(py_file, encoding="utf-8") as f:
                    content = f.read()
                tree = ast.parse(content, filename=str(py_file))
                self._scan_file(tree, py_file, content)
            except SyntaxError as e:
                print(f"Syntax error in {py_file}: {e}")

    def _should_skip(self, path: Path) -> bool:
        """Skip test files, venv, and build artifacts."""
        skip_patterns = [
            "venv",
            "lib",
            "site-packages",
            "__pycache__",
            ".pytest_cache",
            "node_modules",
            "SBITB150626",
            "verify_ast_scans.py",
        ]
        path_str = str(path)
        return any(p in path_str for p in skip_patterns)

    def _scan_file(self, tree: ast.AST, filepath: Path, content: str):
        """Scan a single file for all patterns."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                line_num = node.lineno
                self.results["G7_float_literals"].append(
                    (str(filepath), line_num, content.split("\n")[line_num - 1].strip())
                )

            if isinstance(node, ast.Call):
                # Check for datetime.utcnow() or datetime.now() without tz
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("utcnow", "now") and self._is_datetime_call(node):
                        self.results["G8_naive_datetimes"].append(
                            (str(filepath), node.lineno, self._get_line(content, node.lineno))
                        )

            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    self.results["G9_print_statements"].append(
                        (str(filepath), node.lineno, self._get_line(content, node.lineno))
                    )

            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                func_size = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                if func_size > 50:
                    self.results["G10_function_sizes"].append((str(filepath), node.lineno, node.name, func_size))

    def _is_datetime_call(self, node: ast.Call) -> bool:
        """Check if call is datetime.datetime.*"""
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return node.func.value.id == "datetime"
        return False

    def _get_line(self, content: str, line_num: int) -> str:
        """Get a specific line from content."""
        lines = content.split("\n")
        if 0 < line_num <= len(lines):
            return lines[line_num - 1].strip()
        return ""

    def report(self) -> str:
        """Generate a report of findings."""
        lines = ["=" * 70]
        lines.append("SBITB-150626 AST SCAN REPORT (G7-G10)")
        lines.append("=" * 70)

        # G7: Float literals
        lines.append(f"\n[G7] Float Literals: {len(self.results['G7_float_literals'])} found")
        if self.results["G7_float_literals"]:
            for file, line, code in self.results["G7_float_literals"][:10]:
                lines.append(f"  {file}:{line}")
                lines.append(f"    -> {code[:80]}")
            if len(self.results["G7_float_literals"]) > 10:
                lines.append(f"  ... and {len(self.results['G7_float_literals']) - 10} more")

        # G8: Naive datetimes
        lines.append(f"\n[G8] Naive Datetime Usage: {len(self.results['G8_naive_datetimes'])} found")
        if self.results["G8_naive_datetimes"]:
            for file, line, code in self.results["G8_naive_datetimes"]:
                lines.append(f"  {file}:{line}")
                lines.append(f"    -> {code[:80]}")

        # G9: Print statements
        lines.append(f"\n[G9] Print Statements: {len(self.results['G9_print_statements'])} found")
        if self.results["G9_print_statements"]:
            for file, line, code in self.results["G9_print_statements"][:10]:
                lines.append(f"  {file}:{line}")
                lines.append(f"    -> {code[:80]}")
            if len(self.results["G9_print_statements"]) > 10:
                lines.append(f"  ... and {len(self.results['G9_print_statements']) - 10} more")

        # G10: Large functions
        lines.append(f"\n[G10] Large Functions (>50 lines): {len(self.results['G10_function_sizes'])} found")
        if self.results["G10_function_sizes"]:
            for file, line, name, size in self.results["G10_function_sizes"]:
                lines.append(f"  {file}:{line} - {name}() [{size} lines]")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)


if __name__ == "__main__":
    import sys

    root = sys.argv[1] if len(sys.argv) > 1 else "src"

    print(f"Scanning {root} for AST patterns (G7-G10)...\n")
    scanner = ASTScanner(root)
    scanner.scan()
    print(scanner.report())
