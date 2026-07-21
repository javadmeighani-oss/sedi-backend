"""Section 15-I5-B2-P1-L1 — controlled legacy companion seed tests (authored; not executed)."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typing import Optional

from backend.app.models import GovernedSourceProfile, GovernedSourceProfileVersion, KnowledgeSource
from backend.app.services.governance.contracts import (
    AutomationStatus,
    AuthorityTier,
    ClinicalJurisdictionScope,
    FreshnessStatus,
    LicenseStatus,
    PermissionDecision,
    SourceClass,
    SourceOperationalStatus,
    VerificationMethod,
)
from backend.app.services.governance import kb_b2_legacy_companion_seed as p1l1
from backend.app.services.governance.kb_b2_legacy_companion_seed import (
    DEFAULT_OPERATIONAL_STATUS,
    EligibilityClass,
    GATE3H_CATALOG_SOURCE_KEYS,
    LegacyCompanionSeedCandidate,
    LegacyCompanionSeedError,
    OPERATOR_CONFIRM_TOKEN,
    SeedDecision,
    _find_forbidden_imports,
    apply_plan,
    assert_module_security_boundaries,
    build_plan,
    catalog_inventory_candidates,
    compute_plan_digest,
    deterministic_canonical_key,
    deterministic_seed_operation_key,
    evaluate_candidate,
)
from backend.app.services.governance.kb_b2_source_profile_persistence import (
    SourceProfilePersistenceError,
)


def _pg_only(db) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _require_postgres(db) -> None:
    if not _pg_only(db):
        pytest.skip("PostgreSQL required for this invariant (CI-gated)")


def _full_evidence(**overrides):
    base = {
        "publisher_authority_identity": "NHS England",
        "source_class": SourceClass.KNOWLEDGE_DOCUMENT.value,
        "authority_evidence_tier": AuthorityTier.OFFICIAL_NATIONAL.value,
        "jurisdiction_scope": ClinicalJurisdictionScope.COUNTRY.value,
        "jurisdiction_country_code": "GB",
        "jurisdiction_subdivision_code": None,
        "jurisdiction_organization_id": None,
        "primary_language": "en",
        "specialty_domain": "sleep",
        "license_status": LicenseStatus.EXPLICIT_GRANT.value,
        "permitted_use_restriction": "ogl_v3_attribution_required",
        "storage_permission": PermissionDecision.ALLOW_EXPLICIT.value,
        "transformation_permission": PermissionDecision.DENY_EXPLICIT.value,
        "display_redistribution_permission": PermissionDecision.ALLOW_EXPLICIT.value,
        "automation_status": AutomationStatus.DISABLED.value,
        "verification_method": VerificationMethod.HUMAN_REVIEWED_DOCUMENT.value,
        "freshness_policy_days": 7,
        "freshness_status": FreshnessStatus.UNKNOWN_AGE.value,
        "fetch_policy": "manual_upload_only",
        "iran_first_applicable": False,
        "policy_version_reference": "p1-l1-policy-v1",
        "configuration_version_reference": "p1-l1-cfg-v1",
        "effective_at": datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


def _eligible(
    source_key: str = "nhs_uk_live_well",
    *,
    legacy_id: Optional[int] = None,
    locator: Optional[str] = "https://www.nhs.uk/live-well/sleep-and-tiredness/",
    **evidence_overrides,
) -> LegacyCompanionSeedCandidate:
    return LegacyCompanionSeedCandidate(
        source_key=source_key,
        display_name=source_key,
        locator_kind="url" if locator else None,
        locator=locator,
        legacy_knowledge_source_id=legacy_id,
        governance_evidence=_full_evidence(**evidence_overrides),
    )


# ---------------------------------------------------------------------------
# Planning / eligibility / determinism
# ---------------------------------------------------------------------------


def test_empty_inventory_plan() -> None:
    plan = build_plan(None, (), dry_run=True)
    assert plan.total_scanned == 0
    assert plan.plan_digest == compute_plan_digest(())
    assert plan.would_create == 0


def test_catalog_inventory_all_ineligible_without_evidence() -> None:
    candidates = catalog_inventory_candidates()
    assert len(candidates) == len(GATE3H_CATALOG_SOURCE_KEYS)
    plan = build_plan(None, candidates, dry_run=True)
    assert plan.total_scanned == len(GATE3H_CATALOG_SOURCE_KEYS)
    assert plan.would_create == 0
    assert plan.ineligible + plan.blocked == plan.total_scanned
    for d in plan.decisions:
        assert d.proposed_operational_status == DEFAULT_OPERATIONAL_STATUS
        assert d.decision in (SeedDecision.INELIGIBLE, SeedDecision.BLOCKED)


def test_eligible_candidate_would_create() -> None:
    d = evaluate_candidate(None, _eligible())
    assert d.eligibility == EligibilityClass.ELIGIBLE_WITH_EXISTING_EVIDENCE
    assert d.decision == SeedDecision.WOULD_CREATE
    assert d.proposed_fingerprint
    assert d.proposed_operational_status == SourceOperationalStatus.DISABLED.value


@pytest.mark.parametrize(
    "drop_field",
    [
        "license_status",
        "jurisdiction_scope",
        "authority_evidence_tier",
        "publisher_authority_identity",
    ],
)
def test_missing_required_evidence_fail_closed(drop_field: str) -> None:
    raw = _full_evidence()
    del raw[drop_field]
    c = LegacyCompanionSeedCandidate(
        source_key="nhs_uk_live_well",
        display_name="nhs",
        governance_evidence=raw,
    )
    d = evaluate_candidate(None, c)
    assert d.decision == SeedDecision.INELIGIBLE
    assert drop_field in d.missing_evidence


def test_missing_trust_proxy_is_authority_tier() -> None:
    """Trust is represented by authority_evidence_tier in P1 evidence."""
    raw = _full_evidence()
    del raw["authority_evidence_tier"]
    c = LegacyCompanionSeedCandidate(
        source_key="x", display_name="x", governance_evidence=raw
    )
    d = evaluate_candidate(None, c)
    assert "authority_evidence_tier" in d.missing_evidence


def test_invalid_locator_typed_error() -> None:
    c = _eligible(locator="https://user:pass@evil.example/")
    d = evaluate_candidate(None, c)
    assert d.decision == SeedDecision.ERROR
    assert "credential" in d.reason or "locator" in d.reason


def test_deterministic_candidate_ordering_and_digest() -> None:
    a = _eligible("zzz_source", locator="https://zzz.example/")
    b = _eligible("aaa_source", locator="https://aaa.example/")
    plan1 = build_plan(None, (a, b), dry_run=True)
    plan2 = build_plan(None, (b, a), dry_run=True)
    assert plan1.plan_digest == plan2.plan_digest
    assert [d.legacy_identifier for d in plan1.decisions] == [
        d.legacy_identifier for d in plan2.decisions
    ]


def test_deterministic_canonical_and_seed_keys() -> None:
    k1 = deterministic_canonical_key("nhs_uk_live_well")
    k2 = deterministic_canonical_key("  NHS_UK_LIVE_WELL  ")
    assert k1 == k2
    fp = "a" * 64
    s1 = deterministic_seed_operation_key(
        canonical_key=k1, legacy_knowledge_source_id=1, fingerprint=fp
    )
    s2 = deterministic_seed_operation_key(
        canonical_key=k1, legacy_knowledge_source_id=1, fingerprint=fp
    )
    assert s1 == s2


def test_product_legal_hold_blocked() -> None:
    c = LegacyCompanionSeedCandidate(
        source_key="nice_org_uk_public",
        display_name="nice",
        governance_evidence=_full_evidence(),
        product_legal_hold=True,
    )
    d = evaluate_candidate(None, c)
    assert d.decision == SeedDecision.BLOCKED
    assert d.eligibility == EligibilityClass.BLOCKED_REQUIRES_PRODUCT_OR_LEGAL_DECISION


def test_dry_run_plan_zero_write_contract() -> None:
    plan = build_plan(None, (_eligible(),), dry_run=True)
    assert plan.dry_run is True
    assert plan.would_create == 1


def test_apply_authorization_gates(db) -> None:
    plan = build_plan(db, (_eligible(),), dry_run=True)
    with pytest.raises(LegacyCompanionSeedError, match="apply_requires_target_environment"):
        apply_plan(
            db,
            (_eligible(),),
            dry_run=False,
            target_environment="",
            candidate_allowlist=["nhs_uk_live_well"],
            expected_plan_digest=plan.plan_digest,
            operator_confirmation=OPERATOR_CONFIRM_TOKEN,
        )
    with pytest.raises(LegacyCompanionSeedError, match="apply_requires_operator_confirmation"):
        apply_plan(
            db,
            (_eligible(),),
            dry_run=False,
            target_environment="ci",
            candidate_allowlist=["nhs_uk_live_well"],
            expected_plan_digest=plan.plan_digest,
            operator_confirmation="NO",
        )


def test_dry_run_apply_report_zero_writes(db) -> None:
    before = db.query(GovernedSourceProfile).count()
    report = apply_plan(db, (_eligible(),), dry_run=True)
    assert report.applied is False
    assert "dry_run_zero_writes" in report.notes
    assert db.query(GovernedSourceProfile).count() == before


def test_apply_requires_digest_match(db) -> None:
    c = _eligible()
    plan = build_plan(db, (c,), dry_run=True)
    with pytest.raises(LegacyCompanionSeedError, match="apply_plan_digest_mismatch"):
        apply_plan(
            db,
            (c,),
            dry_run=False,
            target_environment="ci",
            candidate_allowlist=["nhs_uk_live_well"],
            expected_plan_digest="0" * 64,
            operator_confirmation=OPERATOR_CONFIRM_TOKEN,
        )
    assert plan.would_create == 1


# ---------------------------------------------------------------------------
# PostgreSQL apply / conflicts / idempotency
# ---------------------------------------------------------------------------


def test_postgres_first_apply_creates_disabled_profile(db) -> None:
    _require_postgres(db)
    ks = KnowledgeSource(slug="p1l1-nhs-sleep", name="NHS Sleep", category="sleep")
    db.add(ks)
    db.flush()
    c = _eligible(legacy_id=ks.id)
    plan = build_plan(db, (c,), dry_run=True)
    report = apply_plan(
        db,
        (c,),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["nhs_uk_live_well"],
        expected_plan_digest=plan.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.commit()
    assert report.applied is True
    assert "nhs_uk_live_well" in report.committed
    profile = (
        db.query(GovernedSourceProfile)
        .filter(GovernedSourceProfile.canonical_key == plan.decisions[0].canonical_key)
        .one()
    )
    assert profile.operational_status == SourceOperationalStatus.DISABLED.value
    assert profile.legacy_knowledge_source_id == ks.id
    assert profile.current_profile_version_id is not None
    versions = (
        db.query(GovernedSourceProfileVersion)
        .filter(GovernedSourceProfileVersion.profile_id == profile.id)
        .count()
    )
    assert versions == 1


def test_postgres_identical_repeat_is_noop(db) -> None:
    _require_postgres(db)
    ks = KnowledgeSource(slug="p1l1-nhs-repeat", name="NHS Repeat", category="sleep")
    db.add(ks)
    db.flush()
    c = _eligible(source_key="nhs_repeat", legacy_id=ks.id, locator="https://www.nhs.uk/live-well/sleep/")
    plan1 = build_plan(db, (c,), dry_run=True)
    apply_plan(
        db,
        (c,),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["nhs_repeat"],
        expected_plan_digest=plan1.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.commit()
    plan2 = build_plan(db, (c,), dry_run=True)
    assert plan2.already_present == 1
    assert plan2.would_create == 0
    before = db.query(GovernedSourceProfileVersion).count()
    report = apply_plan(
        db,
        (c,),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["nhs_repeat"],
        expected_plan_digest=plan2.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.commit()
    assert report.committed == ("nhs_repeat",)
    assert db.query(GovernedSourceProfileVersion).count() == before


def test_postgres_changed_evidence_blocked(db) -> None:
    _require_postgres(db)
    ks = KnowledgeSource(slug="p1l1-nhs-change", name="NHS Change", category="sleep")
    db.add(ks)
    db.flush()
    c1 = _eligible(source_key="nhs_change", legacy_id=ks.id, locator="https://www.nhs.uk/live-well/a/")
    plan1 = build_plan(db, (c1,), dry_run=True)
    apply_plan(
        db,
        (c1,),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["nhs_change"],
        expected_plan_digest=plan1.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.commit()
    c2 = _eligible(
        source_key="nhs_change",
        legacy_id=ks.id,
        locator="https://www.nhs.uk/live-well/a/",
        specialty_domain="exercise",
    )
    d = evaluate_candidate(db, c2)
    assert d.decision == SeedDecision.BLOCKED
    assert d.reason == "block_requires_separate_approval"


def test_postgres_canonical_key_conflict_fail_closed(db) -> None:
    _require_postgres(db)
    ks1 = KnowledgeSource(slug="p1l1-c1", name="C1", category="other")
    ks2 = KnowledgeSource(slug="p1l1-c2", name="C2", category="other")
    db.add_all([ks1, ks2])
    db.flush()
    c1 = _eligible(source_key="conflict_key", legacy_id=ks1.id, locator="https://a.example/")
    plan1 = build_plan(db, (c1,), dry_run=True)
    apply_plan(
        db,
        (c1,),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["conflict_key"],
        expected_plan_digest=plan1.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.commit()
    c2 = _eligible(source_key="conflict_key", legacy_id=ks2.id, locator="https://b.example/")
    d = evaluate_candidate(db, c2)
    assert d.decision == SeedDecision.CONFLICTED
    assert "canonical_key_identity_conflict" in d.conflicts


def test_postgres_locator_conflict_fail_closed(db) -> None:
    _require_postgres(db)
    ks1 = KnowledgeSource(slug="p1l1-l1", name="L1", category="other")
    ks2 = KnowledgeSource(slug="p1l1-l2", name="L2", category="other")
    db.add_all([ks1, ks2])
    db.flush()
    url = "https://shared-locator.example/path"
    c1 = _eligible(source_key="loc_a", legacy_id=ks1.id, locator=url)
    plan1 = build_plan(db, (c1,), dry_run=True)
    apply_plan(
        db,
        (c1,),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["loc_a"],
        expected_plan_digest=plan1.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.commit()
    c2 = _eligible(source_key="loc_b", legacy_id=ks2.id, locator=url)
    d = evaluate_candidate(db, c2)
    assert d.decision == SeedDecision.CONFLICTED
    assert "locator_identity_conflict" in d.conflicts


def test_postgres_legacy_linkage_conflict(db) -> None:
    _require_postgres(db)
    ks = KnowledgeSource(slug="p1l1-leg", name="Leg", category="other")
    db.add(ks)
    db.flush()
    c1 = _eligible(source_key="leg_a", legacy_id=ks.id, locator="https://leg-a.example/")
    plan1 = build_plan(db, (c1,), dry_run=True)
    apply_plan(
        db,
        (c1,),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["leg_a"],
        expected_plan_digest=plan1.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.commit()
    c2 = _eligible(source_key="leg_b", legacy_id=ks.id, locator="https://leg-b.example/")
    d = evaluate_candidate(db, c2)
    assert d.decision == SeedDecision.CONFLICTED
    assert "legacy_knowledge_source_conflict" in d.conflicts


def test_postgres_batch_failure_reporting(db) -> None:
    _require_postgres(db)
    ks = KnowledgeSource(slug="p1l1-batch", name="Batch", category="other")
    db.add(ks)
    db.flush()
    good = _eligible(source_key="batch_ok", legacy_id=ks.id, locator="https://batch-ok.example/")
    bad = _eligible(
        source_key="batch_bad",
        legacy_id=999999,
        locator="https://batch-bad.example/",
    )
    # bad legacy id missing → conflicted in plan; apply skips non-create decisions
    plan = build_plan(db, (good, bad), dry_run=True)
    assert plan.conflicted >= 1
    report = apply_plan(
        db,
        (good, bad),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["batch_ok", "batch_bad"],
        expected_plan_digest=plan.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.commit()
    assert "batch_ok" in report.committed
    assert "batch_bad" not in report.committed


def test_postgres_transaction_rollback_leaves_clean(db) -> None:
    _require_postgres(db)
    before_p = db.query(GovernedSourceProfile).count()
    before_v = db.query(GovernedSourceProfileVersion).count()
    c = _eligible(source_key="rollback_case", locator="https://rollback.example/")
    plan = build_plan(db, (c,), dry_run=True)
    apply_plan(
        db,
        (c,),
        dry_run=False,
        target_environment="ci",
        candidate_allowlist=["rollback_case"],
        expected_plan_digest=plan.plan_digest,
        operator_confirmation=OPERATOR_CONFIRM_TOKEN,
    )
    db.rollback()
    assert db.query(GovernedSourceProfile).count() == before_p
    assert db.query(GovernedSourceProfileVersion).count() == before_v


# ---------------------------------------------------------------------------
# Static boundaries
# ---------------------------------------------------------------------------


def test_module_security_boundaries() -> None:
    """Real P1-L1 module must pass AST security scan despite forbidden-policy string constants."""
    source = Path(inspect.getsourcefile(p1l1) or "").read_text(encoding="utf-8")
    assert_module_security_boundaries(source)
    assert _find_forbidden_imports(source) == ()
    # Policy constants may contain marker strings; they are not real imports.
    assert '"urllib.request"' in source or "'urllib.request'" in source
    assert "import urllib.request" not in source
    assert "PublicationRelease" not in {
        n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)
    }


@pytest.mark.parametrize(
    ("snippet", "expected_fragment"),
    [
        ("import urllib.request\n", "urllib.request"),
        ("import urllib.request as request_client\n", "urllib.request"),
        ("from urllib import request\n", "urllib.request"),
        ("from urllib.request import urlopen\n", "urllib.request"),
        ("import urllib.request.helpers\n", "urllib.request.helpers"),
        ("import httpx\n", "httpx"),
        ("import apscheduler\n", "apscheduler"),
        (
            "from apscheduler.schedulers.background import BackgroundScheduler\n",
            "BackgroundScheduler",
        ),
    ],
)
def test_security_rejects_forbidden_imports(snippet: str, expected_fragment: str) -> None:
    with pytest.raises(LegacyCompanionSeedError) as excinfo:
        assert_module_security_boundaries(snippet)
    assert excinfo.value.reason.startswith("forbidden_import_present:")
    assert expected_fragment in excinfo.value.reason


def test_security_safe_literal_is_not_treated_as_import() -> None:
    source = '''
POLICY = ("urllib.request", "httpx", "requests")
# comment mentions urllib.request and apscheduler
msg = "forbidden_import_present:urllib.request"
def describe() -> str:
    """Docstring may cite urllib.request without importing it."""
    return msg
'''
    assert_module_security_boundaries(source)
    assert _find_forbidden_imports(source) == ()


def test_security_parse_failure_fail_closed() -> None:
    with pytest.raises(LegacyCompanionSeedError) as excinfo:
        assert_module_security_boundaries("def broken(:\n  pass\n")
    assert excinfo.value.reason == "security_boundary_parse_failed"


@pytest.mark.parametrize(
    "snippet",
    [
        '__import__("urllib.request")\n',
        'import importlib\nimportlib.import_module("urllib.request")\n',
        'from importlib import import_module\nimport_module("httpx")\n',
        'name = "urllib.request"\n__import__(name)\n',
    ],
)
def test_security_rejects_dynamic_imports(snippet: str) -> None:
    with pytest.raises(LegacyCompanionSeedError) as excinfo:
        assert_module_security_boundaries(snippet)
    assert excinfo.value.reason.startswith("forbidden_import_present:")


def test_security_rejects_side_effect_symbols() -> None:
    with pytest.raises(LegacyCompanionSeedError) as excinfo:
        assert_module_security_boundaries("x = PublicationRelease\n")
    assert excinfo.value.reason == "forbidden_side_effect:PublicationRelease"
    with pytest.raises(LegacyCompanionSeedError) as excinfo2:
        assert_module_security_boundaries("fetch_source(1)\n")
    assert excinfo2.value.reason == "forbidden_side_effect:fetch_source"


def test_no_startup_or_scheduler_registration() -> None:
    source = Path(inspect.getsourcefile(p1l1) or "").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # no bare register_job / add_job at module level beyond functions
            pass
    assert "register_job" not in source
    assert "add_job" not in source
    assert "on_event" not in source


def test_entry_point_defaults_dry_run() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "seed_i5b2_p1_l1_legacy_companions.py"
    )
    text = script.read_text(encoding="utf-8")
    assert "default=True" in text
    assert "--apply" in text
    assert "if __name__" in text
    # No seed execution at import beyond argparse helpers.
    assert "SessionFactory()" not in text.split("def main")[0]


def test_workflow_includes_p1_l1_path_exactly_once() -> None:
    wf = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "ci-backend-tests.yml"
    ).read_text(encoding="utf-8")
    needle = "backend/tests/test_section15_i5b2_p1_l1_legacy_companion_seed.py"
    assert wf.count(needle) == 1
    section = wf.split("- name: Section 15 backend foundation tests", 1)[1]
    section = section.split("- name:", 1)[0]
    assert "continue-on-error" not in section
    assert "|| true" not in section


def test_apply_uses_row_lock_for_concurrency() -> None:
    source = Path(inspect.getsourcefile(p1l1) or "").read_text(encoding="utf-8")
    assert "with_for_update" in source
    assert "begin_nested" in source


def test_no_migration_seed_in_051() -> None:
    mig = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "051_i5b2_governed_source_profile.py"
    ).read_text(encoding="utf-8")
    assert "No seed" in mig
    assert "op.bulk_insert" not in mig
    assert "GovernedSourceProfile(" not in mig


def test_p1_assert_legacy_seed_still_deferred_in_p1_module() -> None:
    from backend.app.services.governance.kb_b2_source_profile_persistence import (
        assert_no_legacy_seed_in_p1,
    )

    with pytest.raises(SourceProfilePersistenceError, match="legacy_seed_deferred_to_p1_l1"):
        assert_no_legacy_seed_in_p1()
