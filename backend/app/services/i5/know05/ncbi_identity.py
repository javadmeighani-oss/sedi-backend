"""NF16 — operational NCBI identity (no .test / no invented contacts)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional


class NcbiIdentityError(EnvironmentError):
    pass


_DISALLOWED_EMAIL_SUFFIXES = (
    ".test",
    ".example",
    ".invalid",
    ".localhost",
)
_DISALLOWED_LOCAL_PARTS = frozenset({"test", "example", "noreply", "no-reply"})
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class NcbiOperationalIdentity:
    tool: str
    email: str
    api_key_present: bool
    weekly_operation_status: str  # LIVE_READY | BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY

    def as_dict(self) -> dict[str, object]:
        return {
            "tool": self.tool,
            "email_domain": self.email.rsplit("@", 1)[-1] if "@" in self.email else "",
            "api_key_present": self.api_key_present,
            "weekly_operation_status": self.weekly_operation_status,
            # Never expose full email in logs/artifacts
            "email_redacted": True,
        }


def is_disallowed_operational_email(email: str) -> bool:
    e = (email or "").strip().lower()
    if not e or not _EMAIL_RE.match(e):
        return True
    local, _, domain = e.partition("@")
    if any(domain.endswith(suf) or domain == suf.lstrip(".") for suf in _DISALLOWED_EMAIL_SUFFIXES):
        return True
    if domain in {"example.com", "example.org", "example.net", "sedi.test"}:
        return True
    if local in _DISALLOWED_LOCAL_PARTS:
        return True
    return False


def load_ncbi_operational_identity(*, require_for_weekly: bool = True) -> NcbiOperationalIdentity:
    tool = os.environ.get("SEDI_NCBI_TOOL", "").strip()
    email = os.environ.get("SEDI_NCBI_EMAIL", "").strip()
    api_key = os.environ.get("SEDI_NCBI_API_KEY", "").strip()
    if not tool or not email or is_disallowed_operational_email(email):
        if require_for_weekly:
            return NcbiOperationalIdentity(
                tool=tool or "",
                email=email or "",
                api_key_present=bool(api_key),
                weekly_operation_status="BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY",
            )
        raise NcbiIdentityError("BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY")
    if " " in tool:
        raise NcbiIdentityError("NCBI_TOOL_MUST_HAVE_NO_SPACES")
    return NcbiOperationalIdentity(
        tool=tool,
        email=email,
        api_key_present=bool(api_key),
        weekly_operation_status="LIVE_READY",
    )


def assert_no_secret_leak(blob: str) -> None:
    """Fail if an operational NCBI email appears in log/artifact text."""
    email = os.environ.get("SEDI_NCBI_EMAIL", "").strip()
    if email and email in blob:
        raise NcbiIdentityError("NCBI_EMAIL_LEAKED_TO_ARTIFACT_OR_LOG")
