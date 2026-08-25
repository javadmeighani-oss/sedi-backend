"""Bounds tests for governed I8 proactive flag activation ops path."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "db03" / "db_prod_i8_flag_remote.sh"
WF = ROOT.parent / ".github" / "workflows" / "db-prod-i8-flag.yml"


def test_i8_flag_ops_script_bounds():
    body = SCRIPT.read_text(encoding="utf-8")
    assert "SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED" in body
    assert "070_i8_proactive_evaluation_ledger" in body
    assert "ACTIVATE" in body
    assert "OBSERVE" in body
    assert "KILL_SWITCH" in body
    assert "alembic upgrade" not in body.lower()
    assert "SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED=1" not in body
    assert "SEDI_I5_" not in body
    assert "SEDI_I7_" not in body
    assert "unsafe_synthetic_action" in body
    assert "smart_notification_bypass" in body


def test_i8_flag_workflow_bounds():
    body = WF.read_text(encoding="utf-8")
    assert "workflow_dispatch" in body
    assert "source_sha" in body
    assert "ref: ${{ github.event.inputs.source_sha }}" in body
    assert "I8_FLAG_PREFLIGHT_ONLY" in body
    assert "I8_FLAG_ACTIVATE_ON" in body
    assert "I8_FLAG_OBSERVE_BOUNDED" in body
    assert "I8_FLAG_KILL_SWITCH_OFF" in body
    assert "db_prod_i8_flag_remote.sh" in body
    assert "sedi-production-backend-operation" in body
    assert "alembic upgrade" not in body.lower()
    assert "run: alembic" not in body.lower()
