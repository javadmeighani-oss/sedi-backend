"""
Compatibility shim.
Canonical entrypoint: backend.app.main:app
"""

from backend.app.main import app  # re-export canonical FastAPI app
