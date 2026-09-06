"""Uvicorn launcher with deterministic AI stub (harness-only; not production).

THIS IS NOT PRODUCTION LOAD.
No real OpenAI calls.
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace


def _install_ai_stub() -> None:
    os.environ.setdefault("OPENAI_API_KEY", "capacity-stub-not-real")
    latency_file = os.environ.get(
        "SEDI_CAPACITY_AI_LATENCY_FILE", "/tmp/sedi_capacity_ai_latency_ms"
    )

    def _latency_s() -> float:
        # Prefer shared file so multi-worker children see harness sweeps.
        try:
            with open(latency_file, "r", encoding="utf-8") as fh:
                return max(0.0, float(fh.read().strip()) / 1000.0)
        except Exception:  # noqa: BLE001
            return max(0.0, float(os.environ.get("SEDI_CAPACITY_AI_LATENCY_MS", "50")) / 1000.0)

    # Seed file from env if missing
    try:
        if not os.path.exists(latency_file):
            with open(latency_file, "w", encoding="utf-8") as fh:
                fh.write(str(os.environ.get("SEDI_CAPACITY_AI_LATENCY_MS", "50")))
    except Exception:  # noqa: BLE001
        pass

    class _Resp:
        def __init__(self, text: str):
            self.output_text = text

    class _Responses:
        def create(self, *args, **kwargs):
            time.sleep(_latency_s())
            return _Resp("CAPACITY_AI_STUB_OK")

    class _Completions:
        def create(self, *args, **kwargs):
            time.sleep(_latency_s())
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="CAPACITY_AI_STUB_OK"))]
            )

    class _Chat:
        completions = _Completions()

    class _Client:
        responses = _Responses()
        chat = _Chat()

    # Patch prompt client before app import path uses it.
    import backend.app.core.conversation.prompts as prompts

    prompts.client = _Client()
    print(
        f"[CAPACITY_AI_STUB] installed file={latency_file} REAL_OPENAI_CALLED=NO "
        f"initial_ms={os.environ.get('SEDI_CAPACITY_AI_LATENCY_MS', '50')}",
        flush=True,
    )


def main() -> None:
    os.environ.setdefault("SEDI_DISABLE_SCHEDULER", "1")
    os.environ.setdefault("SEDI_PROCESS_ROLE", "api")
    os.environ.setdefault("RAG_LOCAL_ENABLED", "false")
    os.environ.setdefault("RAG_VECTOR_ENABLED", "false")
    _install_ai_stub()

    import uvicorn

    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "8000"))
    workers = int(os.environ.get("UVICORN_WORKERS", "1"))
    # Note: workers>1 re-imports app in children; stub must be installed via
    # factory or preload. For multi-worker, use --factory path below.
    if workers <= 1:
        uvicorn.run(
            "backend.app.main:app",
            host=host,
            port=port,
            workers=1,
            log_level=os.environ.get("UVICORN_LOG_LEVEL", "warning"),
        )
        return

    # Multi-worker: use import string + sitecustomize-like preload module
    os.environ["SEDI_CAPACITY_AI_STUB"] = "1"
    uvicorn.run(
        "backend.ops.capacity.controlled_load_asgi:app",
        host=host,
        port=port,
        workers=workers,
        log_level=os.environ.get("UVICORN_LOG_LEVEL", "warning"),
    )


if __name__ == "__main__":
    main()
