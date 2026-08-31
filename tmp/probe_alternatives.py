"""Probe gap URLs with browser-like UA; propose MedlinePlus alternatives."""
from __future__ import annotations

import json
import ssl
import urllib.request
from urllib import robotparser
from urllib.parse import urlparse


def probe(url: str) -> dict:
    out = {"url": url, "http": None, "final": None, "ct": None, "err": None, "robots": None}
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SediI5GovernedProbe/1.0; +https://sedi-ai.com)",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
            out["http"] = resp.getcode()
            out["final"] = resp.geturl()
            out["ct"] = (resp.headers.get("Content-Type") or "").split(";")[0]
            resp.read(1024)
    except Exception as exc:  # noqa: BLE001
        out["err"] = f"{type(exc).__name__}:{exc}"
    try:
        p = urlparse(url)
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        out["robots"] = rp.can_fetch("SediI5GovernedProbe/1.0", url)
    except Exception as exc:  # noqa: BLE001
        out["robots_err"] = str(exc)
    return out


URLS = [
    "https://www.cdc.gov/ncbddd/childdevelopment/",
    "https://www.cdc.gov/ncezid/",
    "https://www.cdc.gov/ncbddd/childdevelopment/facts.html",
    "https://www.cdc.gov/infectious-diseases/",
    "https://medlineplus.gov/childdevelopment.html",
    "https://medlineplus.gov/infectionsandpregnancy.html",
    "https://medlineplus.gov/infectiousdiseases.html",
    "https://medlineplus.gov/developmentaldisabilities.html",
    "https://www.nichd.nih.gov/health",
    "https://www.nichd.nih.gov/health/topics",
    "https://www.niaid.nih.gov/diseases-conditions",
    "https://www.womenshealth.gov/",
]

print(json.dumps({u: probe(u) for u in URLS}, indent=2))
