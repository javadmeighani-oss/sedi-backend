"""W2-P02 — models/services import circularity smoke (static; not in runtime selectors).

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
                "postgresql+psycopg2://__W2P02_REFUSED_USER__:__REFUSED__@"
                "127.0.0.1:1/__W2P02_REFUSED_DB__"
            ),
            "TEST_DATABASE_URL": (
                "postgresql+psycopg2://__W2P02_REFUSED_USER__:__REFUSED__@"
                "127.0.0.1:1/__W2P02_REFUSED_DB__"
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


def test_W2P02_T1_i5_enums_import_without_services_package_cycle() -> None:
    script = """
import sys
import importlib
importlib.import_module("backend.app.services.i5.enums")
assert "backend.app.services.i5.enums" in sys.modules
assert "backend.app.services.medical" not in sys.modules
from backend.app.services.i5.enums import SafetyReviewQueueStatus, EvidenceStrength, FreshnessState
assert SafetyReviewQueueStatus.OPEN.value == "OPEN"
assert EvidenceStrength.HIGH.value == "HIGH"
assert FreshnessState.CURRENT.value == "CURRENT"
print("W2P02_T1_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "W2P02_T1_PASS" in result.stdout


def test_W2P02_T2_safety_services_import_pure() -> None:
    script = """
import importlib
fresh = importlib.import_module("backend.app.services.i5.freshness_service")
ev = importlib.import_module("backend.app.services.i5.evidence_strength_service")
conflict = importlib.import_module("backend.app.services.i5.conflict_service")
gate = importlib.import_module("backend.app.services.i5.medical_safety_gate")
elig = importlib.import_module("backend.app.services.i5.runtime_eligibility_gate")
assert callable(fresh.calculate_freshness_state)
assert callable(ev.classify_evidence_strength)
assert callable(conflict.detect_structured_conflict)
assert callable(gate.requires_human_review)
assert callable(elig.evaluate_knowledge_unit_eligibility)
print("W2P02_T2_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "W2P02_T2_PASS" in result.stdout


def test_W2P02_T3_models_import_includes_w2p02_classes() -> None:
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
for name in ("KnowledgeConflict", "SafetyReviewQueueItem", "KnowledgeUnit"):
    assert hasattr(models, name), name
assert "knowledge_conflicts" in models.Base.metadata.tables
assert "knowledge_safety_reviews" in models.Base.metadata.tables
print("W2P02_T3_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "W2P02_T3_PASS" in result.stdout
    assert "partially initialized" not in (result.stderr + result.stdout)


def test_W2P02_T4_schemas_import() -> None:
    script = """
import importlib
schemas = importlib.import_module("backend.app.schemas.i5_knowledge_safety")
assert hasattr(schemas, "ConflictView")
assert hasattr(schemas, "SafetyQueueView")
assert hasattr(schemas, "EligibilityView")
assert hasattr(schemas, "FreshnessInputs")
print("W2P02_T4_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "W2P02_T4_PASS" in result.stdout
