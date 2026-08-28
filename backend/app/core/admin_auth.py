"""Fail-closed admin token guard (repository convention)."""

from __future__ import annotations

import os

from fastapi import HTTPException, Request


def require_admin_token_fail_closed(request: Request) -> None:
    """Require configured ADMIN_TOKEN and matching X-Admin-Token header."""
    admin_token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not admin_token:
        raise HTTPException(status_code=403, detail="admin_disabled")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != admin_token:
        raise HTTPException(status_code=401, detail="Admin token required")
