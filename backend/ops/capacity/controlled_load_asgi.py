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

# Harness-only pool probe (QueuePool checkout/timeout counters → shared file)
try:
    from backend.app.database import engine as _engine
    from backend.ops.capacity.controlled_load_pool_probe import install_pool_probe

    install_pool_probe(_engine)
except Exception as _probe_exc:  # noqa: BLE001
    print(f"[CAPACITY_POOL_PROBE] install_failed err={type(_probe_exc).__name__}", flush=True)

__all__ = ["app"]
