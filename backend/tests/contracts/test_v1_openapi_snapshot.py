from pathlib import Path

from backend.tests.contracts._openapi_snapshot_util import canonical_openapi_string


SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "openapi_v1_snapshot.json"


def test_v1_openapi_snapshot_matches() -> None:
    """
    Guardrail for V1 API freeze.

    To regenerate snapshot intentionally:
    PYTHONPATH=. python -m backend.tests.contracts._openapi_snapshot_util --write
    """
    current = canonical_openapi_string()
    expected = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert current == expected, "OpenAPI changed. If intentional, regenerate snapshot."
