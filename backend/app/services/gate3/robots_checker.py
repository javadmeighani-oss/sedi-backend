"""robots.txt policy check for curated KB fetch (Gate 3G)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
from urllib import robotparser

import requests

from backend.app import models


class RobotsBlockedError(Exception):
    pass


def check_robots_allowed(url: str, source: models.KnowledgeSource, *, user_agent: str = "SediKB/1.0") -> bool:
    """
    Return True if fetch is allowed. Fail closed for high-trust medical sources when robots cannot be checked.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        resp = requests.get(robots_url, timeout=8, headers={"User-Agent": user_agent})
        if resp.status_code >= 400:
            if source.trust_level in ("official", "clinical_guideline") and source.review_required:
                raise RobotsBlockedError("robots_unreachable_fail_closed")
            return True
        rp.parse(resp.text.splitlines())
        allowed = rp.can_fetch(user_agent, url)
        source.robots_checked_at = datetime.utcnow()
        source.robots_allowed = allowed
        if not allowed:
            raise RobotsBlockedError("robots_disallow")
        return True
    except RobotsBlockedError:
        raise
    except Exception:
        if source.trust_level in ("official", "clinical_guideline") and source.review_required:
            raise RobotsBlockedError("robots_check_failed") from None
        return True
