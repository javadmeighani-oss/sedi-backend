"""W2-P01 — models/services import circularity smoke (static; not in runtime selectors).

Subprocess-only import proofs. No live DB connects.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TIMEOUT_SEC = 60


def _isolated_env() -> dict[str, str]:
    keep = (
        "PATH",
        "SystemRoot",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "COMSPEC",
        "PATHEXT",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "USERNAME",
    )
    env: dict[str, str] = {}
    for key in keep:
        val = os.environ.get(key)
        if val:
            env[key] = val
    env.update(
        {
            "PYTHONPATH": str(_REPO_ROOT),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "SEDI_DISABLE_SCHEDULER": "1",
            "APP_ENV": "validation_isolated",
            "ENVIRONMENT": "validation_isolated",
            "ENV": "validation_isolated",
            "DATABASE_URL": (
                "postgresql+psycopg2://__W2P01_REFUSED_USER__:__REFUSED__@"
                "127.0.0.1:1/__W2P01_REFUSED_DB__"
            ),
            "TEST_DATABASE_URL": (
                "postgresql+psycopg2://__W2P01_REFUSED_USER__:__REFUSED__@"
                "127.0.0.1:1/__W2P01_REFUSED_DB__"
            ),
        }
    )
    return env


def _run_inline(script: str, *, timeout: int = _TIMEOUT_SEC) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-c", textwrap.dedent(script)],
        cwd=str(_REPO_ROOT),
        env=_isolated_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_W2P01_T1_i5_enums_import_without_services_package_cycle() -> None:
    script = """
import sys
import importlib
importlib.import_module("backend.app.services.i5.enums")
assert "backend.app.services.i5.enums" in sys.modules
assert "backend.app.services.medical" not in sys.modules
from backend.app.services.i5.enums import SupersessionState, MemoryChangeKind, MemoryTransitionKind
assert SupersessionState.CURRENT.value == "CURRENT"
assert MemoryChangeKind.CONTENT_CHANGE.value == "CONTENT_CHANGE"
assert MemoryTransitionKind.NO_CHANGE.value == "NO_CHANGE"
print("W2P01_T1_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "W2P01_T1_PASS" in result.stdout


def test_W2P01_T2_memory_and_supersession_services_import_pure() -> None:
    script = """
import importlib
mem = importlib.import_module("backend.app.services.i5.knowledge_memory_service")
sup = importlib.import_module("backend.app.services.i5.supersession_service")
assert callable(mem.build_memory_item_id)
assert callable(sup.compute_structured_diff)
assert callable(sup.resolve_superseded_by)
print("W2P01_T2_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "W2P01_T2_PASS" in result.stdout


def test_W2P01_T3_models_import_includes_w2p01_classes() -> None:
    script = """
import importlib

def _refuse(*a, **k):
    raise RuntimeError("SENTINEL_DB_CONNECT_ATTEMPTED")

try:
    import sqlalchemy.engine.base as seb
    seb.Engine.connect = _refuse
except Exception:
    pass
try:
    import psycopg2
    psycopg2.connect = _refuse
except Exception:
    pass

models = importlib.import_module("backend.app.models")
for name in ("KnowledgeMemoryItem", "KnowledgeMemoryTransition", "KnowledgeUnit"):
    assert hasattr(models, name), name
assert "supersedes_unit_id" in models.KnowledgeUnit.__table__.c
assert "superseded_by" not in models.KnowledgeUnit.__table__.c
print("W2P01_T3_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "W2P01_T3_PASS" in result.stdout
    assert "partially initialized" not in (result.stderr + result.stdout)


def test_W2P01_T4_schemas_import() -> None:
    script = """
import importlib
schemas = importlib.import_module("backend.app.schemas.i5_knowledge_memory")
assert hasattr(schemas, "MemoryItemView")
assert hasattr(schemas, "StructuredDiffView")
assert hasattr(schemas, "TransitionView")
print("W2P01_T4_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "W2P01_T4_PASS" in result.stdout
