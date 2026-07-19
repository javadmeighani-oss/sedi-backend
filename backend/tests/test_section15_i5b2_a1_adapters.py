"""Pure tests for Section 15-I5-B2-A1 / Fix2–Fix3 boundary adapters (authored; not executed)."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from backend.app.services.governance.contracts import (
    GovernanceAction,
    PublicationState,
    ReviewStatus,
    SourceOperationalStatus,
)
from backend.app.services.governance.kb_lifecycle_mapping import (
    PolicyCheckpoint,
    map_legacy_publication_state,
    map_legacy_review_status,
    map_legacy_source_operational_status,
    policy_checkpoint_spec,
)
from backend.app.services.governance import kb_b2_adapters as a1
from backend.app.services.governance.kb_b2_adapters import (
    LegacyToTypedConversionError,
    ScheduledAuthorizationInputs,
    assert_checkpoint_evidence_or_raise,
    build_prefetch_evidence_categories,
    build_prepublish_evidence_categories,
    build_scheduled_authorization_request,
    convert_automation_inputs,
    convert_publication_state,
    convert_review_status,
    convert_source_operational_status,
    derive_document_version_dedup_key,
    derive_fetch_run_idempotency_key,
    derive_policy_decision_idempotency_key,
    derive_provenance_evidence_fingerprint,
    derive_publication_release_evidence_fingerprint,
    derive_source_version_composition_key,
)


# ---------------------------------------------------------------------------
# Typed rejection (no passthrough, no synthetic tuples)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ctx",
    [
        dict(
            source_fetch_enabled=True,
            governed_profile_present=True,
            governed_profile_verified=True,
        ),
        dict(
            source_fetch_enabled=False,
            governed_profile_present=False,
            governed_profile_verified=False,
        ),
    ],
)
def test_convert_source_rejects_typed_enum(ctx: dict) -> None:
    with pytest.raises(
        LegacyToTypedConversionError,
        match="^typed_source_operational_status_not_accepted$",
    ) as exc_info:
        convert_source_operational_status(
            SourceOperationalStatus.ENABLED_IDLE,
            **ctx,
        )
    assert "ENABLED_IDLE" not in str(exc_info.value)
    assert "enabled_idle" not in str(exc_info.value)


@pytest.mark.parametrize("published_at_present", [True, False])
def test_convert_publication_rejects_typed_enum(published_at_present: bool) -> None:
    with pytest.raises(
        LegacyToTypedConversionError,
        match="^typed_publication_state_not_accepted$",
    ) as exc_info:
        convert_publication_state(
            PublicationState.PUBLISHED,
            published_at_present=published_at_present,
        )
    assert "PUBLISHED" not in str(exc_info.value)
    assert "published" not in str(exc_info.value)


def test_convert_review_rejects_typed_enum() -> None:
    with pytest.raises(
        LegacyToTypedConversionError,
        match="^typed_review_status_not_accepted$",
    ) as exc_info:
        convert_review_status(ReviewStatus.APPROVED)
    assert "APPROVED" not in str(exc_info.value)
    assert "approved" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Raw source parity + missing operands
# ---------------------------------------------------------------------------


def test_convert_source_active_missing_profile_matches_b1() -> None:
    a1_result = convert_source_operational_status(
        "active",
        source_fetch_enabled=True,
        governed_profile_present=False,
        governed_profile_verified=True,
    )
    b1_result = map_legacy_source_operational_status(
        legacy_ingestion_status="active",
        source_fetch_enabled=True,
        governed_profile_present=False,
        governed_profile_verified=True,
    )
    assert a1_result == b1_result
    assert a1_result[0] is SourceOperationalStatus.DISABLED


def test_convert_source_active_unverified_profile_matches_b1() -> None:
    a1_result = convert_source_operational_status(
        "active",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=False,
    )
    b1_result = map_legacy_source_operational_status(
        legacy_ingestion_status="active",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=False,
    )
    assert a1_result == b1_result
    assert a1_result[0] is SourceOperationalStatus.DISABLED


def test_convert_source_active_fetch_disabled_matches_b1() -> None:
    a1_result = convert_source_operational_status(
        "active",
        source_fetch_enabled=False,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    b1_result = map_legacy_source_operational_status(
        legacy_ingestion_status="active",
        source_fetch_enabled=False,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    assert a1_result == b1_result


def test_convert_source_active_valid_profile_matches_b1() -> None:
    a1_result = convert_source_operational_status(
        "active",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    b1_result = map_legacy_source_operational_status(
        legacy_ingestion_status="active",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    assert a1_result == b1_result
    assert a1_result == (SourceOperationalStatus.ENABLED_IDLE, (), False, False)


def test_convert_source_draft_and_deprecated_match_b1() -> None:
    assert convert_source_operational_status(
        "draft",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    ) == map_legacy_source_operational_status(
        legacy_ingestion_status="draft",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    assert convert_source_operational_status(
        "deprecated",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    ) == map_legacy_source_operational_status(
        legacy_ingestion_status="deprecated",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    )


def test_convert_source_paused_unknown_matches_b1() -> None:
    a1_result = convert_source_operational_status(
        "paused",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    b1_result = map_legacy_source_operational_status(
        legacy_ingestion_status="paused",
        source_fetch_enabled=True,
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    assert a1_result == b1_result


@pytest.mark.parametrize("bad", [1, True, object()])
def test_convert_source_rejects_invalid_raw_type(bad: object) -> None:
    with pytest.raises(LegacyToTypedConversionError):
        convert_source_operational_status(
            bad,
            source_fetch_enabled=True,
            governed_profile_present=True,
            governed_profile_verified=True,
        )


def test_convert_source_missing_operands_package_error() -> None:
    with pytest.raises(
        LegacyToTypedConversionError, match="^source_fetch_enabled_required$"
    ):
        convert_source_operational_status(
            "active",
            governed_profile_present=True,
            governed_profile_verified=True,
        )
    with pytest.raises(
        LegacyToTypedConversionError, match="^governed_profile_present_required$"
    ):
        convert_source_operational_status(
            "active",
            source_fetch_enabled=True,
            governed_profile_verified=True,
        )
    with pytest.raises(
        LegacyToTypedConversionError, match="^governed_profile_verified_required$"
    ):
        convert_source_operational_status(
            "active",
            source_fetch_enabled=True,
            governed_profile_present=True,
        )


def test_convert_source_non_bool_context_rejected() -> None:
    with pytest.raises(LegacyToTypedConversionError, match="must_be_bool"):
        convert_source_operational_status(
            "active",
            source_fetch_enabled=1,
            governed_profile_present=True,
            governed_profile_verified=True,
        )


# ---------------------------------------------------------------------------
# Raw publication / review parity
# ---------------------------------------------------------------------------


def test_convert_publication_active_with_and_without_evidence_match_b1() -> None:
    assert convert_publication_state(
        "active", published_at_present=True
    ) == map_legacy_publication_state(
        document_status="active", published_at_present=True
    )
    assert convert_publication_state(
        "active", published_at_present=False
    ) == map_legacy_publication_state(
        document_status="active", published_at_present=False
    )
    assert convert_publication_state("active", published_at_present=False)[0] is (
        PublicationState.UNPUBLISHED
    )


def test_convert_publication_draft_archived_unknown_match_b1() -> None:
    assert convert_publication_state(
        "draft", published_at_present=False
    ) == map_legacy_publication_state(
        document_status="draft", published_at_present=False
    )
    assert convert_publication_state(
        "archived", published_at_present=True
    ) == map_legacy_publication_state(
        document_status="archived", published_at_present=True
    )
    assert convert_publication_state(
        "revoked", published_at_present=True
    ) == map_legacy_publication_state(
        document_status="revoked", published_at_present=True
    )


def test_convert_publication_missing_and_invalid_operands() -> None:
    with pytest.raises(
        LegacyToTypedConversionError, match="^published_at_present_required$"
    ):
        convert_publication_state("active")
    with pytest.raises(LegacyToTypedConversionError, match="must_be_bool"):
        convert_publication_state("active", published_at_present=1)
    with pytest.raises(LegacyToTypedConversionError):
        convert_publication_state(object(), published_at_present=True)


@pytest.mark.parametrize(
    "legacy",
    ["pending_review", "approved", "rejected", "auto_approved", "quarantined", "bogus", None],
)
def test_convert_review_parity_with_b1(legacy: object) -> None:
    assert convert_review_status(legacy) == map_legacy_review_status(legacy)  # type: ignore[arg-type]


def test_convert_review_auto_approved_full_metadata() -> None:
    status, reasons, manual, fail_closed, auto_flag = convert_review_status(
        "auto_approved"
    )
    assert status is ReviewStatus.APPROVED
    assert "LEGACY_AUTO_APPROVED_OBSERVED" in reasons
    assert manual is True and fail_closed is True and auto_flag is True


def test_convert_review_rejects_invalid_raw_type() -> None:
    with pytest.raises(LegacyToTypedConversionError):
        convert_review_status(1)


# ---------------------------------------------------------------------------
# Category-name-only builders
# ---------------------------------------------------------------------------


def _prefetch_required() -> tuple[str, ...]:
    return policy_checkpoint_spec(PolicyCheckpoint.PRE_FETCH).required_evidence_categories


def _prepublish_required() -> tuple[str, ...]:
    return policy_checkpoint_spec(
        PolicyCheckpoint.PRE_PUBLISH
    ).required_evidence_categories


def test_prefetch_complete_official_set() -> None:
    required = _prefetch_required()
    cats = build_prefetch_evidence_categories(required)
    assert cats == required
    assert_checkpoint_evidence_or_raise(PolicyCheckpoint.PRE_FETCH, cats)


def test_prefetch_arbitrary_order_whitespace_duplicates() -> None:
    required = _prefetch_required()
    shuffled = [
        f" {required[3]} ",
        required[0],
        required[2],
        required[1],
        required[3],
        required[0],
    ]
    cats = build_prefetch_evidence_categories(shuffled)
    assert cats == required


def test_prefetch_list_tuple_generator_forms() -> None:
    required = _prefetch_required()
    assert build_prefetch_evidence_categories(list(required)) == required
    assert build_prefetch_evidence_categories(tuple(required)) == required
    assert build_prefetch_evidence_categories(c for c in required) == required


def test_prepublish_complete_and_order() -> None:
    required = _prepublish_required()
    reversed_input = list(reversed(required)) + [required[0]]
    cats = build_prepublish_evidence_categories(reversed_input)
    assert cats == required
    assert_checkpoint_evidence_or_raise(PolicyCheckpoint.PRE_PUBLISH, cats)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "source_profile_version",
        (),
        [],
        True,
        False,
        1,
        0,
        1.5,
        b"x",
        {"source_profile_version": True},
        object(),
    ],
)
def test_prefetch_rejects_invalid_containers(bad: object) -> None:
    with pytest.raises(LegacyToTypedConversionError):
        build_prefetch_evidence_categories(bad)  # type: ignore[arg-type]


class _CategoryKeyMapping(Mapping[str, bool]):
    """Minimal test-only Mapping whose keys are valid category names."""

    def __init__(self, keys: tuple[str, ...]) -> None:
        self._data = {key: True for key in keys}

    def __getitem__(self, key: str) -> bool:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


@pytest.mark.parametrize(
    "builder,required_fn",
    [
        (build_prefetch_evidence_categories, _prefetch_required),
        (build_prepublish_evidence_categories, _prepublish_required),
    ],
)
def test_builders_reject_all_mapping_containers(
    builder: Any, required_fn: Any
) -> None:
    required = required_fn()
    as_dict = {name: True for name in required}
    as_proxy = MappingProxyType(as_dict)
    as_custom = _CategoryKeyMapping(required)

    for container in (as_dict, as_proxy, as_custom):
        with pytest.raises(
            LegacyToTypedConversionError,
            match="^invalid_checkpoint_evidence_categories_container$",
        ) as exc_info:
            builder(container)
        message = str(exc_info.value)
        assert "source_profile_version" not in message
        assert "human_approved_review_state" not in message
        for name in required:
            assert name not in message


@pytest.mark.parametrize(
    "builder,required_fn",
    [
        (build_prefetch_evidence_categories, _prefetch_required),
        (build_prepublish_evidence_categories, _prepublish_required),
    ],
)
def test_builders_preserve_list_tuple_generator(
    builder: Any, required_fn: Any
) -> None:
    required = required_fn()
    assert builder(list(required)) == required
    assert builder(tuple(required)) == required
    assert builder(c for c in required) == required
    assert required == (
        policy_checkpoint_spec(
            PolicyCheckpoint.PRE_FETCH
            if builder is build_prefetch_evidence_categories
            else PolicyCheckpoint.PRE_PUBLISH
        ).required_evidence_categories
    )


def test_prefetch_rejects_missing_one_required() -> None:
    required = _prefetch_required()
    incomplete = required[:-1]
    with pytest.raises(
        LegacyToTypedConversionError,
        match="checkpoint_evidence_categories_incomplete",
    ):
        build_prefetch_evidence_categories(incomplete)


def test_prefetch_rejects_unknown_category_without_leaking_name() -> None:
    required = _prefetch_required()
    with pytest.raises(
        LegacyToTypedConversionError,
        match="^unknown_checkpoint_evidence_category$",
    ) as exc_info:
        build_prefetch_evidence_categories([*required, "not_a_real_category"])
    assert "not_a_real_category" not in str(exc_info.value)


def test_prefetch_rejects_blank_and_invalid_items() -> None:
    required = _prefetch_required()
    with pytest.raises(LegacyToTypedConversionError):
        build_prefetch_evidence_categories([*required[:-1], ""])
    with pytest.raises(LegacyToTypedConversionError):
        build_prefetch_evidence_categories([*required[:-1], "   "])
    with pytest.raises(LegacyToTypedConversionError):
        build_prefetch_evidence_categories([*required[:-1], True])
    with pytest.raises(LegacyToTypedConversionError):
        build_prefetch_evidence_categories([*required[:-1], 1])


def test_prepublish_rejects_incomplete_and_unknown() -> None:
    required = _prepublish_required()
    with pytest.raises(LegacyToTypedConversionError):
        build_prepublish_evidence_categories(required[:-1])
    with pytest.raises(
        LegacyToTypedConversionError,
        match="^unknown_checkpoint_evidence_category$",
    ):
        build_prepublish_evidence_categories([*required, "extra_category"])


def test_duplicate_cannot_compensate_for_missing_category() -> None:
    required = _prefetch_required()
    # Duplicate first category; omit last.
    bad = [required[0], required[0], *required[1:-1]]
    with pytest.raises(
        LegacyToTypedConversionError,
        match="checkpoint_evidence_categories_incomplete",
    ):
        build_prefetch_evidence_categories(bad)


def test_builders_no_longer_expose_per_category_value_kwargs() -> None:
    prefetch_sig = inspect.signature(build_prefetch_evidence_categories)
    prepublish_sig = inspect.signature(build_prepublish_evidence_categories)
    assert list(prefetch_sig.parameters) == ["provided_evidence_categories"]
    assert list(prepublish_sig.parameters) == ["provided_evidence_categories"]
    forbidden = {
        "source_profile_version",
        "license_policy",
        "jurisdiction_policy",
        "fetch_policy",
        "human_approved_review_state",
        "exact_immutable_version_evidence",
        "fresh_policy_evaluation_at_approval",
        "publication_release_evidence",
        "evidence_reference",
        "evidence_value",
    }
    assert forbidden.isdisjoint(prefetch_sig.parameters)
    assert forbidden.isdisjoint(prepublish_sig.parameters)


# ---------------------------------------------------------------------------
# Six-way scheduled authorization
# ---------------------------------------------------------------------------


def _valid_six_way(**overrides: object) -> ScheduledAuthorizationInputs:
    base = dict(
        i5_schedule_flag_enabled=True,
        legacy_kb_schedule_flag_enabled=True,
        global_scheduler_enabled=True,
        source_fetch_enabled=True,
        governed_profile_automation_permitted=True,
        source_operational_status="active",
        governed_profile_present=True,
        governed_profile_verified=True,
    )
    base.update(overrides)
    return convert_automation_inputs(**base)  # type: ignore[arg-type]


def test_six_way_raw_status_via_b1() -> None:
    req = _valid_six_way()
    assert req.source_operational_status is SourceOperationalStatus.ENABLED_IDLE


def test_six_way_typed_status_direct_without_converter() -> None:
    req = convert_automation_inputs(
        i5_schedule_flag_enabled=True,
        legacy_kb_schedule_flag_enabled=False,
        global_scheduler_enabled=True,
        source_fetch_enabled=True,
        governed_profile_automation_permitted=True,
        source_operational_status=SourceOperationalStatus.ENABLED_IDLE,
    )
    assert req.legacy_kb_schedule_flag_enabled is False
    assert req.source_operational_status is SourceOperationalStatus.ENABLED_IDLE


@pytest.mark.parametrize(
    "field",
    [
        "i5_schedule_flag_enabled",
        "legacy_kb_schedule_flag_enabled",
        "global_scheduler_enabled",
        "source_fetch_enabled",
        "governed_profile_automation_permitted",
    ],
)
def test_six_way_each_bool_false_preserved(field: str) -> None:
    req = _valid_six_way(**{field: False})
    assert getattr(req, field) is False


def test_six_way_all_bools_false() -> None:
    req = _valid_six_way(
        i5_schedule_flag_enabled=False,
        legacy_kb_schedule_flag_enabled=False,
        global_scheduler_enabled=False,
        source_fetch_enabled=False,
        governed_profile_automation_permitted=False,
    )
    assert req.i5_schedule_flag_enabled is False
    assert req.source_fetch_enabled is False


def test_six_way_non_fetch_eligible_and_invalid_raw_status() -> None:
    assert (
        _valid_six_way(governed_profile_present=False).source_operational_status
        is SourceOperationalStatus.DISABLED
    )
    assert (
        _valid_six_way(source_operational_status="unknown").source_operational_status
        is SourceOperationalStatus.DISABLED
    )


def test_six_way_bool_strictness_and_missing() -> None:
    with pytest.raises(LegacyToTypedConversionError):
        _valid_six_way(i5_schedule_flag_enabled=1)
    with pytest.raises(LegacyToTypedConversionError, match="_required"):
        convert_automation_inputs(
            legacy_kb_schedule_flag_enabled=True,
            global_scheduler_enabled=True,
            source_fetch_enabled=True,
            governed_profile_automation_permitted=True,
            source_operational_status="active",
            governed_profile_present=True,
            governed_profile_verified=True,
        )


def test_build_scheduled_authorization_request_typed_direct() -> None:
    req = build_scheduled_authorization_request(
        i5_schedule_flag_enabled=True,
        legacy_kb_schedule_flag_enabled=True,
        global_scheduler_enabled=True,
        source_fetch_enabled=True,
        governed_profile_automation_permitted=True,
        source_operational_status=SourceOperationalStatus.SUSPENDED,
    )
    assert req.source_operational_status is SourceOperationalStatus.SUSPENDED


# ---------------------------------------------------------------------------
# Canonical identity (unchanged)
# ---------------------------------------------------------------------------


def test_policy_decision_key_stable_and_sensitive() -> None:
    base = dict(
        ingestion_run_id="run-1",
        action=GovernanceAction.PUBLISH,
        request_fingerprint="a" * 64,
        policy_version="pv-1",
    )
    k1 = derive_policy_decision_idempotency_key(**base)
    assert k1 == derive_policy_decision_idempotency_key(**base)
    assert k1 != derive_policy_decision_idempotency_key(
        **{**base, "ingestion_run_id": "run-2"}
    )


def test_fetch_run_key_each_field_changes_independently() -> None:
    base = dict(
        source_profile_id="sp-1",
        source_profile_version_id="spv-1",
        trigger_type="scheduled",
        trigger_identity="window-2026-01",
        canonical_url="https://example.org/doc",
        policy_version="pv-1",
    )
    k0 = derive_fetch_run_idempotency_key(**base)
    assert k0 != derive_fetch_run_idempotency_key(
        **{**base, "source_profile_id": "sp-2"}
    )
    assert k0 != derive_fetch_run_idempotency_key(
        **{**base, "source_profile_version_id": "spv-2"}
    )
    assert k0 != derive_fetch_run_idempotency_key(
        **{**base, "trigger_type": "manual"}
    )
    assert k0 != derive_fetch_run_idempotency_key(
        **{**base, "trigger_identity": "window-2026-02"}
    )
    assert k0 != derive_fetch_run_idempotency_key(
        **{**base, "canonical_url": "https://example.org/other"}
    )
    assert k0 != derive_fetch_run_idempotency_key(
        **{**base, "policy_version": "pv-2"}
    )


def test_source_version_composition_key() -> None:
    k1 = derive_source_version_composition_key(
        source_profile_version_reference="spv-1",
        raw_object_reference="raw-1",
    )
    assert k1 != derive_source_version_composition_key(
        source_profile_version_reference="spv-2",
        raw_object_reference="raw-1",
    )


def _prov(**overrides: object) -> str:
    base = dict(
        governed_document_id="doc-1",
        governed_source_version_id="gsv-1",
        raw_content_id="raw-1",
        source_acquisition_id="acq-1",
        document_content_hash="content-hash",
        parser_version="p1",
        normalizer_version="n1",
        chunker_version="c1",
        producer_service_version="svc-1",
        normalization_config_fingerprint="norm-cfg",
        chunking_config_fingerprint="chunk-cfg",
    )
    base.update(overrides)
    return derive_provenance_evidence_fingerprint(**base)  # type: ignore[arg-type]


def _dedup(**overrides: object) -> str:
    base = dict(
        governed_document_id="doc-1",
        document_content_hash="content-hash",
        parser_version="p1",
        normalizer_version="n1",
        chunker_version="c1",
        normalization_config_fingerprint="norm-cfg",
        chunking_config_fingerprint="chunk-cfg",
    )
    base.update(overrides)
    return derive_document_version_dedup_key(**base)  # type: ignore[arg-type]


def test_provenance_and_dedup_separation() -> None:
    assert _prov() == _prov()
    assert _prov(source_acquisition_id="acq-1") != _prov(source_acquisition_id="acq-2")
    assert _dedup() == _dedup()
    assert "source_acquisition_id" not in inspect.signature(
        derive_document_version_dedup_key
    ).parameters


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_content_hash", "other-hash"),
        ("parser_version", "p2"),
        ("normalizer_version", "n2"),
        ("chunker_version", "c2"),
        ("normalization_config_fingerprint", "norm-2"),
        ("chunking_config_fingerprint", "chunk-2"),
    ],
)
def test_document_dedup_pipeline_sensitivity(field: str, value: str) -> None:
    assert _dedup() != _dedup(**{field: value})


def test_publication_release_evidence_fingerprint() -> None:
    when = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    base = dict(
        document_version_id="dv-1",
        human_approval_record_id="ha-1",
        human_approval_projection_version_counter=3,
        release_channel="internal",
        release_target="kb_serving",
        visibility="restricted",
        release_configuration_fingerprint="cfg-1",
        jurisdiction_snapshot_reference="jur-1",
        license_evidence_reference="lic-1",
        intended_effective_time=when,
        rollback_target_document_version_id=None,
    )
    k1 = derive_publication_release_evidence_fingerprint(**base)
    when_offset = when.astimezone(timezone(timedelta(hours=3)))
    assert k1 == derive_publication_release_evidence_fingerprint(
        **{**base, "intended_effective_time": when_offset}
    )


def test_canonicalization_bool_int_and_real_nfc() -> None:
    assert _dedup(governed_document_id="1") != _dedup(governed_document_id=1)
    cafe_nfc = "café"
    cafe_nfd = "cafe\u0301"
    assert cafe_nfc != cafe_nfd
    assert _dedup(parser_version=cafe_nfc) == _dedup(parser_version=cafe_nfd)


# ---------------------------------------------------------------------------
# Purity / surface
# ---------------------------------------------------------------------------


def test_a1_module_purity_and_no_evidence_value_contract() -> None:
    path = Path(inspect.getsourcefile(a1) or "")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            assert not node.module.startswith("backend.app.models")
            assert not node.module.startswith("backend.app.core.scheduler")
            assert not node.module.startswith("backend.app.services.gate3")
    for root in (
        "sqlalchemy",
        "fastapi",
        "alembic",
        "requests",
        "httpx",
        "os",
        "apscheduler",
    ):
        assert root not in imported
    assert "_require_evidence_reference" not in source
    assert "_evidence_present" not in source
    assert "ESTABLISHED_STRING_REFERENCE_CONTRACT_REUSED" not in source
    assert "typed_source_operational_status_not_accepted" in source
    assert "ScheduledAuthorizationInputs" not in a1.__all__
