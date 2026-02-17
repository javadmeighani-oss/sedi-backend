"""
Pytest conftest: ensure backend.app resolves; disable scheduler in tests; alias app.* to backend.app.*.
"""
import os
import sys
import importlib
from pathlib import Path

# Before any app/backend.app import: disable scheduler and set test env
os.environ.setdefault("SEDI_DISABLE_SCHEDULER", "true")
os.environ.setdefault("ENV", "test")

# backend project root = folder containing tests/ and backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Alias app.* to backend.app.* so SQLAlchemy tables are not defined twice
sys.modules.setdefault("app", importlib.import_module("backend.app"))
sys.modules.setdefault("app.models", importlib.import_module("backend.app.models"))
sys.modules.setdefault("app.main", importlib.import_module("backend.app.main"))

if os.environ.get("PYTEST_DEBUG_IMPORTS"):
    try:
        import backend
        print(f"[conftest] backend.__file__ = {getattr(backend, '__file__', 'N/A')}")
    except ImportError:
        print("[conftest] backend import failed")
