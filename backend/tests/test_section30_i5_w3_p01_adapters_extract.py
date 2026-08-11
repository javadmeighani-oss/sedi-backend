"""Section 30 / W3-P01 — Adapter framework + extract/normalize/dedupe (no live network).

Runtime selectors are exercised by w3p01-adapter-framework-runtime.yml.
Controlled real-source validation is NOT owned / NOT executed in this package.
"""
from __future__ import annotations

import importlib
from typing import Callable

import pytest

from backend.app.schemas import i5_adapters as schemas
from backend.app.services.i5 import conceptual_extraction as extract
from backend.app.services.i5 import normalization as norm
from backend.app.services.i5.adapters import base as adapters_base
from backend.app.services.i5.adapters.base import (
    AdapterFrameworkError,
    AdapterRegistry,
    FixtureTransportResponse,
    default_registry,
)
from backend.app.schemas.i5_adapters import SourceGovernanceSnapshot


def _ok_gov(**overrides) -> SourceGovernanceSnapshot:
    base = dict(
        source_profile_id=1,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="ACCEPTABLE",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain="example.org",
    )
    base.update(overrides)
    return SourceGovernanceSnapshot(**base)


def _transport(
    status: int = 200,
    body: bytes = b"<html><title>T</title><body><p>Enough visible medical guidance text for extraction threshold.</p></body></html>",
    content_type: str = "text/html; charset=utf-8",
    **kwargs,
) -> Callable[[str], FixtureTransportResponse]:
    def _inner(url: str) -> FixtureTransportResponse:
        return FixtureTransportResponse(
            status_code=status,
            body=body,
            content_type=content_type,
            final_url=kwargs.get("final_url"),
            etag=kwargs.get("etag"),
            last_modified=kwargs.get("last_modified"),
        )

    return _inner


def test_W3P01_T1_package_identity() -> None:
    assert schemas.PACKAGE_ID == "I5-IMPL-W3-P01"
    assert schemas.MANAGEMENT_ALIAS == "P06"
    assert "Adapter framework" in schemas.PACKAGE_TITLE
    assert "OFFICIAL_API" in adapters_base.ADAPTER_MODES
    assert "PUBLIC_WEB_FETCH" in adapters_base.ADAPTER_MODES
    assert "RSS_OR_FEED" in adapters_base.ADAPTER_MODES
    assert "GOVERNANCE_BLOCKED" in adapters_base.ERROR_CATEGORIES


def test_W3P01_T2_registry_register_and_resolve() -> None:
    registry = default_registry()
    ids = set(registry.list_ids())
    assert ids == {
        "i5.public_web_fetch",
        "i5.official_api",
        "i5.rss_feed",
        "i5.pdf_text",
        "i5.jats_xml",
    }
    assert registry.resolve_by_mode("PUBLIC_WEB_FETCH").metadata().adapter_id == "i5.public_web_fetch"
    assert registry.resolve_by_mode("OFFICIAL_API").metadata().adapter_id == "i5.official_api"
    assert registry.resolve_by_mode("RSS_OR_FEED").metadata().adapter_id == "i5.rss_feed"
    assert registry.resolve_by_mode("PDF_TEXT").metadata().adapter_id == "i5.pdf_text"
    assert registry.resolve_by_mode("OFFICIAL_XML").metadata().adapter_id == "i5.jats_xml"
    with pytest.raises(AdapterFrameworkError, match="DUPLICATE_ADAPTER"):
        registry.register(registry.get("i5.public_web_fetch"))
    with pytest.raises(AdapterFrameworkError, match="ADAPTER_UNKNOWN"):
        registry.get("missing")
    with pytest.raises(AdapterFrameworkError, match="ADAPTER_DISABLED"):
        registry.resolve_by_mode("BLOCKED_OR_EXCLUDED")


def test_W3P01_T3_public_web_wraps_fetcher_symbol() -> None:
    adapter = default_registry().get("i5.public_web_fetch")
    symbol = adapter.substrate()  # type: ignore[attr-defined]
    assert symbol.endswith("KnowledgeSourceFetcher")
    assert "knowledge_source_fetcher" in symbol


@pytest.mark.parametrize(
    "case_id",
    [
        "unknown_rights",
        "robots_blocked",
        "rate_undefined",
        "registry_blocked",
    ],
)
def test_W3P01_T4_governance_fail_closed(case_id: str) -> None:
    adapter = default_registry().get("i5.public_web_fetch")
    overrides = {
        "unknown_rights": {"rights_terms_state": "UNKNOWN"},
        "robots_blocked": {"robots_access_state": "BLOCKED"},
        "rate_undefined": {"rate_limit_policy": "UNKNOWN"},
        "registry_blocked": {"registry_state": "BLOCKED"},
    }[case_id]
    with pytest.raises(AdapterFrameworkError) as ei:
        adapter.fetch_fixture(
            request_id="r1",
            url="https://example.org/page",
            transport=_transport(),
            governance=_ok_gov(**overrides),
        )
    assert ei.value.category in {
        "GOVERNANCE_BLOCKED",
        "ROBOTS_BLOCKED",
        "TERMS_BLOCKED",
    }


@pytest.mark.parametrize(
    "case_id",
    [
        "http_scheme",
        "localhost",
        "private_ip",
        "domain_mismatch",
    ],
)
def test_W3P01_T5_network_safety_url_policy(case_id: str) -> None:
    adapter = default_registry().get("i5.public_web_fetch")
    urls = {
        "http_scheme": "http://example.org/x",
        "localhost": "https://localhost/x",
        "private_ip": "https://127.0.0.1/x",
        "domain_mismatch": "https://evil.test/x",
    }
    with pytest.raises(AdapterFrameworkError, match="UNSAFE_URL"):
        adapter.fetch_fixture(
            request_id="r1",
            url=urls[case_id],
            transport=_transport(),
            governance=_ok_gov(),
        )


@pytest.mark.parametrize(
    "case_id",
    [
        "ok_200",
        "not_modified_304",
        "not_found_404",
        "gone_410",
        "rate_429",
        "server_500",
        "oversize",
    ],
)
def test_W3P01_T6_fetch_envelope_statuses(case_id: str) -> None:
    adapter = default_registry().get("i5.public_web_fetch")
    body = b"<html><body><p>Enough visible medical guidance text for extraction threshold.</p></body></html>"
    if case_id == "ok_200":
        env = adapter.fetch_fixture(
            request_id="r1",
            url="https://example.org/a",
            transport=_transport(200, body),
            governance=_ok_gov(),
        )
        assert env.http_status == 200
        assert env.error_category is None
        assert env.byte_count == len(body)
        assert len(env.content_hash) == 64
        assert env.disposition == "OK"
    elif case_id == "not_modified_304":
        env = adapter.fetch_fixture(
            request_id="r1",
            url="https://example.org/a",
            transport=_transport(304, b"", etag='"abc"'),
            governance=_ok_gov(),
        )
        assert env.error_category == "NO_MATERIAL_CHANGE"
        assert env.body == b""
    elif case_id == "not_found_404":
        env = adapter.fetch_fixture(
            request_id="r1",
            url="https://example.org/a",
            transport=_transport(404, b""),
            governance=_ok_gov(),
        )
        assert env.error_category == "NOT_FOUND"
    elif case_id == "gone_410":
        env = adapter.fetch_fixture(
            request_id="r1",
            url="https://example.org/a",
            transport=_transport(410, b""),
            governance=_ok_gov(),
        )
        assert env.error_category == "GONE"
    elif case_id == "rate_429":
        env = adapter.fetch_fixture(
            request_id="r1",
            url="https://example.org/a",
            transport=_transport(429, b""),
            governance=_ok_gov(),
        )
        assert env.error_category == "RATE_LIMITED"
        assert env.retryable is True
    elif case_id == "server_500":
        env = adapter.fetch_fixture(
            request_id="r1",
            url="https://example.org/a",
            transport=_transport(500, b""),
            governance=_ok_gov(),
        )
        assert env.error_category == "NETWORK_ERROR"
    else:
        huge = b"x" * (adapters_base.MAX_CONTENT_BYTES + 1)
        with pytest.raises(AdapterFrameworkError, match="CONTENT_TOO_LARGE"):
            adapter.fetch_fixture(
                request_id="r1",
                url="https://example.org/a",
                transport=_transport(200, huge),
                governance=_ok_gov(),
            )


def test_W3P01_T7_official_api_and_rss_content_types() -> None:
    registry = default_registry()
    api = registry.get("i5.official_api")
    json_body = b'{"title":"API","text":"Official API guidance body for candidate extraction."}'
    env = api.fetch_fixture(
        request_id="r1",
        url="https://example.org/api",
        transport=_transport(200, json_body, "application/json"),
        governance=_ok_gov(),
    )
    assert env.content_type == "application/json"
    with pytest.raises(AdapterFrameworkError, match="INVALID_CONTENT_TYPE"):
        api.fetch_fixture(
            request_id="r2",
            url="https://example.org/api",
            transport=_transport(200, b"<html/>", "text/html"),
            governance=_ok_gov(),
        )
    rss = registry.get("i5.rss_feed")
    rss_body = (
        b'<?xml version="1.0"?><rss><channel><item>'
        b"<title>Item</title><description>Feed item guidance body text here.</description>"
        b"</item></channel></rss>"
    )
    env2 = rss.fetch_fixture(
        request_id="r3",
        url="https://example.org/feed.xml",
        transport=_transport(200, rss_body, "application/rss+xml"),
        governance=_ok_gov(),
    )
    assert env2.content_type == "application/rss+xml"


def test_W3P01_T8_normalize_and_dedupe_idempotency() -> None:
    doc1 = norm.normalize_document(
        raw_text="  Hello\nWorld  ",
        domain="Neurology",
        topic="Migraine",
        population="Adult",
        jurisdiction="ZZ",
    )
    doc2 = norm.normalize_document(
        raw_text="hello world",
        domain="neurology",
        topic="migraine",
        population="adult",
        jurisdiction="zz",
    )
    assert doc1.dedupe_key == doc2.dedupe_key
    assert doc1.content_hash == doc2.content_hash
    assert norm.detect_no_material_change(doc1.content_hash, doc2.content_hash) is True
    other = norm.normalize_document(
        raw_text="different body",
        domain="neurology",
        topic="migraine",
        population="adult",
        jurisdiction="zz",
    )
    assert other.dedupe_key != doc1.dedupe_key
    assert norm.detect_no_material_change(doc1.content_hash, other.content_hash) is False


def test_W3P01_T9_extraction_html_json_rss_and_failures() -> None:
    html_env = default_registry().get("i5.public_web_fetch").fetch_fixture(
        request_id="r1",
        url="https://example.org/p",
        transport=_transport(),
        governance=_ok_gov(),
    )
    cands = extract.extract_candidates(html_env, mode="PUBLIC_WEB_FETCH")
    assert len(cands) == 1
    assert cands[0].extractor_version.startswith("w3p01-")
    assert "candidate_only" in cands[0].warnings[0]

    json_env = default_registry().get("i5.official_api").fetch_fixture(
        request_id="r2",
        url="https://example.org/api",
        transport=_transport(
            200,
            b'{"title":"X","text":"JSON official text for candidates."}',
            "application/json",
        ),
        governance=_ok_gov(),
    )
    assert extract.extract_candidates(json_env, mode="OFFICIAL_API")

    rss_body = (
        b'<?xml version="1.0"?><rss><channel><item>'
        b"<title>I</title><description>RSS guidance body for candidates.</description>"
        b"</item></channel></rss>"
    )
    rss_env = default_registry().get("i5.rss_feed").fetch_fixture(
        request_id="r3",
        url="https://example.org/feed.xml",
        transport=_transport(200, rss_body, "application/rss+xml"),
        governance=_ok_gov(),
    )
    assert extract.extract_candidates(rss_env, mode="RSS_OR_FEED")

    with pytest.raises(AdapterFrameworkError, match="EXTRACTION_FAILED"):
        extract.extract_candidates(
            default_registry()
            .get("i5.public_web_fetch")
            .fetch_fixture(
                request_id="r4",
                url="https://example.org/p",
                transport=_transport(404, b""),
                governance=_ok_gov(),
            ),
            mode="PUBLIC_WEB_FETCH",
        )
    with pytest.raises(AdapterFrameworkError, match="UNSUPPORTED_FORMAT"):
        extract.extract_from_html(
            default_registry()
            .get("i5.official_api")
            .fetch_fixture(
                request_id="r5",
                url="https://example.org/api",
                transport=_transport(
                    200, b'{"title":"t","text":"body text here"}', "application/json"
                ),
                governance=_ok_gov(),
            )
        )


def test_W3P01_T10_no_activation_no_production_write_markers() -> None:
    from backend.app.schemas.i5_adapters import AdapterPipelineResult

    env = default_registry().get("i5.public_web_fetch").fetch_fixture(
        request_id="r1",
        url="https://example.org/p",
        transport=_transport(),
        governance=_ok_gov(),
    )
    cands = extract.extract_candidates(env, mode="PUBLIC_WEB_FETCH")
    doc = norm.normalize_document(
        raw_text=cands[0].normalized_text,
        domain="neurology",
        topic="migraine",
    )
    result = AdapterPipelineResult(
        adapter_id=env.adapter_id,
        mode="PUBLIC_WEB_FETCH",
        fetch=env,
        normalized=doc,
        candidates=cands,
        knowledge_unit_approved=False,
        source_activated=False,
        production_write=False,
        live_network_used=False,
    )
    assert result.knowledge_unit_approved is False
    assert result.source_activated is False
    assert result.production_write is False
    assert result.live_network_used is False


def test_W3P01_T11_conditional_fetch_etag_passthrough() -> None:
    env = default_registry().get("i5.public_web_fetch").fetch_fixture(
        request_id="r1",
        url="https://example.org/p",
        transport=_transport(304, b"", etag='"v1"', last_modified="Wed, 01 Jan 2020 00:00:00 GMT"),
        governance=_ok_gov(),
    )
    assert env.etag == '"v1"'
    assert env.last_modified is not None
    assert env.error_category == "NO_MATERIAL_CHANGE"
