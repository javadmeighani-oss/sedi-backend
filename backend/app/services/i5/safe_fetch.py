"""J3-b (D-407): a small, SSRF-safe HTTPS page reader for provider verification.

Sedi reads the PUBLIC page a search result points to, to check that the phone / address / rating the search model reported are really
on that page (anti-fabrication). The URL comes from a model, so it is untrusted input:

* https only, port 443 only, no credentials in the URL, host must be a real DNS name (no IP literals);
* EVERY resolved address must be public (no loopback / private / link-local / reserved / multicast / metadata ranges);
* the connection is PINNED to the validated address (DNS rebinding cannot swap it afterwards);
* redirects are followed by hand (max 3) and each hop is validated again;
* total time, body size and content type are capped; ``Accept-Encoding: identity`` (no decompression bombs);
* robots.txt of the host is honoured (R-045): a disallowed path is not fetched.

Never raises: every failure is a ``FetchResult`` with ``ok=False`` and a short reason. No cookies, no body is sent, nothing from the
user is ever put in the request.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
import urllib.robotparser
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

USER_AGENT = "SediBot/1.0 (+https://sedi-ai.com; provider page check)"
MAX_BYTES = 1_500_000
TOTAL_TIMEOUT = 8.0
MAX_REDIRECTS = 3
_ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "application/json", "text/plain")

Resolver = Callable[[str], list]


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    url: str = ""
    status: int = 0
    body: bytes = b""
    reason: str = ""


def _default_resolver(host: str) -> list:
    return [info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]


def is_public_address(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast
        or addr.is_unspecified or (addr.version == 4 and addr in ipaddress.ip_network("100.64.0.0/10"))  # carrier-grade NAT
    )


def validate_url(url: str, resolver: Resolver = _default_resolver) -> tuple[Optional[str], Optional[str], str]:
    """-> (host, pinned_ip, reason). ``reason`` is empty when the URL may be fetched."""
    try:
        parts = urlparse((url or "").strip())
    except ValueError:
        return None, None, "bad_url"
    if parts.scheme != "https":
        return None, None, "not_https"
    if parts.username or parts.password:
        return None, None, "credentials_in_url"
    if parts.port not in (None, 443):
        return None, None, "port_not_allowed"
    host = (parts.hostname or "").strip(".").lower()
    try:
        ipaddress.ip_address(host)
        return None, None, "ip_literal"
    except ValueError:
        pass
    if not host or "." not in host:
        return None, None, "bad_host"
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost", ".lan", ".home", ".corp")):
        return None, None, "internal_name"
    try:
        addresses = list(dict.fromkeys(resolver(host)))
    except Exception:  # noqa: BLE001
        return None, None, "dns_failed"
    if not addresses:
        return None, None, "dns_failed"
    if not all(is_public_address(a) for a in addresses):
        return None, None, "non_public_address"
    return host, addresses[0], ""


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS to a validated IP while keeping the real host name for SNI and certificate checks."""

    def __init__(self, host: str, ip: str, timeout: float):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = ip

    def connect(self) -> None:  # noqa: D401
        sock = socket.create_connection((self._pinned_ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _get_once(host: str, ip: str, path: str, timeout: float) -> tuple[int, dict, bytes, str]:
    conn = _PinnedHTTPS(host, ip, timeout)
    try:
        conn.request("GET", path or "/", headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                                                   "Accept-Encoding": "identity", "Connection": "close"})
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        ctype = headers.get("content-type", "").split(";")[0].strip().lower()
        if resp.status in (301, 302, 303, 307, 308):
            return resp.status, headers, b"", ctype
        if ctype and ctype not in _ALLOWED_TYPES:
            return resp.status, headers, b"", ctype
        length = headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BYTES:
            return resp.status, headers, b"", "too_large"
        body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            return resp.status, headers, b"", "too_large"
        return resp.status, headers, body, ctype
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


_robots_cache: dict[str, tuple[float, Optional[urllib.robotparser.RobotFileParser]]] = {}


def _allowed_by_robots(host: str, ip: str, url: str, timeout: float) -> bool:
    now = time.time()
    hit = _robots_cache.get(host)
    if hit is None or now - hit[0] > 6 * 3600:
        parser: Optional[urllib.robotparser.RobotFileParser] = None
        try:
            status, _h, body, _c = _get_once(host, ip, "/robots.txt", min(timeout, 4.0))
            if status == 200 and body:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(body.decode("utf-8", "replace").splitlines())
        except Exception:  # noqa: BLE001 - no readable robots.txt = no restriction published
            parser = None
        if len(_robots_cache) > 256:
            _robots_cache.pop(next(iter(_robots_cache)))
        _robots_cache[host] = (now, parser)
        hit = _robots_cache[host]
    parser = hit[1]
    return True if parser is None else parser.can_fetch(USER_AGENT, url)


def fetch_page(url: str, *, resolver: Resolver = _default_resolver) -> FetchResult:
    """Read one public page. Never raises."""
    deadline = time.time() + TOTAL_TIMEOUT
    current = (url or "").strip()
    try:
        for _hop in range(MAX_REDIRECTS + 1):
            host, ip, why = validate_url(current, resolver)
            if why or not host or not ip:
                return FetchResult(False, current, reason=why or "invalid")
            remaining = deadline - time.time()
            if remaining <= 0.5:
                return FetchResult(False, current, reason="timeout")
            parts = urlparse(current)
            path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
            if not _allowed_by_robots(host, ip, current, remaining):
                return FetchResult(False, current, reason="robots_disallow")
            status, headers, body, ctype = _get_once(host, ip, path, max(remaining, 1.0))
            if status in (301, 302, 303, 307, 308):
                location = headers.get("location")
                if not location:
                    return FetchResult(False, current, status, reason="redirect_without_location")
                current = urljoin(current, location)
                continue
            if ctype == "too_large":
                return FetchResult(False, current, status, reason="too_large")
            if ctype and ctype not in _ALLOWED_TYPES:
                return FetchResult(False, current, status, reason="content_type")
            if status != 200:
                return FetchResult(False, current, status, reason=f"http_{status}")
            return FetchResult(True, current, status, body)
        return FetchResult(False, current, reason="too_many_redirects")
    except Exception as exc:  # noqa: BLE001
        return FetchResult(False, current, reason=type(exc).__name__)
