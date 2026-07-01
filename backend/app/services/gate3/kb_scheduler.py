"""Optional scheduled KB fetch hook (disabled by default).

Enable with environment variable:
  SEDI_KB_SCHEDULED_FETCH_ENABLED=true
"""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session


def scheduled_fetch_enabled() -> bool:
    return os.environ.get("SEDI_KB_SCHEDULED_FETCH_ENABLED", "").strip().lower() in ("1", "true", "yes")


def run_scheduled_kb_fetch(db: Session) -> Optional[dict]:
    """
    Placeholder for future cron/worker integration.
    Does nothing unless SEDI_KB_SCHEDULED_FETCH_ENABLED is set.
    """
    if not scheduled_fetch_enabled():
        return None
    # V1: orchestration hook only; no production crawl without explicit env + admin-configured sources.
    return {"status": "disabled_hook", "fetched": 0}
