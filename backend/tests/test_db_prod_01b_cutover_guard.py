"""DB-PROD-01B — cutover-only script must never contain migration apply commands."""

from pathlib import Path


def test_cutover_script_has_no_migration_apply():
    path = Path(__file__).resolve().parents[1] / "ops" / "db03" / "db_prod_01b_cutover.sh"
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "cutover_only" in lowered
    assert "sedi_app_runtime" in text
    assert "alembic upgrade" not in lowered
    assert "upgrade head" not in lowered
    assert "python -m alembic" not in lowered
