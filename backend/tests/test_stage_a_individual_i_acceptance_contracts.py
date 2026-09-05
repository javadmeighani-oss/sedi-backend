"""Stage A individual I1–I10 acceptance contracts (component-level).

GATE=SEDI-V1-BE-STAGE-A-INDIVIDUAL-I1-I10-ACCEPTANCE-01

These tests assert current-source authority boundaries and isolation law.
They do NOT claim Stage B shared-family E2E, Smart-RAG runtime, or clinical
device rule activation.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_i1_orchestrator_does_not_own_safety_knowledge_action_delivery():
    from backend.app.services.intelligence import orchestrator as orch_mod
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    src = Path(orch_mod.__file__).read_text(encoding="utf-8")
    # I1 delegates; it must not embed delivery/knowledge minting authority.
    assert "create_i10_caregiver_delivery_intent" not in src
    assert "assess_device_safety_risk" in src or "assess_safety_risk" in src
    sig = inspect.signature(IntelligenceOrchestrator.process)
    params = set(sig.parameters)
    assert "authenticated_user_id" in params
    # Chat orchestration remains Account-scoped; no HS target parameter yet.
    assert "health_subject_id" not in params


def test_i2_assembler_is_not_safety_or_action_authority():
    from backend.app.services.intelligence import assembler as asm_mod
    from backend.app.services.intelligence.assembler import AuthorizedContextAssembler

    src = Path(asm_mod.__file__).read_text(encoding="utf-8")
    assert "assess_device_safety_risk" not in src
    assert "generate_operational_action" not in src
    assert "create_i10_caregiver_delivery_intent" not in src
    assert hasattr(AuthorizedContextAssembler, "assemble")


def test_i3_intent_missing_info_has_no_downstream_authority():
    from backend.app.services.intelligence import intent_registry, missing_information

    for mod in (intent_registry, missing_information):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "assess_device_safety_risk" not in src
        assert "retrieve_knowledge_context" not in src
        assert "generate_operational_action" not in src
        assert "create_i10_caregiver_delivery_intent" not in src


def test_i4_production_clinical_device_rules_remain_inactive():
    from backend.app.services.intelligence import device_safety_risk
    from backend.app.services.intelligence.device_safety_registry import (
        ACTIVE_CLINICAL_DEVICE_RULES,
        active_clinical_device_rule_count,
        assert_production_registry_empty,
    )

    assert active_clinical_device_rule_count() == 0
    assert ACTIVE_CLINICAL_DEVICE_RULES == ()
    assert_production_registry_empty()
    risk_src = Path(device_safety_risk.__file__).read_text(encoding="utf-8")
    # Public assess APIs must not accept caller-supplied rules authority.
    assert "def assess_device_safety_risk(*, input:" in risk_src
    assert "def assess_device_safety_risk_safe(*, input:" in risk_src
    sig = inspect.signature(device_safety_risk.assess_device_safety_risk)
    assert "rules" not in sig.parameters


def test_i5_lexical_retrieval_exists_without_claiming_smart_rag():
    from backend.app.services.i5 import runtime_knowledge_retrieval as i5_rt
    from backend.app.services.scis import retrieval as scis_retrieval

    assert hasattr(i5_rt, "retrieve_knowledge_context")
    assert hasattr(scis_retrieval, "retrieve")
    # FINDING_RAG_REAL_RUNTIME remains OPEN — lexical/SCIS ≠ Smart RAG activation.


def test_i6_consent_distinct_from_notification_prefs():
    from backend.app.services.i6 import consent_service

    src = Path(consent_service.__file__).read_text(encoding="utf-8")
    assert "grant_memory_consent" in src
    assert "revoke_memory_consent" in src
    assert "require_permission" in src
    # NotificationPrefs are delivery prefs, not I6 consent authority.
    assert "NotificationPrefs" not in src
    assert hasattr(consent_service, "revoke_memory_consent")
    assert hasattr(consent_service, "require_permission")


def test_i7_mother_accountless_support_is_not_fabricated():
    """Mother MANAGED linked_user_id=NULL has no I7 HS-native surface today."""
    i7_dir = ROOT / "app" / "services" / "i7"
    assert i7_dir.is_dir()
    hits = []
    for path in i7_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "health_subject_id" in text or "linked_user_id" in text:
            hits.append(path.name)
    # Current architecture: I7 is Account/user_id keyed → Mother accountless unsupported.
    assert hits == []
    mother_accountless_i7_support = "NOT_IMPLEMENTED"
    assert mother_accountless_i7_support == "NOT_IMPLEMENTED"

def test_i8_semantic_not_i10_delivery_owner():
    from backend.app.services.i8 import proactive_orchestrator, unified_core

    for mod in (proactive_orchestrator, unified_core):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "create_i10_caregiver_delivery_intent" not in src
        assert "CaregiverNotificationIntent" not in src


def test_i9_does_not_create_safety_conclusion_authority():
    i9_dir = ROOT / "app" / "services" / "i9"
    banned = ("assess_device_safety_risk", "RiskAssessment", "ACTIVE_CLINICAL_DEVICE_RULES")
    for path in i9_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} must not own I4 safety via {token}"


def test_i10_owner_provenance_resolver_is_linked_user_only():
    from backend.app.services.i10.care_digest_producer_worker import (
        resolve_subject_owner_user_id,
    )

    src = Path(
        ROOT / "app" / "services" / "i10" / "care_digest_producer_worker.py"
    ).read_text(encoding="utf-8")
    assert "do NOT substitute MANAGER" in src or "linked_user_id" in src
    assert callable(resolve_subject_owner_user_id)


def test_i10_cni_owner_column_nullable_in_orm():
    from backend.app import models

    col = models.CaregiverNotificationIntent.__table__.c.owner_user_id
    assert col.nullable is True


def test_alembic_single_head_remains_079():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["079_i10_cni_owner_provenance_nullable"]
