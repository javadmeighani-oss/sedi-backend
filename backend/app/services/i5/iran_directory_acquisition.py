"""Injectable, bounded IRIMC acquisition client.

This module deliberately has no HTTP implementation. A caller must supply its
own GET/POST transport, making live access explicit and testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Callable, Protocol

from .iran_directory_source_manifest import (
    IRIMC_SOURCE,
    MAX_RESULTS_PER_SEARCH,
    get_authorized_source,
    robots_path_allowed,
)

SEARCH_FIELDS = (
    "FirstName", "LastName", "Gender", "McCode", "DegreeField", "OfficeCity", "OfficeAddress",
)
MAX_QUERY_LENGTH = 128


class Transport(Protocol):
    def __call__(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class TransportResponse:
    body: bytes
    cookies: dict[str, str] | None = None


class _TokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "input" and values.get("name") == "__RequestVerificationToken":
            self.token = values.get("value")


def _response_parts(response: Any) -> tuple[bytes, dict[str, str]]:
    if isinstance(response, TransportResponse):
        return response.body, response.cookies or {}
    if isinstance(response, bytes):
        return response, {}
    if isinstance(response, str):
        return response.encode("utf-8"), {}
    body = getattr(response, "content", getattr(response, "body", None))
    if body is None:
        raise TypeError("TRANSPORT_RESPONSE_BODY_REQUIRED")
    return bytes(body), dict(getattr(response, "cookies", {}) or {})


def bounded_query(filters: dict[str, Any]) -> dict[str, str]:
    """Return only supported, nonempty filters bounded to a safe request size."""
    if not isinstance(filters, dict):
        raise ValueError("QUERY_INVALID")
    result: dict[str, str] = {}
    for field in SEARCH_FIELDS:
        value = filters.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if len(text) > MAX_QUERY_LENGTH:
            raise ValueError(f"QUERY_FIELD_TOO_LONG:{field}")
        if text:
            result[field] = text
    if not result:
        raise ValueError("QUERY_EMPTY")
    return result


class IrimcMemberSearchClient:
    """IRIMC form client; it neither solves nor bypasses authentication/captcha."""

    def __init__(self, get: Transport, post: Transport) -> None:
        self._get = get
        self._post = post
        self._cookies: dict[str, str] = {}

    def search(self, filters: dict[str, Any]) -> bytes:
        source = get_authorized_source(IRIMC_SOURCE)
        if not robots_path_allowed(IRIMC_SOURCE, "/") or not robots_path_allowed(IRIMC_SOURCE, "/searchresult"):
            raise ValueError("ROBOTS_PATH_NOT_ALLOWED")
        home, cookies = _response_parts(self._get(source["base_url"] + "/", cookies=self._cookies))
        self._cookies.update(cookies)
        parser = _TokenParser()
        parser.feed(home.decode("utf-8", errors="replace"))
        if not parser.token:
            raise ValueError("ANTIFORGERY_TOKEN_MISSING")
        payload = {field: "" for field in SEARCH_FIELDS}
        payload.update(bounded_query(filters))
        payload["__RequestVerificationToken"] = parser.token
        payload["pageSize"] = str(MAX_RESULTS_PER_SEARCH)
        result, cookies = _response_parts(
            self._post(source["base_url"] + "/searchresult", data=payload, cookies=self._cookies)
        )
        self._cookies.update(cookies)
        return result
