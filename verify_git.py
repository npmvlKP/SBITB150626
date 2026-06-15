#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SBITB-150626 Git Repository Verification
Checks git status, commits, and remote configuration
"""

import sys
import subprocess
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_git_repository():
    """Check if we're in a git repository."""
    print("=" * 60)
    print("GIT REPOSITORY CHECK")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ["git", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("✓ PASS: Git repository detected")
            return True
        else:
            print("✗ FAIL: Not a git repository")
            return False
    except FileNotFoundError:
        print("✗ FAIL: Git not installed")
        return False
    except subprocess.TimeoutExpired:
        print("✗ FAIL: Git status check timed out")
        return False

def check_working_directory():
    """Check if working directory is clean."""
    print("\n" + "=" * 60)
    print("GIT WORKING DIRECTORY STATUS")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            if not result.stdout.strip():
                print("✓ PASS: Working directory is clean")
                print("  No uncommitted changes")
                return True
            else:
                print("⚠ WARNING: Uncommitted changes detected")
                print("\nModified files:")
                for line in result.stdout.strip().split('\n'):
                    print(f"  {line}")
                return False
        else:
            print("✗ FAIL: Could not check git status")
            return False
    except FileNotFoundError:
        print("✗ FAIL: Git not installed")
        return False
    except subprocess.TimeoutExpired:
        print("✗ FAIL: Git status check timed out")
        return False

def check_commit_history():
    """Show recent commit history."""
    print("\n" + "=" * 60)
    print("RECENT COMMIT HISTORY")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("Recent commits:")
            for line in result.stdout.strip().split('\n'):
                print(f"  {line}")
            return True
        else:
            print("✗ FAIL: Could not get commit history")
            return False
    except FileNotFoundError:
        print("✗ FAIL: Git not installed")
        return False
    except subprocess.TimeoutExpired:
        print("✗ FAIL: Git log check timed out")
        return False

def check_remote_configuration():
    """Check if remote repository is configured."""
    print("\n" + "=" * 60)
    print("GIT REMOTE CONFIGURATION")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            if result.stdout.strip():
                print("✓ PASS: Remote repository configured")
                print("\nRemotes:")
                for line in result.stdout.strip().split('\n'):
                    print(f"  {line}")
                return True
            else:
                print("⚠ WARNING: No remote repository configured")
                return False
        else:
            print("✗ FAIL: Could not check remote configuration")
            return False
    except FileNotFoundError:
        print("✗ FAIL: Git not installed")
        return False
    except subprocess.TimeoutExpired:
        print("✗ FAIL: Git remote check timed out")
        return False

def main():
    """Run all git checks."""
    print("\n" + "=" * 60)
    print("SBITB-150626 GIT REPOSITORY VERIFICATION")
    print("=" * 60)
    
    all_results = {}
    
    # Run all checks
    repo_pass = check_git_repository()
    all_results["Git Repository"] = repo_pass
    
    if repo_pass:
        wd_pass = check_working_directory()
        all_results["Working Directory Clean"] = wd_pass
        
        hist_pass = check_commit_history()
        all_results["Commit History"] = hist_pass
        
        remote_pass = check_remote_configuration()
        all_results["Remote Configuration"] = remote_pass
    else:
        print("\n⚠ Skipping git checks - not a git repository")
        return 1
    
    # Summary
    print("\n" + "=" * 60)
    print("GIT VERIFICATION SUMMARY")
    print("=" * 60)
    
    for check, result in all_results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {check}")
    
    print("\n" + "=" * 60)
    
    if all(all_results.values()):
        print("✓ ALL GIT CHECKS PASSED")
        print("Git repository is properly configured.")
        return 0
    else:
        print("✗ SOME GIT CHECKS FAILED")
        print("Review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())