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
            loc = resp.headers.get("Location")
            if not loc:
                raise FetchSecurityError("redirect_missing_location")
            redirect_url = validate_redirect_url(loc, source)
            resp = requests.get(
                redirect_url,
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=False,
            )
            target = redirect_url
        resp.raise_for_status()
        content = resp.content[:max_bytes]
        if len(resp.content) > max_bytes:
            raise FetchSecurityError("max_fetch_bytes_exceeded")
        return FetchResult(
            url=target,
            content=content,
            content_type=resp.headers.get("Content-Type", "text/plain"),
            final_url=target,
        )
