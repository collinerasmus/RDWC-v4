#!/usr/bin/env python3
"""
Validation script for RDWC-v4 Codespaces environment.
Run this after the devcontainer is created to verify everything is set up correctly.
"""

import sys
import json
from pathlib import Path

def check_config_exists():
    """Verify devcontainer.json exists and is valid."""
    config_path = Path(__file__).parent / "devcontainer.json"
    if not config_path.exists():
        print("❌ devcontainer.json not found")
        return False
    
    try:
        with open(config_path) as f:
            config = json.load(f)
        print("✅ devcontainer.json is valid JSON")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ devcontainer.json has invalid JSON: {e}")
        return False

def check_python_version():
    """Verify Python version is 3.9+."""
    if sys.version_info >= (3, 9):
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} (>= 3.9)")
        return True
    else:
        print(f"❌ Python {sys.version_info.major}.{sys.version_info.minor} (need >= 3.9)")
        return False

def check_imports():
    """Verify key dependencies can be imported."""
    required_modules = [
        ("fastapi", "FastAPI web framework"),
        ("uvicorn", "ASGI server"),
        ("pytest", "Testing framework"),
        ("gpiozero", "GPIO control (mocked in Codespaces)"),
        ("smbus2", "I²C communication (mocked in Codespaces)"),
    ]
    
    all_ok = True
    for module_name, description in required_modules:
        try:
            __import__(module_name)
            print(f"✅ {module_name} - {description}")
        except ImportError:
            print(f"❌ {module_name} - {description} (not installed)")
            all_ok = False
    
    return all_ok

def check_project_structure():
    """Verify key project files exist."""
    repo_root = Path(__file__).parent.parent
    required_files = [
        "app/main.py",
        "requirements.txt",
        "requirements-dev.txt",
        "pytest.ini",
        "README.md",
    ]
    
    all_ok = True
    for file_path in required_files:
        full_path = repo_root / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} (missing)")
            all_ok = False
    
    return all_ok

def main():
    """Run all validation checks."""
    print("=" * 60)
    print("RDWC-v4 Codespaces Environment Validation")
    print("=" * 60)
    print()
    
    checks = [
        ("Configuration", check_config_exists),
        ("Python Version", check_python_version),
        ("Dependencies", check_imports),
        ("Project Structure", check_project_structure),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n{name}:")
        print("-" * 40)
        result = check_func()
        results.append(result)
    
    print("\n" + "=" * 60)
    if all(results):
        print("✅ All checks passed! Codespaces environment is ready.")
        print("\nYou can now:")
        print("  - Run tests: pytest")
        print("  - Start API: uvicorn app.main:app --reload --host 0.0.0.0 --port 8080")
        print("  - View docs: see README.md and .devcontainer/README.md")
        return 0
    else:
        print("❌ Some checks failed. See above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
