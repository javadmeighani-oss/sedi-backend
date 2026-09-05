"""GATE=SEDI-V1-BE-S02-IMPL — Device/I9 → I4 safety infrastructure contract.

Infrastructure only: zero active clinical production rules.
Test-only synthetic EMERGENCY rule is never in the production registry.
"""

from __future__ import annotations

import ast
import inspect
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.services.intelligence.contracts import (
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.device_safety_input import (
    DeviceBindingFacts,
    I4DeviceSafetyInput,
    RAW_PACKET_KIND,
    SUPPORTED_EVIDENCE_TYPES,
    accept_device_safety_input,
    build_i4_device_safety_input,
)
from backend.app.services.intelligence.device_safety_registry import (
    ACTIVE_CLINICAL_DEVICE_RULES,
    DEVICE_REGISTRY_VERSION,
    DeviceSafetyRule,
    active_clinical_device_rule_count,
    get_active_clinical_device_rules,
)
from backend.app.services.intelligence.device_safety_risk import (
    DEVICE_RISK_LANGUAGE,
    NO_ACTIVE_MATCH_RULE_ID,
    _public_assess_rejects_rules_parameter,
    assess_device_safety_risk,
    assess_device_safety_risk_safe,
    fail_closed_device_assessment,
)
from backend.app.services.intelligence.safety_risk import (
    REGISTRY_VERSION as CHAT_REGISTRY_VERSION,
    assess_safety_risk,
)
from backend.app.services.section10.i4_escalation_provenance import (
    is_authoritative_i4_emergency_assessment,
)
import backend.app.services.intelligence.device_safety_registry as device_safety_registry
import backend.app.services.intelligence.device_safety_risk as device_safety_risk_mod


def _test_only_emergency_matches(inp: I4DeviceSafetyInput) -> bool:
    """Test-scope matcher only — never importable as production registry authority."""
    return (inp.semantic_state or "").strip().lower() == "test_force_emergency"


# Lives ONLY in test module (not production registry).
TEST_ONLY_SYNTHETIC_EMERGENCY_RULE = DeviceSafetyRule(
    rule_id="i4.device.rule.test_only.synthetic_emergency.v1",
    registry_version=DEVICE_REGISTRY_VERSION,
    evidence_type="heart_rate",
    required_unit="bpm",
    required_quality_states=frozenset({"ok", "good", "acceptable", "device_packet", "device_ingest"}),
    required_freshness_states=frozenset({"FRESH"}),
    level=RiskLevel.EMERGENCY,
    action=SafetyAction.RETURN_EMERGENCY_RESPONSE,
    domain=RiskDomain.GENERAL,
    matches=_test_only_emergency_matches,
)


def _activate_test_only_rule(monkeypatch):
    """Isolate test rule via monkeypatch — no public production rules= API."""
    monkeypatch.setattr(
        device_safety_registry, "ACTIVE_CLINICAL_DEVICE_RULES", (TEST_ONLY_SYNTHETIC_EMERGENCY_RULE,)
    )
    monkeypatch.setattr(device_safety_risk_mod, "assert_production_registry_empty", lambda: None)


def _now() -> datetime:
    return datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def _binding(
    *,
    device_id: int = 1,
    binding_id: int = 10,
    hs_id: int = 100,
    active: bool = True,
) -> DeviceBindingFacts:
    return DeviceBindingFacts(
        device_id=device_id,
        binding_id=binding_id if active else None,
        binding_health_subject_id=hs_id if active else None,
        binding_active=active,
    )


def _valid_input(**overrides) -> I4DeviceSafetyInput:
    base = dict(
        health_subject_id=100,
        evidence_type="heart_rate",
        observed_at=_now() - timedelta(minutes=5),
        source_class="DEVICE_REPORTED",
        quality_state="ok",
        device_id=1,
        binding=_binding(),
        evidence_ref="physiological_measurement:1",
        provenance_ref="device_subject_binding:10",
        unit="bpm",
        normalized_value=72.0,
        now=_now(),
    )
    base.update(overrides)
    return build_i4_device_safety_input(**base)


# ---------------------------------------------------------------------------
# Unit: contract + fail-closed matrix
# ---------------------------------------------------------------------------


def test_device_input_contract_fields():
    inp = _valid_input()
    assert inp.health_subject_id == 100
    assert inp.freshness_state == "FRESH"
    assert accept_device_safety_input(inp).ok is True


def test_active_production_rule_count_zero():
    assert active_clinical_device_rule_count() == 0
    assert ACTIVE_CLINICAL_DEVICE_RULES == ()
    assert get_active_clinical_device_rules() == ()
    assert TEST_ONLY_SYNTHETIC_EMERGENCY_RULE not in ACTIVE_CLINICAL_DEVICE_RULES


def test_valid_no_active_rule_means_none_continue_not_clinical_assertion():
    result = assess_device_safety_risk_safe(input=_valid_input())
    assert result.level is RiskLevel.NONE
    assert result.action is SafetyAction.CONTINUE
    assert result.domain is RiskDomain.NONE
    assert result.rule_id == NO_ACTIVE_MATCH_RULE_ID
    assert result.registry_version == DEVICE_REGISTRY_VERSION
    assert result.language == DEVICE_RISK_LANGUAGE
    assert is_authoritative_i4_emergency_assessment(result) is False


def test_wrong_subject_fail_closed():
    inp = _valid_input(binding=_binding(hs_id=999))
    r = assess_device_safety_risk_safe(input=inp)
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE
    assert r.level is RiskLevel.NONE


def test_unbound_device_fail_closed():
    inp = _valid_input(binding=_binding(active=False))
    r = assess_device_safety_risk_safe(input=inp)
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_revoked_binding_fail_closed():
    # Inactive binding with stale ids still present — treated as revoked/inactive.
    binding = DeviceBindingFacts(
        device_id=1,
        binding_id=10,
        binding_health_subject_id=100,
        binding_active=False,
    )
    inp = _valid_input(binding=binding)
    r = assess_device_safety_risk_safe(input=inp)
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_stale_evidence_fail_closed():
    inp = _valid_input(observed_at=_now() - timedelta(hours=48), now=_now())
    assert inp.freshness_state == "STALE"
    r = assess_device_safety_risk_safe(input=inp)
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_low_quality_fail_closed():
    r = assess_device_safety_risk_safe(input=_valid_input(quality_state="bad"))
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_missing_provenance_fail_closed():
    r = assess_device_safety_risk_safe(
        input=_valid_input(provenance_ref=None, evidence_ref="physiological_measurement:1")
    )
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_missing_timestamp_fail_closed():
    r = assess_device_safety_risk_safe(input=_valid_input(observed_at=None, now=_now()))
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_unknown_unit_fail_closed():
    r = assess_device_safety_risk_safe(input=_valid_input(unit="widgets"))
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_raw_packet_rejected():
    r = assess_device_safety_risk_safe(
        input=_valid_input(evidence_kind=RAW_PACKET_KIND, is_normalized=False)
    )
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE
    assert is_authoritative_i4_emergency_assessment(r) is False


def test_no_data_ne_normal():
    r = assess_device_safety_risk_safe(
        input=_valid_input(normalized_value=None, semantic_state="no_data")
    )
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE
    assert r.level is not RiskLevel.EMERGENCY
    # Fail-closed is NONE level with FAIL_CLOSED action — never "normal healthy"
    assert r.rule_id != "i4.rule.none.v1"


def test_inactivity_only_no_risk():
    r = assess_device_safety_risk_safe(
        input=_valid_input(normalized_value=None, semantic_state="inactivity")
    )
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE
    assert is_authoritative_i4_emergency_assessment(r) is False


def test_missing_health_subject_fail_closed():
    r = assess_device_safety_risk_safe(input=_valid_input(health_subject_id=0))
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_unsupported_evidence_fail_closed():
    r = assess_device_safety_risk_safe(input=_valid_input(evidence_type="raw_ecg_blob"))
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE


def test_device_risk_language_is_en_metadata_only():
    r = assess_device_safety_risk_safe(input=_valid_input())
    assert r.language == "en"
    assert DEVICE_RISK_LANGUAGE == "en"


def test_i9_does_not_create_risk_authority_in_modules():
    """Static: device_safety modules must not call I9 packet ingest as risk owner."""
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "intelligence"
    for name in (
        "device_safety_input.py",
        "device_safety_registry.py",
        "device_safety_risk.py",
    ):
        src = (root / name).read_text(encoding="utf-8")
        assert "ingest_device_packet" not in src
        assert "openai" not in src.lower()
        assert "retrieve_knowledge" not in src
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "llm" not in node.module.lower()
                assert "rag" not in node.module.lower()


def test_evaluator_has_no_db_session_param():
    sig = inspect.signature(assess_device_safety_risk_safe)
    assert "db" not in sig.parameters
    assert "session" not in sig.parameters


# ---------------------------------------------------------------------------
# Registry authority seam (PRE-E2E-BLOCKER-CLOSURE / FINDING_S02)
# ---------------------------------------------------------------------------


def test_public_assess_rejects_rules_parameter():
    assert _public_assess_rejects_rules_parameter() is True
    assert "rules" not in inspect.signature(assess_device_safety_risk).parameters
    assert "rules" not in inspect.signature(assess_device_safety_risk_safe).parameters


def test_test_synthetic_not_production_evidence_authority():
    assert "test_synthetic" not in SUPPORTED_EVIDENCE_TYPES
    r = assess_device_safety_risk_safe(
        input=_valid_input(
            evidence_type="test_synthetic",
            unit=None,
            normalized_value=None,
            semantic_state="test_force_emergency",
        )
    )
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE
    assert is_authoritative_i4_emergency_assessment(r) is False


def test_production_cannot_activate_test_only_rule_without_registry():
    """Production path with empty ACTIVE registry never yields test-only EMERGENCY."""
    assert active_clinical_device_rule_count() == 0
    r = assess_device_safety_risk_safe(
        input=_valid_input(semantic_state="test_force_emergency")
    )
    assert r.level is RiskLevel.NONE
    assert r.action is SafetyAction.CONTINUE
    assert r.rule_id == NO_ACTIVE_MATCH_RULE_ID
    assert is_authoritative_i4_emergency_assessment(r) is False


def test_production_registry_module_has_no_test_only_rule_symbol():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "intelligence"
    registry_src = (root / "device_safety_registry.py").read_text(encoding="utf-8")
    assert "TEST_ONLY_SYNTHETIC_EMERGENCY_RULE" not in registry_src
    assert "test_synthetic" not in registry_src
    input_src = (root / "device_safety_input.py").read_text(encoding="utf-8")
    assert '"test_synthetic"' not in input_src
    assert "rules" not in inspect.signature(assess_device_safety_risk).parameters
    assert "rules" not in inspect.signature(assess_device_safety_risk_safe).parameters


# ---------------------------------------------------------------------------
# Test-only EMERGENCY + B16 authority gate (monkeypatch isolation; no I10 redesign)
# ---------------------------------------------------------------------------


def test_test_only_emergency_rule_not_in_production():
    assert TEST_ONLY_SYNTHETIC_EMERGENCY_RULE not in get_active_clinical_device_rules()
    assert TEST_ONLY_SYNTHETIC_EMERGENCY_RULE.rule_id.startswith("i4.device.rule.test_only.")
    assert active_clinical_device_rule_count() == 0


def test_test_only_emergency_enters_b16_authority_gate(monkeypatch):
    _activate_test_only_rule(monkeypatch)
    inp = _valid_input(semantic_state="test_force_emergency")
    r = assess_device_safety_risk_safe(input=inp)
    assert r.level is RiskLevel.EMERGENCY
    assert r.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    assert r.registry_version == DEVICE_REGISTRY_VERSION
    assert is_authoritative_i4_emergency_assessment(r) is True


@pytest.mark.parametrize(
    "level,action",
    [
        (RiskLevel.HIGH, SafetyAction.RETURN_HIGH_RESPONSE),
        (RiskLevel.CAUTION, SafetyAction.CONTINUE_WITH_CONSTRAINTS),
        (RiskLevel.NONE, SafetyAction.CONTINUE),
        (RiskLevel.NONE, SafetyAction.FAIL_CLOSED_RESPONSE),
    ],
)
def test_non_emergency_cannot_enter_b16(level, action):
    from backend.app.services.intelligence.contracts import RiskAssessment

    ra = RiskAssessment(
        registry_version=DEVICE_REGISTRY_VERSION,
        level=level,
        action=action,
        domain=RiskDomain.GENERAL,
        rule_id="i4.device.rule.synthetic.non_emergency.v1",
        language="en",
    )
    assert is_authoritative_i4_emergency_assessment(ra) is False


def test_production_empty_registry_zero_device_emergencies():
    r = assess_device_safety_risk_safe(input=_valid_input())
    assert is_authoritative_i4_emergency_assessment(r) is False


# ---------------------------------------------------------------------------
# Chat I4 regression
# ---------------------------------------------------------------------------


def test_chat_i4_regression_untouched():
    assert CHAT_REGISTRY_VERSION == "sedi.safety.risk.v1"
    assert DEVICE_REGISTRY_VERSION == "sedi.safety.device.v1"
    assert CHAT_REGISTRY_VERSION != DEVICE_REGISTRY_VERSION

    none = assess_safety_risk(message="hello how are you", language="en")
    assert none.level is RiskLevel.NONE
    assert none.action is SafetyAction.CONTINUE

    emergency = assess_safety_risk(message="I have chest pain", language="en")
    assert emergency.level is RiskLevel.EMERGENCY
    assert emergency.action is SafetyAction.RETURN_EMERGENCY_RESPONSE


# ---------------------------------------------------------------------------
# PostgreSQL: accountless Mother HS + binding isolation
# ---------------------------------------------------------------------------


def _pg_url() -> str:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("SCIS_TEST_DATABASE_URL") or ""


pytestmark_pg = pytest.mark.skipif(not _pg_url(), reason="TEST_DATABASE_URL not set")


@pytest.fixture
def pg_db():
    url = _pg_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


@pytestmark_pg
def test_accountless_mother_hs_device_input_pg(pg_db, monkeypatch):
    from backend.app import models
    from backend.app.core.device_auth import hash_device_token
    from backend.app.services.i9.device_binding_service import bind_device_to_subject, get_active_binding
    from backend.app.services.i9.health_subject_service import (
        create_managed_subject_without_account,
        ensure_self_subject_for_account,
    )
    from backend.app.services.section10.i4_emergency_escalation import persist_i4_emergency_escalation

    db = pg_db
    wall = datetime.now(timezone.utc)
    son = models.User(
        name=f"Son-{uuid4().hex[:8]}",
        secret_key=f"sk-{uuid4().hex[:8]}",
        preferred_language="en",
    )
    db.add(son)
    db.flush()
    son_hs = ensure_self_subject_for_account(db, son.id, commit=False)
    mother = create_managed_subject_without_account(
        db,
        account_user_id=son.id,
        display_name="Mother",
        access_role="CAREGIVER",
        commit=False,
    )
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"
    assert son_hs.id != mother.id

    device = models.Device(
        user_id=son.id,
        device_id=f"S02Dev-{uuid4().hex[:8]}",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token(f"tok-{uuid4().hex[:8]}"),
    )
    db.add(device)
    db.flush()
    bound_at = wall - timedelta(hours=1)
    binding = bind_device_to_subject(
        db,
        device=device,
        health_subject_id=mother.id,
        bound_by_account_user_id=son.id,
        bound_at=bound_at,
        commit=False,
    )
    assert device.health_subject_id == mother.id

    measured = wall - timedelta(minutes=5)
    received = wall - timedelta(minutes=4)
    pm = models.PhysiologicalMeasurement(
        health_subject_id=mother.id,
        user_id=None,
        device_id=device.id,
        measurement_type="heart_rate",
        numeric_value=74.0,
        unit="bpm",
        measured_at=measured,
        received_at=received,
        quality_state="ok",
        idempotency_key=f"s02-{uuid4().hex}",
        ingestion_status="accepted",
    )
    db.add(pm)
    db.flush()

    active = get_active_binding(db, device.id, at_time=measured)
    assert active is not None
    assert active.health_subject_id == mother.id

    inp = build_i4_device_safety_input(
        health_subject_id=mother.id,
        evidence_type=pm.measurement_type,
        observed_at=pm.measured_at,
        received_at=pm.received_at,
        source_class="DEVICE_REPORTED",
        quality_state=pm.quality_state,
        device_id=device.id,
        binding=DeviceBindingFacts(
            device_id=device.id,
            binding_id=binding.id,
            binding_health_subject_id=active.health_subject_id,
            binding_active=True,
        ),
        evidence_ref=f"physiological_measurement:{pm.id}",
        provenance_ref=f"device_subject_binding:{binding.id}",
        unit=pm.unit,
        normalized_value=float(pm.numeric_value),
        now=wall,
    )
    result = assess_device_safety_risk_safe(input=inp)
    assert result.level is RiskLevel.NONE
    assert result.action is SafetyAction.CONTINUE
    assert result.rule_id == NO_ACTIVE_MATCH_RULE_ID
    # Son account is not patient identity for assessment
    assert inp.health_subject_id == mother.id
    assert mother.linked_user_id is None

    # Wrong subject isolation
    wrong = build_i4_device_safety_input(
        health_subject_id=son_hs.id,
        evidence_type=pm.measurement_type,
        observed_at=pm.measured_at,
        source_class="DEVICE_REPORTED",
        quality_state=pm.quality_state,
        device_id=device.id,
        binding=DeviceBindingFacts(
            device_id=device.id,
            binding_id=binding.id,
            binding_health_subject_id=mother.id,
            binding_active=True,
        ),
        evidence_ref=f"physiological_measurement:{pm.id}",
        provenance_ref=f"device_subject_binding:{binding.id}",
        unit=pm.unit,
        normalized_value=float(pm.numeric_value),
        now=wall,
    )
    wrong_r = assess_device_safety_risk_safe(input=wrong)
    assert wrong_r.action is SafetyAction.FAIL_CLOSED_RESPONSE

    # Non-emergency must not persist B16 ledger
    assert (
        persist_i4_emergency_escalation(
            db,
            authenticated_user_id=son.id,
            health_subject_id=son_hs.id,
            risk_assessment=result,
            commit=False,
        )
        is None
    )

    # Test-only EMERGENCY via monkeypatched registry (not public rules= injection)
    _activate_test_only_rule(monkeypatch)
    synth = assess_device_safety_risk_safe(
        input=build_i4_device_safety_input(
            health_subject_id=son_hs.id,
            evidence_type="heart_rate",
            observed_at=wall - timedelta(minutes=1),
            source_class="DEVICE_REPORTED",
            quality_state="ok",
            device_id=None,
            binding=DeviceBindingFacts(
                device_id=None,
                binding_id=None,
                binding_health_subject_id=None,
                binding_active=False,
            ),
            evidence_ref="test:1",
            provenance_ref="test:prov",
            unit="bpm",
            normalized_value=72.0,
            semantic_state="test_force_emergency",
            now=wall,
        )
    )
    assert is_authoritative_i4_emergency_assessment(synth) is True
    # Existing persist seam requires SELF-linked subject — prove EMERGENCY can enter for SELF HS
    persisted = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=son.id,
        health_subject_id=son_hs.id,
        risk_assessment=synth,
        commit=False,
    )
    assert persisted is not None
    assert persisted.current_state == "caregiver_escalation_ready"

    # FAIL_CLOSED must not persist
    fc = fail_closed_device_assessment()
    assert (
        persist_i4_emergency_escalation(
            db,
            authenticated_user_id=son.id,
            health_subject_id=son_hs.id,
            risk_assessment=fc,
            commit=False,
        )
        is None
    )


@pytestmark_pg
def test_revoked_binding_pg_fail_closed(pg_db):
    from backend.app import models
    from backend.app.core.device_auth import hash_device_token
    from backend.app.services.i9.device_binding_service import bind_device_to_subject, rebind_device
    from backend.app.services.i9.health_subject_service import (
        create_managed_subject_without_account,
        ensure_self_subject_for_account,
    )

    db = pg_db
    wall = datetime.now(timezone.utc)
    son = models.User(
        name=f"SonR-{uuid4().hex[:8]}",
        secret_key=f"sk-{uuid4().hex[:8]}",
        preferred_language="en",
    )
    db.add(son)
    db.flush()
    ensure_self_subject_for_account(db, son.id, commit=False)
    mother = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="MotherR", access_role="CAREGIVER", commit=False
    )
    other = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="Other", access_role="CAREGIVER", commit=False
    )
    device = models.Device(
        user_id=son.id,
        device_id=f"S02Rev-{uuid4().hex[:8]}",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token(f"tok-{uuid4().hex[:8]}"),
    )
    db.add(device)
    db.flush()
    first = bind_device_to_subject(
        db,
        device=device,
        health_subject_id=mother.id,
        bound_by_account_user_id=son.id,
        bound_at=wall - timedelta(hours=2),
        commit=False,
    )
    rebind_device(
        db,
        device=device,
        new_health_subject_id=other.id,
        bound_by_account_user_id=son.id,
        bound_at=wall - timedelta(minutes=30),
        commit=False,
    )
    db.refresh(first)
    assert first.unbound_at is not None

    inp = build_i4_device_safety_input(
        health_subject_id=mother.id,
        evidence_type="heart_rate",
        observed_at=wall - timedelta(minutes=1),
        source_class="DEVICE_REPORTED",
        quality_state="ok",
        device_id=device.id,
        binding=DeviceBindingFacts(
            device_id=device.id,
            binding_id=first.id,
            binding_health_subject_id=mother.id,
            binding_active=False,
        ),
        evidence_ref="physiological_measurement:revoked",
        provenance_ref=f"device_subject_binding:{first.id}",
        unit="bpm",
        normalized_value=70.0,
        now=wall,
    )
    r = assess_device_safety_risk_safe(input=inp)
    assert r.action is SafetyAction.FAIL_CLOSED_RESPONSE
