"""Static governance guards for PD-I8-04D production 068→069→070 ops path."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "db03" / "db_prod_i8_068_to_070_remote.sh"
WORKFLOW = ROOT.parent / ".github" / "workflows" / "db-prod-i8-068-070.yml"


def test_ops_script_bounds():
    body = SCRIPT.read_text(encoding="utf-8")
    assert "068_i7_wave2_governed_memory_lifecycle" in body
    assert "069_i8_operational_plan_state_foundation" in body
    assert "070_i8_proactive_evaluation_ledger" in body
    assert "SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED" in body
    assert "sedi_migration_admin" in body
    assert "PHASE=PREFLIGHT" in body or 'PREFLIGHT)' in body
    assert "BACKUP" in body and "APPLY" in body
    assert "writers_frozen" in body
    assert "restore_backend" in body
    assert "alembic upgrade head" not in body.lower()
    assert "downgrade" not in body.lower() or 's "downgrade" "NO"' in body
    # no flag activation
    assert "SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED=1" not in body
    assert "SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED=true" not in body.lower()


def test_workflow_bounds():
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch" in body
    assert "source_sha" in body
    assert "ref: ${{ github.event.inputs.source_sha }}" in body
    assert "I8_068_070_PREFLIGHT_ONLY" in body
    assert "I8_068_070_BACKUP_AT_068" in body
    assert "I8_068_070_APPLY_069_THEN_070" in body
    assert "db_prod_i8_068_to_070_remote.sh" in body
    assert "deploy-backend" not in body.lower()
    assert "run: alembic upgrade head" not in body.lower()
    assert "python -m alembic" not in body.lower()
