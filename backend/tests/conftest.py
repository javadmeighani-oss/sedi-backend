"""
Pytest conftest: ensure backend.app resolves; disable scheduler in tests; alias app.* to backend.app.*.
"""
import os
import sys
from pathlib import Path

# backend project root = folder containing tests/ and backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Always disable scheduler in unit/integration tests
os.environ.setdefault("SEDI_DISABLE_SCHEDULER", "true")

# Prevent double-import: app.* vs backend.app.* (same codebase)
try:
    import backend.app as _backend_app
    sys.modules.setdefault("app", _backend_app)
    sys.modules.setdefault("app.models", __import__("backend.app.models", fromlist=["*"]))
    sys.modules.setdefault("app.main", __import__("backend.app.main", fromlist=["*"]))
except Exception:
    # If import fails during collection, don't crash conftest
    pass

if os.environ.get("PYTEST_DEBUG_IMPORTS"):
    try:
        import backend
        print(f"[conftest] backend.__file__ = {getattr(backend, '__file__', 'N/A')}")
    except ImportError:
        print("[conftest] backend import failed")
