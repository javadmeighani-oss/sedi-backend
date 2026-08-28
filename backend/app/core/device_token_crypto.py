"""Per-device token hashing helpers (no auth policy)."""

from __future__ import annotations

import hashlib
import secrets


def generate_device_token() -> str:
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()
