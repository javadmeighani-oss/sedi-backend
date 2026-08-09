"""I5-IMPL-W6-P01 — controlled live HTTPS transport (PUBLIC_WEB path only).

Reuses Gate3 SSRF / robots primitives (`validate_fetch_url`, `validate_redirect_url`,
`check_robots_allowed`) against a transient, never-persisted `models.KnowledgeSource`
object, plus the same `USER_AGENT` / timeout / max_bytes pattern as
`KnowledgeSourceFetcher` (Gate 3G). I5 additionally enforces an HTTPS-only gate
*ahead of* Gate3 (Gate3 itself still tolerates `http://`).

This module performs no governance/activation decisions of its own — callers
(`PublicWebFetchAdapter.fetch_live`, the weekly orchestrator controlled-live
path) are responsible for the governance snapshot gate. `http_get` is
injectable so unit tests never open a real socket for the content fetch; tests
must still stub the Gate3 robots-check network call separately (it is not
routed through `http_get`), matching the existing Gate3G test pattern of
patching `backend.app.services.gate3.robots_checker.requests.get` and
`backend.app.services.gate3.fetch_security.socket.getaddrinfo`.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional, Sequence
from urllib.parse import urljoin, urlparse

import requests

from backend.app import models
from backend.app.services.gate3.fetch_security import (
    FetchSecurityError,
    validate_fetch_url,
    validate_redirect_url,
)
from backend.app.services.gate3.knowledge_source_fetcher import USER_AGENT
from backend.app.services.gate3.robots_checker import RobotsBlockedError, check_robots_allowed
from backend.app.services.i5.adapters.base import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CONTENT_BYTES,
    AdapterFrameworkError,
    FixtureTransportResponse,
    assert_safe_public_https_url,
)

HttpGet = Callable[..., Any]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _header_value(headers: Any, key: str, default: str = "") -> str:
    if headers is None:
        return default
    try:
        raw = headers.get(key, default)
    except AttributeError:
        return default
    if not isinstance(raw, str):
        return default
    return raw.strip() or default


def _response_body(resp: Any) -> bytes:
    body = getattr(resp, "content", b"")
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    if isinstance(body, str):
        return body.encode("utf-8", errors="replace")
    return b""


def _build_transient_source(
    *,
    url: str,
    allowed_domain: Optional[str],
    allowed_url_patterns: Optional[Sequence[str]],
    trust_level: str,
    review_required: bool,
    max_bytes: int,
) -> models.KnowledgeSource:
    """In-memory-only `KnowledgeSource` shape — never added to a session, never flushed."""
    return models.KnowledgeSource(
        source_fetch_enabled=True,
        source_url=url,
        allowed_domain=allowed_domain,
        allowed_url_patterns_json=(
            json.dumps(list(allowed_url_patterns)) if allowed_url_patterns else None
        ),
        max_fetch_bytes=max_bytes,
        trust_level=trust_level,
        review_required=review_required,
    )


def _get(http_get: HttpGet, url: str, *, timeout: int) -> Any:
    try:
        return http_get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=False,
        )
    except requests.Timeout as exc:
        raise AdapterFrameworkError("TIMEOUT", str(exc)) from exc
    except requests.RequestException as exc:
        raise AdapterFrameworkError("NETWORK_ERROR", str(exc)) from exc


def fetch_live_https(
    *,
    url: str,
    allowed_domain: str,
    allowed_url_patterns: Optional[Sequence[str]] = None,
    trust_level: str = "official",
    review_required: bool = True,
    max_bytes: int = MAX_CONTENT_BYTES,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    http_get: Optional[HttpGet] = None,
) -> FixtureTransportResponse:
    """Controlled single-URL live HTTPS fetch (I5 PUBLIC_WEB_FETCH path only).

    Fail-closed: SSRF, robots-block, timeout, rate-limit, and oversized-body
    conditions all raise `AdapterFrameworkError` with the matching category.
    Ordinary HTTP outcomes (200/304/404/410/5xx) are returned as a
    `FixtureTransportResponse` so the unchanged `build_fetch_envelope`
    pipeline classifies them exactly like the fixture path.

    `http_get` defaults to `requests.get`; unit tests MUST inject a fake to
    avoid real network I/O for the content fetch.
    """
    # I5 HTTPS-only enforcement ahead of Gate3 (Gate3's validate_fetch_url still
    # tolerates http:// — I5 requires https:// for the controlled live path).
    safe_url = assert_safe_public_https_url(url, allowed_domain=allowed_domain)
    source = _build_transient_source(
        url=safe_url,
        allowed_domain=allowed_domain,
        allowed_url_patterns=allowed_url_patterns,
        trust_level=trust_level,
        review_required=review_required,
        max_bytes=max_bytes,
    )
    getter = http_get or requests.get

    try:
        target = validate_fetch_url(safe_url, source)
        check_robots_allowed(target, source, user_agent=USER_AGENT)
    except FetchSecurityError as exc:
        raise AdapterFrameworkError("UNSAFE_URL", str(exc)) from exc
    except RobotsBlockedError as exc:
        raise AdapterFrameworkError("ROBOTS_BLOCKED", str(exc)) from exc

    resp = _get(getter, target, timeout=timeout)

    if int(resp.status_code) in _REDIRECT_STATUSES:
        loc = _header_value(resp.headers, "Location")
        if not loc:
            raise AdapterFrameworkError("NETWORK_ERROR", "redirect_missing_location")
        try:
            # Same-host relative Location headers (e.g. CDC `/physical-activity/...`)
            # must be joined against the current absolute target before SSRF checks.
            # Cross-host / private / non-https targets still fail closed below.
            redirect_candidate = loc if urlparse(loc).scheme else urljoin(target, loc)
            redirect_safe = assert_safe_public_https_url(
                redirect_candidate, allowed_domain=allowed_domain
            )
            target = validate_redirect_url(redirect_safe, source)
        except (AdapterFrameworkError, FetchSecurityError) as exc:
            raise AdapterFrameworkError("UNSAFE_URL", f"redirect:{exc}") from exc
        resp = _get(getter, target, timeout=timeout)

    status = int(resp.status_code)
    if status == 429:
        raise AdapterFrameworkError("RATE_LIMITED", str(status))
    if status in (408, 504):
        raise AdapterFrameworkError("TIMEOUT", str(status))

    body = _response_body(resp)
    if len(body) > max_bytes:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", str(len(body)))

    return FixtureTransportResponse(
        status_code=status,
        body=body,
        content_type=_header_value(resp.headers, "Content-Type", "text/html; charset=utf-8"),
        final_url=target,
        etag=_header_value(resp.headers, "ETag") or None,
        last_modified=_header_value(resp.headers, "Last-Modified") or None,
    )
