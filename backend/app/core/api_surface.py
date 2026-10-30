"""Pilot hardening of the public API surface (pure helpers, read from the environment; no I/O).

- The interactive API documentation (/docs, /redoc, /openapi.json) lists every route of the service: it is OFF unless
  ``SEDI_EXPOSE_DOCS`` is true. ``app.openapi()`` keeps working for the contract tests.
- CORS is for browser pages. The Sedi app is a native Android client and needs none, so the default is NO cross-origin
  access; a browser client is allowed only through an explicit ``CORS_ALLOW_ORIGINS`` list (comma separated).
- Every response carries the basic browser-hardening headers; HSTS is added only when the request really came over
  HTTPS (nginx sets ``X-Forwarded-Proto``).
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional

_TRUE = ("1", "true", "yes", "on")

# 180 days; no includeSubDomains / preload on purpose (other sub-domains are not ours to decide here).
HSTS_VALUE = "max-age=15552000"


def _flag(environ: Mapping[str, str], name: str) -> bool:
    return (environ.get(name) or "").strip().lower() in _TRUE


def docs_urls(environ: Mapping[str, str]) -> Dict[str, Optional[str]]:
    """FastAPI keyword arguments for the documentation URLs."""
    if _flag(environ, "SEDI_EXPOSE_DOCS"):
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


def cors_origins(environ: Mapping[str, str]) -> List[str]:
    """Allowed browser origins: exactly the listed ones; a wildcard is never accepted."""
    raw = (environ.get("CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return []
    out: List[str] = []
    for part in raw.split(","):
        origin = part.strip().rstrip("/")
        if origin and origin != "*" and origin not in out:
            out.append(origin)
    return out


def security_headers(*, https: bool) -> Dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }
    if https:
        headers["Strict-Transport-Security"] = HSTS_VALUE
    return headers


def request_is_https(scheme: str, forwarded_proto: Optional[str]) -> bool:
    proto = (forwarded_proto or "").split(",")[0].strip().lower()
    return (proto or (scheme or "").lower()) == "https"
