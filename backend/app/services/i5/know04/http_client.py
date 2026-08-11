"""Hardened HTTP client for KNOW-04 official connectors (SSRF + size + retry)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlencode, urlparse

from backend.app.services.i5.adapters.base import assert_safe_public_https_url

MAX_RESPONSE_BYTES = 2_097_152
DEFAULT_TIMEOUT = 15.0
RETRYABLE = {429, 500, 502, 503, 504}


class ConnectorHttpError(RuntimeError):
    def __init__(self, code: str, detail: str = "", *, status: Optional[int] = None):
        self.code = code
        self.detail = detail
        self.status = status
        super().__init__(f"{code}:{detail}")


@dataclass
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    url: str

    def text(self, encoding: str = "utf-8") -> str:
        return self.content.decode(encoding, errors="replace")

    def json(self) -> Any:
        try:
            return json.loads(self.content.decode("utf-8"))
        except Exception as e:
            raise ConnectorHttpError("MALFORMED_JSON", str(e), status=self.status_code) from e


def _header_get(headers: Mapping[str, str], name: str) -> Optional[str]:
    lower = {k.lower(): v for k, v in headers.items()}
    return lower.get(name.lower())


class HardenedHttpClient:
    def __init__(
        self,
        *,
        allowed_domains: Optional[Sequence[str]] = None,
        max_bytes: int = MAX_RESPONSE_BYTES,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        rate_limiter=None,
        http_get: Optional[Callable[..., Any]] = None,
        sleep_fn=time.sleep,
    ):
        self.allowed_domains = tuple(allowed_domains or ())
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limiter = rate_limiter
        self.http_get = http_get
        self.sleep_fn = sleep_fn

    def get(
        self,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        expect_content_types: Optional[set[str]] = None,
    ) -> HttpResponse:
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode({k: v for k, v in params.items() if v is not None})}"
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ConnectorHttpError("SCHEME_NOT_HTTPS", parsed.scheme or "")
        if self.allowed_domains:
            last_err: Exception | None = None
            ok = False
            for d in self.allowed_domains:
                try:
                    assert_safe_public_https_url(url, allowed_domain=d)
                    ok = True
                    break
                except Exception as e:
                    last_err = e
            if not ok and last_err is not None:
                raise ConnectorHttpError("UNSAFE_URL", str(last_err))
        else:
            assert_safe_public_https_url(url)

        attempt = 0
        while True:
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()
            attempt += 1
            if self.http_get is None:
                raise ConnectorHttpError("NETWORK_DISABLED", "inject http_get or enable live transport")
            raw = self.http_get(url, headers=dict(headers or {}), timeout=self.timeout)
            if isinstance(raw, dict):
                status = int(raw.get("status_code", 200))
                hdrs = {str(k): str(v) for k, v in (raw.get("headers") or {}).items()}
                content = raw.get("content", b"")
                if isinstance(content, str):
                    content = content.encode("utf-8")
                final_url = raw.get("url", url)
            else:
                status = int(getattr(raw, "status_code"))
                hdrs = {str(k): str(v) for k, v in dict(getattr(raw, "headers", {})).items()}
                content = getattr(raw, "content", b"") or b""
                final_url = str(getattr(raw, "url", url))

            if len(content) > self.max_bytes:
                raise ConnectorHttpError("CONTENT_TOO_LARGE", str(len(content)), status=status)
            if status in RETRYABLE and attempt <= self.max_retries:
                self.sleep_fn(min(2 ** (attempt - 1), 8))
                continue
            if 400 <= status < 500 and status != 429:
                raise ConnectorHttpError("PERMANENT_HTTP_4XX", str(status), status=status)
            if status >= 500:
                raise ConnectorHttpError("HTTP_5XX_EXHAUSTED", str(status), status=status)
            if expect_content_types:
                ctype = (_header_get(hdrs, "content-type") or "").split(";")[0].strip().lower()
                if ctype and ctype not in expect_content_types:
                    raise ConnectorHttpError("CONTENT_TYPE_MISMATCH", ctype, status=status)
            return HttpResponse(status_code=status, headers=hdrs, content=content, url=final_url)
