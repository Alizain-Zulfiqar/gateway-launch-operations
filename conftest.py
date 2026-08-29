import sys
import pytest
from pathlib import Path


def pytest_configure(config):
    """
    Warn if running under the system Python rather than the project venv.
    A missing venv-installed library (numpy, PyQt6, fpdf2) is the diagnostic
    signal that the wrong interpreter is being used.
    """
    missing = []
    for lib in ['numpy', 'PyQt6', 'fpdf']:
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)

    if missing:
        print(
            f"\n{'='*60}\n"
            f"WARNING: Running tests under the wrong Python interpreter.\n"
            f"Missing libraries: {', '.join(missing)}\n\n"
            f"Fix: run tests using the project venv:\n"
            f"  venv\\Scripts\\python.exe -m pytest\n"
            f"or activate the venv first:\n"
            f"  venv\\Scripts\\activate\n"
            f"  python -m pytest\n"
            f"{'='*60}\n",
            file=sys.stderr
        )
