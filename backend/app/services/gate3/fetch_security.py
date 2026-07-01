"""SSRF guard for curated knowledge source fetch (Gate 3G)."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from typing import List, Optional
from urllib.parse import urlparse

from backend.app import models


class FetchSecurityError(Exception):
    pass


_PRIVATE_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    for net in _PRIVATE_NETS:
        if ip in net:
            return True
    return False


def _resolve_host(hostname: str) -> List[str]:
    try:
        infos = socket.getaddrinfo(hostname, None)
        return list({item[4][0] for item in infos})
    except socket.gaierror:
        return []


def validate_fetch_url(url: str, source: models.KnowledgeSource) -> str:
    """Return normalized URL or raise FetchSecurityError."""
    if not url or not isinstance(url, str):
        raise FetchSecurityError("url_required")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise FetchSecurityError("scheme_not_allowed")
    if not parsed.hostname:
        raise FetchSecurityError("hostname_required")

    host = parsed.hostname.lower()
    if host in ("localhost", "metadata.google.internal"):
        raise FetchSecurityError("localhost_blocked")

    try:
        literal_ip = ipaddress.ip_address(host)
        if _is_blocked_ip(str(literal_ip)):
            raise FetchSecurityError("private_ip_blocked")
    except ValueError:
        pass

    for ip in _resolve_host(host):
        if _is_blocked_ip(ip):
            raise FetchSecurityError("private_ip_blocked")

    if source.allowed_domain:
        allowed = source.allowed_domain.lower().lstrip(".")
        if not (host == allowed or host.endswith("." + allowed)):
            raise FetchSecurityError("domain_not_allowed")

    patterns: List[str] = []
    if source.allowed_url_patterns_json:
        try:
            patterns = json.loads(source.allowed_url_patterns_json) or []
        except json.JSONDecodeError:
            patterns = []
    if patterns:
        if not any(re.search(p, url) for p in patterns):
            raise FetchSecurityError("url_pattern_not_allowed")

    if source.source_url and source.source_url.strip():
        reg = urlparse(source.source_url.strip())
        if reg.hostname and reg.hostname.lower() != host:
            raise FetchSecurityError("url_not_registered_source")

    return url.strip()


def validate_redirect_url(url: str, source: models.KnowledgeSource) -> str:
    return validate_fetch_url(url, source)
