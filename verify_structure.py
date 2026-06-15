#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SBITB-150626 Project Structure Verification
Validates core files, directories, and module structure
"""

import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_required_files():
    """Check if required files exist."""
    print("=" * 60)
    print("REQUIRED FILES CHECK")
    print("=" * 60)
    
    required_files = {
        "pyproject.toml": True,
        ".gitignore": True,
        ".pre-commit-config.yaml": False,
    }
    
    results = {}
    for file_path, required in required_files.items():
        path = Path(file_path)
        exists = path.exists() and path.is_file()
        
        if exists:
            print(f"✓ PASS: {file_path}")
            results[file_path] = True
        else:
            if required:
                print(f"✗ FAIL: {file_path} (required)")
                results[file_path] = False
            else:
                print(f"⚠ WARNING: {file_path} (optional)")
                results[file_path] = True  # Optional, so consider pass
    
    return all(results.values()), results

def check_required_directories():
    """Check if required directories exist."""
    print("\n" + "=" * 60)
    print("REQUIRED DIRECTORIES CHECK")
    print("=" * 60)
    
    required_dirs = [
        "src",
        "tests",
        "config",
        "deployment",
        "scripts",
    ]
    
    results = {}
    for dir_path in required_dirs:
        path = Path(dir_path)
        exists = path.exists() and path.is_dir()
        
        if exists:
            print(f"✓ PASS: {dir_path}/")
            results[dir_path] = True
        else:
            print(f"✗ FAIL: {dir_path}/ (directory not found)")
            results[dir_path] = False
    
    return all(results.values()), results

def check_source_modules():
    """Check if source module structure exists."""
    print("\n" + "=" * 60)
    print("SOURCE MODULES CHECK")
    print("=" * 60)
    
    source_modules = [
        "src/risk",
        "src/brokers",
        "src/data",
        "src/strategy",
    ]
    
    results = {}
    for module_path in source_modules:
        path = Path(module_path)
        exists = path.exists() and path.is_dir()
        
        if exists:
            # Check for __init__.py
            init_file = path / "__init__.py"
            if init_file.exists():
                print(f"✓ PASS: {module_path}/ (with __init__.py)")
                results[module_path] = True
            else:
                print(f"⚠ WARNING: {module_path}/ (missing __init__.py)")
                results[module_path] = False
        else:
            print(f"✗ FAIL: {module_path}/ (module not found)")
            results[module_path] = False
    
    return all(results.values()), results

def check_config_files():
    """Check if configuration files exist."""
    print("\n" + "=" * 60)
    print("CONFIGURATION FILES CHECK")
    print("=" * 60)
    
    config_files = [
        "config/__init__.py",
        "config/settings.py",
        "config/secrets.env.example",
    ]
    
    results = {}
    for file_path in config_files:
        path = Path(file_path)
        exists = path.exists() and path.is_file()
        
        if exists:
            print(f"✓ PASS: {file_path}")
            results[file_path] = True
        else:
            print(f"✗ FAIL: {file_path} (not found)")
            results[file_path] = False
    
    return all(results.values()), results

def main():
    """Run all structure checks."""
    print("\n" + "=" * 60)
    print("SBITB-150626 PROJECT STRUCTURE VERIFICATION")
    print("=" * 60)
    
    all_results = {}
    
    # Run all checks
    files_pass, files_results = check_required_files()
    all_results["Required Files"] = (files_pass, files_results)
    
    dirs_pass, dirs_results = check_required_directories()
    all_results["Required Directories"] = (dirs_pass, dirs_results)
    
    modules_pass, modules_results = check_source_modules()
    all_results["Source Modules"] = (modules_pass, modules_results)
    
    config_pass, config_results = check_config_files()
    all_results["Configuration Files"] = (config_pass, config_results)
    
    # Summary
    print("\n" + "=" * 60)
    print("PROJECT STRUCTURE VERIFICATION SUMMARY")
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
    print(f"OVERALL: {total_passed}/{total_checks} checks passed")
    print("=" * 60)
    
    if total_passed == total_checks:
        print("✓ ALL STRUCTURE CHECKS PASSED")
        print("Project structure is complete and valid.")
        return 0
    else:
        print(f"✗ {total_checks - total_passed} STRUCTURE CHECKS FAILED")
        print("Please review the errors above and fix missing files/directories.")
        return 1

if __name__ == "__main__":
    sys.exit(main())