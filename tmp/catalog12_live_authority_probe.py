"""One-shot live authority/robots probe for Catalog-12. Not a production writer."""

from __future__ import annotations

import json
import ssl
import urllib.request
from urllib.parse import urlparse

from backend.app.services.i5.know01.catalog12_specialty_authorities import CATALOG12_CELLS

UA = "SediKB/1.0 (+https://sedi.health; curated-knowledge-fetch)"
CTX = ssl.create_default_context()


def fetch(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            body = resp.read(12000)
            return {
                "url": url,
                "final": str(getattr(resp, "url", url)),
                "status": int(getattr(resp, "status", 200)),
                "ctype": resp.headers.get("Content-Type", ""),
                "bytes": len(body),
                "has_html": (
                    b"<html" in body.lower()
                    or b"<title" in body.lower()
                    or b"<!doctype" in body.lower()
                ),
                "robots_disallow_star": b"disallow: /\n" in body.lower() or b"disallow: /" == body.lower().strip(),
                "err": "",
            }
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", 0) or 0
        return {
            "url": url,
            "final": "",
            "status": int(code) if code else 0,
            "ctype": "",
            "bytes": 0,
            "has_html": False,
            "robots_disallow_star": False,
            "err": f"{type(exc).__name__}:{str(exc)[:180]}",
        }


def main() -> None:
    rows = []
    for cell in CATALOG12_CELLS:
        page = fetch(cell.canary_url)
        host = urlparse(cell.canary_url).netloc
        robots = fetch(f"https://{host}/robots.txt")
        rows.append(
            {
                "cell": cell.cell_id,
                "authority": cell.primary_authority,
                "domain": cell.primary_domain,
                "page_status": page["status"],
                "page_html": page["has_html"],
                "page_final": page["final"][:160],
                "page_err": page["err"],
                "robots_status": robots["status"],
                "robots_err": robots["err"],
            }
        )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
