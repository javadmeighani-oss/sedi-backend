"""CR-04A — Multilingual semantic quality foundation (evaluation-only).

Corpus-driven regression against public seams:
  - resolve_intent(...)
  - classify_discovery_reply(...)

No DB / network / LLM. No production remediation in this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest

from backend.app.services.i6.relationship_discovery import (
    DiscoveryDisposition,
    classify_discovery_reply,
)
from backend.app.services.intelligence.contracts import IntentId, RequestKind
from backend.app.services.intelligence.intent_registry import resolve_intent

CORPUS_PATH = (
    Path(__file__).resolve().parent / "data" / "cr04a_multilingual_semantic_corpus_v1.json"
)
CORPUS_VERSION = "cr04a_multilingual_semantic_corpus_v1"

REQUIRED_CASE_KEYS = (
    "id",
    "language",
    "message",
    "discovery_target",
    "notification_origin",
    "expected_intent",
    "expected_request_kind",
    "expected_discovery_disposition",
    "memory_write_allowed",
    "operational_route_allowed",
    "severity_if_failed",
)

ALLOWED_LANGUAGES = frozenset({"en", "fa", "ar"})
ALLOWED_DISPOSITIONS = frozenset(d.value for d in DiscoveryDisposition) | {None}
ALLOWED_SEVERITIES = frozenset({"P0", "P1", "P2", "P3"})
ALLOWED_INTENTS = frozenset(i.value for i in IntentId)
ALLOWED_REQUEST_KINDS = frozenset(k.value for k in RequestKind)

PROTECTED_INTENTS = frozenset(
    {
        IntentId.HEALTH.value,
        IntentId.SYMPTOM.value,
        IntentId.MEDICATION.value,
        IntentId.VITALS.value,
        IntentId.REMINDER.value,
        IntentId.NOTIFICATION_FOLLOW_UP.value,
    }
)

NO_MEMORY_DISPOSITIONS = frozenset(
    {
        DiscoveryDisposition.SKIP.value,
        DiscoveryDisposition.AMBIGUOUS.value,
        DiscoveryDisposition.UNRELATED.value,
        DiscoveryDisposition.UNSUPPORTED.value,
        DiscoveryDisposition.NO_MARKER.value,
    }
)


def _load_corpus() -> dict[str, Any]:
    raw = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError("corpus root must be an object")
    return raw


def _cases() -> list[dict[str, Any]]:
    corpus = _load_corpus()
    cases = corpus.get("cases")
    if not isinstance(cases, list) or not cases:
        raise AssertionError("corpus.cases must be a non-empty list")
    return cases


def _validate_case_schema(case: dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_CASE_KEYS if k not in case]
    assert not missing, f"{case.get('id', '<unknown>')}: missing keys {missing}"

    cid = case["id"]
    assert isinstance(cid, str) and cid.strip(), "id must be non-empty string"
    assert case["language"] in ALLOWED_LANGUAGES, f"{cid}: invalid language"
    assert isinstance(case["message"], str) and case["message"].strip(), (
        f"{cid}: message required"
    )
    target = case["discovery_target"]
    assert target is None or (isinstance(target, str) and target.strip()), (
        f"{cid}: discovery_target must be null or non-empty string"
    )
    assert isinstance(case["notification_origin"], bool), (
        f"{cid}: notification_origin must be bool"
    )
    assert case["expected_intent"] in ALLOWED_INTENTS, f"{cid}: invalid expected_intent"
    assert case["expected_request_kind"] in ALLOWED_REQUEST_KINDS, (
        f"{cid}: invalid expected_request_kind"
    )
    disp = case["expected_discovery_disposition"]
    assert disp in ALLOWED_DISPOSITIONS, f"{cid}: invalid expected_discovery_disposition"
    if target is None:
        assert disp is None, f"{cid}: disposition must be null when no discovery_target"
    else:
        assert disp is not None, f"{cid}: disposition required when discovery_target set"
    assert isinstance(case["memory_write_allowed"], bool), (
        f"{cid}: memory_write_allowed must be bool"
    )
    assert isinstance(case["operational_route_allowed"], bool), (
        f"{cid}: operational_route_allowed must be bool"
    )
    assert case["severity_if_failed"] in ALLOWED_SEVERITIES, (
        f"{cid}: invalid severity_if_failed"
    )


def _operational_route_allowed(intent: str, request_kind: str) -> bool:
    """REMINDER / PERSONALIZED_PLAN remain eligible for operational routing."""
    if intent == IntentId.REMINDER.value:
        return True
    if request_kind == RequestKind.PERSONALIZED_PLAN.value:
        return True
    if request_kind == RequestKind.ACTION.value and intent == IntentId.REMINDER.value:
        return True
    return False


def _memory_write_allowed(
    disposition: Optional[str], *, has_normalized_value: bool
) -> bool:
    """Pure discovery ANSWER with normalized value may bind; never fabricate otherwise."""
    if disposition != DiscoveryDisposition.ANSWER.value:
        return False
    return has_normalized_value


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    return _load_corpus()


def test_cr04a_corpus_schema(corpus: dict[str, Any]) -> None:
    assert corpus.get("corpus_version") == CORPUS_VERSION
    cases = corpus["cases"]
    assert 60 <= len(cases) <= 90, f"expected 60–90 cases, got {len(cases)}"

    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"

    for case in cases:
        _validate_case_schema(case)

    by_lang = {"en": 0, "fa": 0, "ar": 0}
    for case in cases:
        by_lang[case["language"]] += 1
    # Balanced across languages — not exhaustive, but no language may dominate.
    for lang, count in by_lang.items():
        assert count >= 15, f"{lang} under-represented ({count})"
        assert count <= 40, f"{lang} over-represented ({count})"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_cr04a_semantic_contract(case: dict[str, Any]) -> None:
    _validate_case_schema(case)
    cid = case["id"]
    language = case["language"]
    message = case["message"]
    target = case["discovery_target"]
    notification_origin = bool(case["notification_origin"])

    disposition: Optional[str] = None
    has_normalized = False
    if target is not None:
        clf = classify_discovery_reply(target, message, language)
        disposition = clf.disposition.value
        has_normalized = clf.normalized_value is not None
        assert disposition == case["expected_discovery_disposition"], (
            f"{cid}: disposition {disposition!r} != "
            f"{case['expected_discovery_disposition']!r}"
        )
    else:
        assert case["expected_discovery_disposition"] is None

    result = resolve_intent(
        message=message,
        language=language,
        has_verified_notification_origin=notification_origin,
        relationship_discovery_disposition=disposition,
    )

    assert result.intent_id.value == case["expected_intent"], (
        f"{cid}: intent {result.intent_id.value!r} != {case['expected_intent']!r}"
    )
    assert result.request_kind.value == case["expected_request_kind"], (
        f"{cid}: request_kind {result.request_kind.value!r} != "
        f"{case['expected_request_kind']!r}"
    )

    mem_allowed = _memory_write_allowed(disposition, has_normalized_value=has_normalized)
    assert mem_allowed is case["memory_write_allowed"], (
        f"{cid}: memory_write_allowed derived={mem_allowed} "
        f"expected={case['memory_write_allowed']}"
    )

    op_allowed = _operational_route_allowed(
        result.intent_id.value, result.request_kind.value
    )
    assert op_allowed is case["operational_route_allowed"], (
        f"{cid}: operational_route_allowed derived={op_allowed} "
        f"expected={case['operational_route_allowed']}"
    )

    # --- Semantic contract invariants (evaluation-only) ---

    # Notification origin remains authoritative.
    if notification_origin:
        assert result.intent_id is IntentId.NOTIFICATION_FOLLOW_UP, (
            f"{cid}: NOTIFICATION_ORIGIN_CONTRACT broken"
        )
        assert result.request_kind is RequestKind.FOLLOW_UP, (
            f"{cid}: NOTIFICATION_ORIGIN_CONTRACT request_kind"
        )

    # Ambiguous / skip / reject / unrelated must never fabricate memory truth.
    if disposition in NO_MEMORY_DISPOSITIONS:
        assert mem_allowed is False, f"{cid}: DISCOVERY_MEMORY_CONTRACT fabricate"

    # Current user request > discovery: UNRELATED never binds discovery memory.
    if disposition == DiscoveryDisposition.UNRELATED.value:
        assert mem_allowed is False, f"{cid}: CURRENT_NEED_CONTRACT memory"
        # Discovery must not rewrite to discovery-reply when unrelated.
        assert result.intent_id.value == case["expected_intent"]

    # Protected intent must not be swallowed by discovery ANSWER/SKIP.
    if (
        disposition in (DiscoveryDisposition.ANSWER.value, DiscoveryDisposition.SKIP.value)
        and case["expected_intent"] in PROTECTED_INTENTS
    ):
        assert result.intent_id.value == case["expected_intent"], (
            f"{cid}: PROTECTED_INTENT_CONTRACT swallowed"
        )

    # REMINDER / PERSONALIZED_PLAN may remain eligible for operational routing.
    if case["operational_route_allowed"]:
        assert op_allowed is True, f"{cid}: OPERATIONAL_ROUTING_CONTRACT"
