"""W1-P01 — models/services package circularity regression (authored; not executed here).

Permanent regression coverage for Option B lazy package re-exports in
backend.app.services.__init__. Guards against reintroduction of the cycle:

  models → services.i5.enums → services.__init__ (eager MedicalService) → medical → models

Top-level application imports are prohibited in this file. Import-state proofs
run only inside fresh subprocesses with PYTHONDONTWRITEBYTECODE=1 / python -B.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TIMEOUT_SEC = 60

_EXPECTED_ALL = [
    "MedicalService",
    "DecisionEngine",
    "NotificationBuilder",
    "TimingRules",
    "RAGService",
    "UserContextService",
    "UserContextPack",
]

_LAZY_MODULES = [
    "backend.app.services.medical",
    "backend.app.services.notification_engine",
    "backend.app.services.rag",
    "backend.app.services.user_context",
]


def _isolated_env() -> dict[str, str]:
    """Minimal subprocess environment: no DB/network config, no bytecode writes."""
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
            # Sentinel URLs — create_engine may construct; must not be live prod.
            "DATABASE_URL": (
                "postgresql+psycopg2://__W1P01_REFUSED_USER__:__REFUSED__@"
                "127.0.0.1:1/__W1P01_REFUSED_DB__"
            ),
            "TEST_DATABASE_URL": (
                "postgresql+psycopg2://__W1P01_REFUSED_USER__:__REFUSED__@"
                "127.0.0.1:1/__W1P01_REFUSED_DB__"
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


def test_T1_services_package_init_does_not_eager_load_lazy_export_modules() -> None:
    """Importing backend.app.services must not preload governed lazy modules."""
    mods = ", ".join(repr(m) for m in _LAZY_MODULES)
    script = f"""
import sys
import backend.app.services as services  # noqa: F401
loaded = [m for m in ({mods}) if m in sys.modules]
assert not loaded, loaded
print("T1_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "T1_PASS" in result.stdout


def test_T2_models_import_succeeds_without_circular_partial_init() -> None:
    """backend.app.models must import cleanly (historical V3 circularity regression)."""
    script = """
import importlib
import sys

# Soft refuse accidental real connects if drivers are present.
def _refuse(*a, **k):
    raise RuntimeError("SENTINEL_DB_CONNECT_ATTEMPTED")

try:
    import psycopg2
    psycopg2.connect = _refuse
except Exception:
    pass
try:
    import sqlalchemy.engine.base as seb
    seb.Engine.connect = _refuse
except Exception:
    pass

importlib.import_module("backend.app.models")
assert "backend.app.models" in sys.modules
print("T2_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "T2_PASS" in result.stdout
    assert "partially initialized" not in (result.stderr + result.stdout)


def test_T3_lazy_MedicalService_is_same_as_direct_import() -> None:
    script = """
from backend.app.services import MedicalService
from backend.app.services.medical import MedicalService as DirectMedicalService
assert MedicalService is DirectMedicalService
print("T3_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "T3_PASS" in result.stdout


def test_T4_lazy_export_is_cached_in_package_globals() -> None:
    script = """
import backend.app.services as services
first = services.MedicalService
assert "MedicalService" in services.__dict__
second = services.MedicalService
assert first is second
print("T4_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "T4_PASS" in result.stdout


def test_T5_all_contract_exact_sequence() -> None:
    expected = _EXPECTED_ALL
    script = f"""
import backend.app.services as services
assert list(services.__all__) == {expected!r}
print("T5_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "T5_PASS" in result.stdout


def test_T6_unknown_attribute_raises_AttributeError() -> None:
    script = """
import backend.app.services as services
try:
    _ = services.DefinitelyNotARealExport_XYZ
except AttributeError as exc:
    assert "DefinitelyNotARealExport_XYZ" in str(exc)
    print("T6_PASS")
else:
    raise AssertionError("expected AttributeError")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "T6_PASS" in result.stdout


def test_T7_dir_includes_all_lazy_exports() -> None:
    expected = _EXPECTED_ALL
    script = f"""
import backend.app.services as services
names = dir(services)
missing = [n for n in {expected!r} if n not in names]
assert not missing, missing
print("T7_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "T7_PASS" in result.stdout


def test_T8_models_import_does_not_require_live_db_connect() -> None:
    """Models import must complete with Engine.connect patched to refuse."""
    script = """
import importlib

def _refuse(*a, **k):
    raise RuntimeError("SENTINEL_DB_CONNECT_ATTEMPTED")

import sqlalchemy.engine.base as seb
seb.Engine.connect = _refuse
try:
    import psycopg2
    psycopg2.connect = _refuse
except Exception:
    pass

importlib.import_module("backend.app.models")
print("T8_PASS")
"""
    result = _run_inline(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "T8_PASS" in result.stdout
    assert "SENTINEL_DB_CONNECT_ATTEMPTED" not in result.stdout
