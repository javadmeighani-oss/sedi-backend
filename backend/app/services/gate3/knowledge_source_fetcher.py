"""Curated single-URL fetch for registered knowledge sources (Gate 3G)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

from backend.app import models
from backend.app.services.gate3.fetch_security import FetchSecurityError, validate_fetch_url, validate_redirect_url
from backend.app.services.gate3.robots_checker import RobotsBlockedError, check_robots_allowed


USER_AGENT = "SediKB/1.0 (+https://sedi.health; curated-knowledge-fetch)"
DEFAULT_TIMEOUT = 15


def _header_value(headers, key: str, default: str = "") -> str:
    if headers is None:
        return default
    try:
        raw = headers.get(key, default)
    except AttributeError:
        return default
    if not isinstance(raw, str):
        return default
    return raw.strip() or default


def _response_body(resp) -> bytes:
    body = getattr(resp, "content", b"")
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    if isinstance(body, str):
        return body.encode("utf-8", errors="replace")
    return b""


@dataclass
class FetchResult:
    url: str
    content: bytes
    content_type: str
    final_url: str


class KnowledgeSourceFetcher:
    def fetch(self, source: models.KnowledgeSource, url: Optional[str] = None) -> FetchResult:
        if not source.source_fetch_enabled:
            raise FetchSecurityError("source_fetch_disabled")
        target = validate_fetch_url(url or source.source_url or "", source)
        check_robots_allowed(target, source, user_agent=USER_AGENT)
        max_bytes = source.max_fetch_bytes or 2_097_152
        resp = requests.get(
            target,
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=False,
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = _header_value(resp.headers, "Location")
            if not loc:
                raise FetchSecurityError("redirect_missing_location")
            try:
                redirect_url = validate_redirect_url(loc, source)
            except TypeError as exc:
                raise FetchSecurityError("redirect_invalid_location") from exc
            resp = requests.get(
                redirect_url,
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=False,
            )
            target = redirect_url
        resp.raise_for_status()
        body = _response_body(resp)
        content = body[:max_bytes]
        if len(body) > max_bytes:
            raise FetchSecurityError("max_fetch_bytes_exceeded")
        return FetchResult(
            url=target,
            content=content,
            content_type=_header_value(resp.headers, "Content-Type", "text/plain"),
            final_url=target,
        )
