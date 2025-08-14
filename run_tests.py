"""Test runner script for DataPlane Agent.

This script provides convenient commands to run different test suites.
"""

import subprocess
import sys
from pathlib import Path


def run_unit_tests() -> bool:
    """Run unit tests."""
    print("Running unit tests...")
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/unit/",
        "-v",
        "--tb=short",
        "--cov=.",
        "--cov-report=term-missing"
    ], cwd=Path(__file__).parent)
    return result.returncode == 0


def run_integration_tests() -> bool:
    """Run integration tests."""
    print("Running integration tests...")
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/integration/",
        "-v",
        "--tb=short"
    ], cwd=Path(__file__).parent)
    return result.returncode == 0


def run_all_tests() -> bool:
    """Run all tests."""
    print("Running all tests...")
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--cov=.",
        "--cov-report=term-missing",
        "--cov-report=html"
    ], cwd=Path(__file__).parent)
    return result.returncode == 0


def run_type_check() -> bool:
    """Run mypy type checking."""
    print("Running type checking...")
    result = subprocess.run([
        sys.executable, "-m", "mypy",
        ".",
        "--strict"
    ], cwd=Path(__file__).parent)
    return result.returncode == 0


def run_linting() -> bool:
    """Run code linting."""
    print("Running linting...")
    
    # Run flake8
    flake8_result = subprocess.run([
        sys.executable, "-m", "flake8",
        ".",
        "tests/"
    ], cwd=Path(__file__).parent)
    
    # Run black check
    black_result = subprocess.run([
        sys.executable, "-m", "black",
        "--check",
        "--diff",
        ".",
        "tests/"
    ], cwd=Path(__file__).parent)
    
    return flake8_result.returncode == 0 and black_result.returncode == 0


def run_security_check() -> bool:
    """Run security checking."""
    print("Running security check...")
    result = subprocess.run([
        sys.executable, "-m", "bandit",
        "-r", ".",
        "-f", "json"
    ], cwd=Path(__file__).parent)
    return result.returncode == 0


def run_all_checks() -> int:
    """Run all quality checks."""
    print("=" * 60)
    print("Running complete test and quality check suite")
    print("=" * 60)
    
    checks = [
        ("Type Checking", run_type_check),
        ("Code Linting", run_linting),
        ("Unit Tests", run_unit_tests),
        ("Integration Tests", run_integration_tests),
        ("Security Check", run_security_check),
    ]
    
    results = {}
    for name, check_func in checks:
        print(f"\n--- {name} ---")
        results[name] = check_func()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\nAll checks passed!")
        return 0
    else:
        print("\nSome checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "unit":
            sys.exit(0 if run_unit_tests() else 1)
        elif command == "integration":
            sys.exit(0 if run_integration_tests() else 1)
        elif command == "tests":
            sys.exit(0 if run_all_tests() else 1)
        elif command == "type":
            sys.exit(0 if run_type_check() else 1)
        elif command == "lint":
            sys.exit(0 if run_linting() else 1)
        elif command == "security":
            sys.exit(0 if run_security_check() else 1)
        elif command == "all":
            sys.exit(run_all_checks())
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    else:
        sys.exit(run_all_checks())
