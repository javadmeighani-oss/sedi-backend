"""
Pytest conftest: ensure backend.app resolves to backend/backend/app (not backend/backend/backend/app).
"""
import os
import sys
from pathlib import Path

# backend project root = folder containing tests/ and backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

if os.environ.get("PYTEST_DEBUG_IMPORTS"):
    try:
        import backend
        print(f"[conftest] backend.__file__ = {getattr(backend, '__file__', 'N/A')}")
    except ImportError:
        print("[conftest] backend import failed")
