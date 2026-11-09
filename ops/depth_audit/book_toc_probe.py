"""R-083 - READ-ONLY probe of candidate reference-book sources (runs inside the backend container via stdin).

For each candidate entry page it reports: HTTP status, bytes, whether the page declares CC BY, how many book-page links the
static HTML exposes (can the weekly link discovery follow the table of contents?), and whether robots.txt allows the path
for a generic crawler. No writes, no DB, no user data. Output lines start with `BOOK|`.
"""
from __future__ import annotations

import json
import re
import urllib.request
from urllib import robotparser
from urllib.parse import urljoin, urlparse

UA = "SediResearchBot/1.0 (+read-only probe)"
CANDIDATES = [
    ("openstax_anatomy_physiology_2e", "https://openstax.org/books/anatomy-and-physiology-2e/pages/1-introduction", r"/books/anatomy-and-physiology-2e/pages/"),
    ("openstax_sociology_3e", "https://openstax.org/books/introduction-sociology-3e/pages/1-introduction", r"/books/introduction-sociology-3e/pages/"),
    ("openstax_psychology_2e", "https://openstax.org/books/psychology-2e/pages/1-introduction", r"/books/psychology-2e/pages/"),
    ("openstax_nutrition_hawaii", "https://pressbooks.oer.hawaii.edu/humannutrition2/", r"/humannutrition2/"),
    ("openstax_microbiology", "https://openstax.org/books/microbiology/pages/1-introduction", r"/books/microbiology/pages/"),
]


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:  # noqa: S310 - fixed https candidates above
        return r.status, r.geturl(), r.read(2_000_000)


def _extra() -> None:
    """Where can a WHOLE open book be listed legally and politely? robots Sitemap lines, sitemap size, GitHub source repos."""
    try:
        robots = _get("https://openstax.org/robots.txt")[2].decode("utf-8", errors="replace")
        sm = [ln.split(":", 1)[1].strip() for ln in robots.splitlines() if ln.lower().startswith("sitemap")]
        print("BOOK|" + json.dumps({"openstax_robots_sitemaps": sm[:5]}, ensure_ascii=False))
        for u in sm[:2]:
            st, _f, body = _get(u)
            txt = body.decode("utf-8", errors="replace")
            print("BOOK|" + json.dumps({"sitemap": u, "status": st, "bytes": len(body), "loc": len(re.findall("<loc>", txt)), "anatomy_pages": len(re.findall("/books/anatomy-and-physiology-2e/pages/", txt))}))
    except Exception as exc:  # noqa: BLE001
        print("BOOK|" + json.dumps({"sitemap_error": type(exc).__name__}))
    for repo in ("openstax/osbooks-anatomy-physiology-bundle", "openstax/osbooks-psychology-bundle"):
        try:
            st, _f, body = _get(f"https://api.github.com/repos/{repo}")
            d = json.loads(body.decode("utf-8", errors="replace"))
            print("BOOK|" + json.dumps({"github": repo, "status": st, "license": (d.get("license") or {}).get("spdx_id"), "size_kb": d.get("size")}))
        except Exception as exc:  # noqa: BLE001
            print("BOOK|" + json.dumps({"github": repo, "error": type(exc).__name__}))


def main() -> int:
    robots_cache: dict[str, robotparser.RobotFileParser] = {}
    for key, url, link_pat in CANDIDATES:
        row = {"key": key, "url": url}
        try:
            status, final, body = _get(url)
            text = body.decode("utf-8", errors="replace")
            links = {urljoin(final, m) for m in re.findall(r'href=["\']([^"\'#]+)["\']', text) if re.search(link_pat, urljoin(final, m))}
            host = urlparse(final).scheme + "://" + urlparse(final).netloc
            if host not in robots_cache:
                rp = robotparser.RobotFileParser()
                try:
                    rp.parse(_get(host + "/robots.txt")[2].decode("utf-8", errors="replace").splitlines())
                except Exception:  # noqa: BLE001
                    rp = None
                robots_cache[host] = rp
            rp = robots_cache[host]
            row.update(
                status=status,
                bytes=len(body),
                cc_by=bool(re.search(r"creativecommons\.org/licenses/by/4\.0", text)),
                cc_nc_nd_sa=bool(re.search(r"creativecommons\.org/licenses/by-(nc|nd|sa)", text)),
                toc_links=len(links),
                robots_allows=(rp.can_fetch(UA, url) if rp else None),
            )
        except Exception as exc:  # noqa: BLE001
            row.update(error=type(exc).__name__)
        print("BOOK|" + json.dumps(row, sort_keys=True, ensure_ascii=False))
    _extra()
    return 0


raise SystemExit(main())
