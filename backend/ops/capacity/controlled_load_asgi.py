"""ASGI app entry for multi-worker capacity API with AI stub preload."""

from __future__ import annotations

import os

# Must run before importing main app in worker processes.
os.environ.setdefault("SEDI_DISABLE_SCHEDULER", "1")
os.environ.setdefault("SEDI_PROCESS_ROLE", "api")
os.environ.setdefault("RAG_LOCAL_ENABLED", "false")
os.environ.setdefault("RAG_VECTOR_ENABLED", "false")
os.environ.setdefault("OPENAI_API_KEY", "capacity-stub-not-real")

from backend.ops.capacity.controlled_load_api import _install_ai_stub

_install_ai_stub()

from backend.app.main import app  # noqa: E402

__all__ = ["app"]
