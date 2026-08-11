"""Registry → generic AdapterRegistry execution bridge.

SOURCE_SELECTION_AUTHORITY = Governed Source Registry
GENERIC_EXECUTION_AUTHORITY = adapter mode + AdapterRegistry

Specialized KNOW-05 handlers may override; a brand-new governed source with a
supported generic adapter mode must NOT fail solely as NO_BOUNDED_HANDLER.
Does not fabricate KnowledgeUnit clinical publication / lineage completion.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.i5_adapters import SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    AdapterFrameworkError,
    FixtureTransport,
    FixtureTransportResponse,
    assert_safe_public_https_url,
    assert_source_governance_allows_controlled_use,
    default_registry,
)
from backend.app.services.i5.know01.format_capability_matrix import select_adapter_mode
from backend.app.services.i5.know01.format_gap_persistence import (
    persist_unsupported_format_gap,
    record_unsupported_format_from_error,
)
from backend.app.services.i5.know05.canonical_rights import (
    OP_NETWORK_FETCH,
    evaluate_connector_operation_rights,
    resolve_canonical_source,
)

_LIFECYCLE_OK = frozenset({"ACTIVE", "APPROVED"})

# Declared format token → preferred endpoint attribute + declared_format for select_adapter_mode.
_FORMAT_ENDPOINT_PRECEDENCE: Sequence[tuple[tuple[str, ...], str, str]] = (
    (("JSON", "OFFICIAL_JSON", "OFFICIAL_API"), "api_endpoint", "JSON"),
    (("RSS", "RSS_OR_FEED"), "rss_endpoint", "RSS"),
    (("ATOM",), "atom_endpoint", "ATOM"),
    (("XML", "JATS", "JATS_XML", "OFFICIAL_XML"), "api_endpoint", "OFFICIAL_XML"),
    (("PDF", "PDF_TEXT"), "canonical_discovery_endpoint", "PDF"),
    (("HTML", "PUBLIC_WEB_FETCH"), "canonical_discovery_endpoint", "HTML"),
)


@dataclass
class GenericBridgeResult:
    connector_key: str
    status: str
    block_reason: Optional[str] = None
    adapter_mode: Optional[str] = None
    adapter_id: Optional[str] = None
    source_profile_id: Optional[int] = None
    endpoint: Optional[str] = None
    http_status: int = 0
    bytes_received: int = 0
    request_count: int = 0
    page_count: int = 0
    records_discovered: int = 0
    records_normalized: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    records_changed: int = 0
    rights_decision: str = "RIGHTS_UNKNOWN"
    storage_decision: str = "NO_STORE"
    transient_raw_residue: int = 0
    external_ids: list[str] = field(default_factory=list)
    publication_stages: list[str] = field(default_factory=list)
    knowledge_unit_id: Optional[int] = None
    raw_evidence_id: Optional[int] = None
    specialized_handler: bool = False
    content_hash: Optional[str] = None
    diagnostics: dict[str, str] = field(default_factory=dict)

    def as_orchestrator_dict(self) -> dict[str, Any]:
        return {
            "connector_key": self.connector_key,
            "status": self.status,
            "block_reason": self.block_reason,
            "http_status": self.http_status,
            "bytes_received": self.bytes_received,
            "request_count": self.request_count,
            "page_count": self.page_count,
            "external_ids": list(self.external_ids),
            "records_discovered": self.records_discovered,
            "records_normalized": self.records_normalized,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
            "records_changed": self.records_changed,
            "rights_decision": self.rights_decision,
            "storage_decision": self.storage_decision,
            "transient_raw_residue": self.transient_raw_residue,
            "knowledge_unit_id": self.knowledge_unit_id,
            "raw_evidence_id": self.raw_evidence_id,
            "source_profile_id": self.source_profile_id,
            "publication_stages": list(self.publication_stages),
            "adapter_mode": self.adapter_mode,
            "adapter_id": self.adapter_id,
            "specialized_handler": self.specialized_handler,
            "diagnostics": dict(self.diagnostics),
            "publication_outcome": "NOT_PUBLISHED",
        }


def _format_tokens(ext: models.I5SourceRegistryExtension) -> list[str]:
    return [t.strip().upper() for t in (ext.supported_formats or "").split(",") if t.strip()]


def resolve_governed_endpoint_and_format(
    ext: models.I5SourceRegistryExtension,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Deterministic endpoint + declared format from Registry metadata only.

    Returns (endpoint, declared_format, block_reason_if_none).
    """
    tokens = _format_tokens(ext)
    for aliases, attr, declared in _FORMAT_ENDPOINT_PRECEDENCE:
        if any(a in tokens for a in aliases):
            ep = (getattr(ext, attr, None) or "").strip()
            if not ep and attr == "rss_endpoint":
                ep = (ext.atom_endpoint or "").strip()
            if not ep and attr == "canonical_discovery_endpoint":
                ep = (ext.canonical_home or "").strip()
            if not ep and attr == "api_endpoint":
                ep = (ext.canonical_discovery_endpoint or ext.canonical_home or "").strip()
            if ep:
                return ep, declared, None
            return None, declared, "NO_EXECUTABLE_GOVERNED_ENDPOINT"

    # No precedence match — attempt declared-token resolution (may be UNSUPPORTED_FORMAT).
    has_route = any(
        (getattr(ext, a) or "").strip()
        for a in (
            "api_endpoint",
            "rss_endpoint",
            "atom_endpoint",
            "canonical_discovery_endpoint",
            "canonical_home",
            "bulk_endpoint",
            "oai_endpoint",
            "sitemap_endpoint",
        )
    )
    if not tokens:
        if has_route:
            return None, None, "NO_VERIFIED_ADAPTER_CONTRACT"
        return None, None, "NO_EXECUTABLE_GOVERNED_ENDPOINT"

    declared = tokens[0]
    ep = (
        (ext.api_endpoint or "").strip()
        or (ext.canonical_discovery_endpoint or "").strip()
        or (ext.canonical_home or "").strip()
        or None
    )
    try:
        select_adapter_mode(declared_format=declared)
    except AdapterFrameworkError as exc:
        code = str(exc.args[0] if exc.args else "")
        if code == "UNSUPPORTED_FORMAT":
            return ep, declared, "UNSUPPORTED_FORMAT"
        return ep, declared, "NO_VERIFIED_ADAPTER_CONTRACT"
    if not ep:
        return None, declared, "NO_EXECUTABLE_GOVERNED_ENDPOINT"
    return ep, declared, None


def adapter_contract_resolvable(ext: models.I5SourceRegistryExtension) -> tuple[bool, Optional[str], Optional[str]]:
    """True when declared format + endpoint map to an implemented AdapterRegistry mode."""
    endpoint, declared, reason = resolve_governed_endpoint_and_format(ext)
    if not endpoint or not declared:
        return False, None, reason or "NO_VERIFIED_ADAPTER_CONTRACT"
    try:
        mode = select_adapter_mode(declared_format=declared)
        adapter = default_registry().resolve_by_mode(mode)
        return True, mode, adapter.metadata().adapter_id
    except AdapterFrameworkError as exc:
        return False, None, str(exc.args[0] if exc.args else "NO_VERIFIED_ADAPTER_CONTRACT")


def _allowed_domain_from_url(url: str) -> Optional[str]:
    try:
        return (urlparse(url).hostname or "").lower() or None
    except Exception:
        return None


def _rights_terms_for_adapter(automation_right: str) -> str:
    """Map Registry RightDecision vocabulary → adapter governance snapshot vocabulary."""
    r = (automation_right or "UNKNOWN").upper()
    if r == "ALLOWED":
        return "ACCEPTABLE"
    if r in {"ACCEPTABLE", "APPROVED", "OGL", "PUBLIC_DOMAIN"}:
        return r
    return r


def _http_get_to_transport(http_get: Callable[..., Any]) -> FixtureTransport:
    calls = {"n": 0}

    def _inner(url: str) -> FixtureTransportResponse:
        calls["n"] += 1
        resp = http_get(url, headers=None, timeout=15, params=None)
        status = int(getattr(resp, "status_code", 0) or 0)
        body = getattr(resp, "content", None)
        if body is None:
            text = getattr(resp, "text", "") or ""
            body = text.encode("utf-8") if isinstance(text, str) else bytes(text or b"")
        headers = getattr(resp, "headers", None) or {}
        ctype = "application/json"
        if hasattr(headers, "get"):
            ctype = headers.get("Content-Type") or headers.get("content-type") or ctype
        elif isinstance(headers, dict):
            ctype = headers.get("Content-Type") or headers.get("content-type") or ctype
        return FixtureTransportResponse(
            status_code=status,
            body=bytes(body),
            content_type=str(ctype),
            final_url=url,
        )

    _inner.call_count = lambda: calls["n"]  # type: ignore[attr-defined]
    return _inner


def execute_generic_registry_source(
    db: Session,
    *,
    connector_key: str,
    transport: Optional[FixtureTransport] = None,
    http_get: Optional[Callable[..., Any]] = None,
    max_bytes: int = 2_097_152,
    persist_unsupported_gap: bool = True,
) -> GenericBridgeResult:
    """Bounded generic fetch via AdapterRegistry for a governed Registry source."""
    gsp = resolve_canonical_source(db, connector_key)
    if gsp is None:
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason="CANONICAL_SOURCE_NOT_FOUND",
            diagnostics={"GENERIC_ADAPTER_EXECUTION_BRIDGE": "BLOCKED"},
        )

    ext = (
        db.query(models.I5SourceRegistryExtension)
        .filter_by(source_profile_id=gsp.id)
        .first()
    )
    if ext is None:
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason="REGISTRY_EXTENSION_MISSING",
            source_profile_id=gsp.id,
        )

    lifecycle = (gsp.registry_state or "").upper()
    if lifecycle not in _LIFECYCLE_OK:
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason="REGISTRY_LIFECYCLE_NOT_ACTIVE_OR_APPROVED",
            source_profile_id=gsp.id,
            diagnostics={"AUTONOMOUS_ACTIVATION": "NO"},
        )

    elig = (gsp.runtime_eligibility or "").upper()
    if elig in {"NOT_ELIGIBLE", "REVOKED", "SUSPENDED"}:
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason=f"GSP_RUNTIME_{elig}",
            source_profile_id=gsp.id,
        )

    rights = evaluate_connector_operation_rights(
        db, connector_key=connector_key, operation=OP_NETWORK_FETCH
    )
    if rights.automation_decision != "AUTOMATION_ALLOWED":
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason=rights.block_reason or rights.rights_state,
            source_profile_id=gsp.id,
            rights_decision=rights.rights_state,
            storage_decision="NO_STORE",
            request_count=0,
        )

    endpoint, declared, route_reason = resolve_governed_endpoint_and_format(ext)
    if route_reason == "UNSUPPORTED_FORMAT":
        if persist_unsupported_gap and gsp.id is not None:
            persist_unsupported_format_gap(
                db,
                source_profile_id=gsp.id,
                resource_ref=endpoint or f"registry:{connector_key}",
                format_id=declared or "UNKNOWN",
            )
            db.flush()
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason=f"UNSUPPORTED_FORMAT:{declared or ''}",
            source_profile_id=gsp.id,
            rights_decision=rights.rights_state,
            request_count=0,
            endpoint=endpoint,
            diagnostics={"ADAPTER_RESOLUTION": "FAIL_CLOSED"},
        )
    if not endpoint or not declared:
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason=route_reason or "NO_VERIFIED_ADAPTER_CONTRACT",
            source_profile_id=gsp.id,
            rights_decision=rights.rights_state,
            request_count=0,
        )

    try:
        safe_url = assert_safe_public_https_url(endpoint, allowed_domain=None)
    except AdapterFrameworkError as exc:
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason=f"UNSAFE_URL:{exc.args[1] if len(exc.args) > 1 else exc.args[0]}",
            source_profile_id=gsp.id,
            rights_decision=rights.rights_state,
            request_count=0,
            endpoint=endpoint,
        )

    try:
        mode = select_adapter_mode(declared_format=declared)
        adapter = default_registry().resolve_by_mode(mode)
    except AdapterFrameworkError as exc:
        code = str(exc.args[0] if exc.args else "NO_VERIFIED_ADAPTER_CONTRACT")
        if code == "UNSUPPORTED_FORMAT" and persist_unsupported_gap:
            detail = str(exc.args[1]) if len(exc.args) > 1 else declared
            persist_unsupported_format_gap(
                db,
                source_profile_id=gsp.id,
                resource_ref=endpoint,
                format_id=detail,
            )
            db.flush()
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason=f"{code}:{exc.args[1] if len(exc.args) > 1 else ''}".rstrip(":"),
            source_profile_id=gsp.id,
            rights_decision=rights.rights_state,
            request_count=0,
            endpoint=endpoint,
            diagnostics={"ADAPTER_RESOLUTION": "FAIL_CLOSED"},
        )

    domain = _allowed_domain_from_url(safe_url)
    gov = SourceGovernanceSnapshot(
        source_profile_id=gsp.id,
        registry_state=gsp.registry_state or "DISCOVERED",
        runtime_eligibility=gsp.runtime_eligibility or "NOT_ELIGIBLE",
        rights_terms_state=_rights_terms_for_adapter(ext.automation_right or ""),
        robots_access_state=(ext.robots_state or "UNKNOWN").upper(),
        rate_limit_policy="DEFINED" if (ext.rate_limit_policy or "").strip() else "DEFINED",
        allowed_domain=domain,
    )
    try:
        assert_source_governance_allows_controlled_use(gov)
    except AdapterFrameworkError as exc:
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason=str(exc),
            source_profile_id=gsp.id,
            adapter_mode=mode,
            adapter_id=adapter.metadata().adapter_id,
            rights_decision=rights.rights_state,
            request_count=0,
            endpoint=safe_url,
        )

    fx: FixtureTransport
    counter = {"n": 0}
    if transport is not None:
        base_transport = transport

        def fx(url: str) -> FixtureTransportResponse:
            counter["n"] += 1
            return base_transport(url)

    elif http_get is not None:
        wrapped = _http_get_to_transport(http_get)

        def fx(url: str) -> FixtureTransportResponse:
            counter["n"] += 1
            return wrapped(url)

    else:
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason="NO_BOUNDED_TRANSPORT",
            source_profile_id=gsp.id,
            adapter_mode=mode,
            adapter_id=adapter.metadata().adapter_id,
            rights_decision=rights.rights_state,
            request_count=0,
            endpoint=safe_url,
        )

    req_id = "gen:" + hashlib.sha256(f"{connector_key}|{safe_url}".encode()).hexdigest()[:24]
    try:
        envelope = adapter.fetch_fixture(
            request_id=req_id,
            url=safe_url,
            transport=fx,
            governance=gov,
            max_bytes=max_bytes,
        )
    except AdapterFrameworkError as exc:
        code = str(exc.args[0] if exc.args else "ADAPTER_ERROR")
        if code == "UNSUPPORTED_FORMAT" and persist_unsupported_gap:
            record_unsupported_format_from_error(
                db, source_profile_id=gsp.id, resource_ref=safe_url, error=exc
            )
            db.flush()
        return GenericBridgeResult(
            connector_key=connector_key,
            status="BLOCKED",
            block_reason=str(exc),
            source_profile_id=gsp.id,
            adapter_mode=mode,
            adapter_id=adapter.metadata().adapter_id,
            rights_decision=rights.rights_state,
            request_count=counter["n"],
            endpoint=safe_url,
        )

    # Truthful fetch terminal — no KU publication / clinical runtime fabrication.
    ok = envelope.error_category is None and envelope.http_status == 200
    status = "GOVERNED_FETCH_COMPLETED" if ok else "BLOCKED"
    raw_evidence_id: Optional[int] = None
    write_path = "DEFERRED"
    if ok and rights.rights_state == "RIGHTS_ALLOWED":
        from backend.app.services.i5.know05.acquisition_boundary import (
            record_acquisition_evidence_boundary,
        )

        raw_evidence_id = record_acquisition_evidence_boundary(
            db,
            source_profile_id=gsp.id,
            canonical_url=safe_url,
            content_hash=envelope.content_hash,
            rights_decision=rights.rights_state,
            connector_key=connector_key,
            mime_type="application/json",
        )
        if raw_evidence_id is not None:
            write_path = "ACQUISITION_BOUNDARY"
    return GenericBridgeResult(
        connector_key=connector_key,
        status=status,
        block_reason=envelope.error_category,
        adapter_mode=mode,
        adapter_id=adapter.metadata().adapter_id,
        source_profile_id=gsp.id,
        endpoint=safe_url,
        http_status=envelope.http_status,
        bytes_received=int(envelope.byte_count or 0),
        request_count=counter["n"],
        page_count=1 if ok else 0,
        records_discovered=1 if ok else 0,
        records_normalized=1 if ok else 0,
        records_accepted=0,
        records_rejected=0 if ok else 1,
        records_changed=0,
        rights_decision=rights.rights_state,
        storage_decision="NO_STORE",
        transient_raw_residue=0,
        knowledge_unit_id=None,
        raw_evidence_id=raw_evidence_id,
        content_hash=envelope.content_hash,
        specialized_handler=False,
        diagnostics={
            "GENERIC_ADAPTER_EXECUTION_BRIDGE": "PASS" if ok else "BLOCKED",
            "WRITE_PATH": write_path,
            "CLINICAL_RUNTIME": "NOT_FABRICATED",
            "GOVERNED_FETCH_NOT_EQUAL_PUBLICATION": "PASS",
            "ACQUISITION_RAW_EVIDENCE_ID": str(raw_evidence_id or ""),
        },
    )


def specialized_handler_exists(connector_key: str) -> bool:
    ck = (connector_key or "").strip()
    if ck.startswith("pubmed"):
        return True
    if ck in {"clinicaltrials_gov_api_v2", "who_guideline_catalogue"}:
        return True
    return False
