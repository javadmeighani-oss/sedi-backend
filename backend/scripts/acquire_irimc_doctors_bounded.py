"""Bounded IRIMC doctor acquisition for production Iran-directory apply.

Uses injectable IrimcMemberSearchClient + parse/normalize APIs.
Honors MIN_SEARCH_INTERVAL_SECONDS (>=60s) and MAX_CONCURRENT_SEARCHES (=1).
Logs counts/hashes only — never full names or PII dumps.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Bounded query set (5–8). Values are search filters only; never printed.
BOUNDED_QUERIES: tuple[dict[str, str], ...] = (
    {"OfficeCity": "تهران"},
    {"OfficeCity": "اصفهان"},
    {"OfficeCity": "شیراز"},
    {"OfficeCity": "مشهد"},
    {"DegreeField": "پزشکی داخلی"},
    {"McCode": "12345"},
    {"FirstName": "علی", "LastName": "محمدی"},
)

DEFAULT_OUTPUT = Path("/tmp/iran_doctors_normalized.json")
MAX_QUERIES = 8


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _http_transport():
    """Build requests-backed get/post callables for IrimcMemberSearchClient."""
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("REQUESTS_REQUIRED") from exc

    from backend.app.services.i5.iran_directory_acquisition import TransportResponse

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "SediIranDirectoryAcquisition/1.0 "
                "(+https://sedi-ai.com; bounded-respectful; robots-honored)"
            ),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fa,en;q=0.8",
        }
    )

    def get(url: str, **kwargs: Any) -> TransportResponse:
        cookies = kwargs.pop("cookies", None) or {}
        resp = session.get(url, cookies=cookies, timeout=90, allow_redirects=True)
        resp.raise_for_status()
        return TransportResponse(body=resp.content, cookies=dict(resp.cookies))

    def post(url: str, **kwargs: Any) -> TransportResponse:
        cookies = kwargs.pop("cookies", None) or {}
        data = kwargs.pop("data", None)
        resp = session.post(
            url, data=data, cookies=cookies, timeout=90, allow_redirects=True
        )
        resp.raise_for_status()
        return TransportResponse(body=resp.content, cookies=dict(resp.cookies))

    return get, post


def acquire(
    *,
    output_path: Path = DEFAULT_OUTPUT,
    queries: tuple[dict[str, str], ...] | None = None,
    sleep_seconds: float | None = None,
) -> dict[str, Any]:
    from backend.app.services.i5.iran_directory_acquisition import (
        IrimcMemberSearchClient,
        bounded_query,
    )
    from backend.app.services.i5.iran_directory_normalization import (
        normalize_records,
        parse_irimc_search_html,
    )
    from backend.app.services.i5.iran_directory_source_manifest import (
        IRIMC_SOURCE,
        MAX_CONCURRENT_SEARCHES,
        MIN_SEARCH_INTERVAL_SECONDS,
        get_authorized_source,
        robots_path_allowed,
    )

    if MAX_CONCURRENT_SEARCHES != 1:
        raise SystemExit("CONCURRENCY_CONTRACT_FAILED")
    interval = float(sleep_seconds if sleep_seconds is not None else MIN_SEARCH_INTERVAL_SECONDS)
    if interval < 60:
        raise SystemExit("INTERVAL_BELOW_ROBOTS_FLOOR")

    source = get_authorized_source(IRIMC_SOURCE)
    if not robots_path_allowed(IRIMC_SOURCE, "/") or not robots_path_allowed(
        IRIMC_SOURCE, "/searchresult"
    ):
        raise SystemExit("ROBOTS_PATH_NOT_ALLOWED")

    selected = list(queries if queries is not None else BOUNDED_QUERIES)[:MAX_QUERIES]
    if not (5 <= len(selected) <= MAX_QUERIES):
        raise SystemExit(f"QUERY_BOUND_INVALID:{len(selected)}")

    get, post = _http_transport()
    client = IrimcMemberSearchClient(get, post)

    raw_all: list[dict[str, Any]] = []
    query_meta: list[dict[str, Any]] = []
    started = datetime.now(timezone.utc).isoformat()

    print(
        json.dumps(
            {
                "phase": "start",
                "source": IRIMC_SOURCE,
                "query_count": len(selected),
                "interval_seconds": interval,
                "base_url_present": bool(source.get("base_url")),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    for idx, filters in enumerate(selected):
        if idx > 0:
            time.sleep(interval)
        q = bounded_query(filters)
        field_keys = sorted(q.keys())
        try:
            html = client.search(q)
            parsed = parse_irimc_search_html(html)
            raw_all.extend(parsed)
            query_meta.append(
                {
                    "index": idx,
                    "fields": field_keys,
                    "html_bytes": len(html),
                    "html_sha256": _sha256_bytes(html),
                    "parsed_count": len(parsed),
                    "status": "ok",
                }
            )
            print(
                json.dumps(
                    {
                        "phase": "query",
                        "index": idx,
                        "fields": field_keys,
                        "html_bytes": len(html),
                        "html_sha256": _sha256_bytes(html),
                        "parsed_count": len(parsed),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 — fail closed with counts only
            query_meta.append(
                {
                    "index": idx,
                    "fields": field_keys,
                    "status": "error",
                    "error_type": type(exc).__name__,
                }
            )
            print(
                json.dumps(
                    {
                        "phase": "query_error",
                        "index": idx,
                        "fields": field_keys,
                        "error_type": type(exc).__name__,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            raise SystemExit(f"ACQUISITION_QUERY_FAILED:{idx}:{type(exc).__name__}") from exc

    valid, rejected = normalize_records(raw_all)
    finished = datetime.now(timezone.utc).isoformat()

    # Stable payload hash over canonical keys only (no PII in hash input log).
    key_blob = "\n".join(
        sorted(f"{r['entity_family']}:{r['canonical_directory_key']}" for r in valid)
    ).encode("utf-8")
    records_key_sha256 = _sha256_bytes(key_blob)

    payload = {
        "records": valid,
        "meta": {
            "source_system_label": IRIMC_SOURCE,
            "entity_family": "DOCTOR",
            "acquired_at": started,
            "finished_at": finished,
            "query_count": len(selected),
            "interval_seconds": interval,
            "raw_parsed_count": len(raw_all),
            "normalized_count": len(valid),
            "rejected_count": len(rejected),
            "rejected_reasons": sorted({str(item.get("reason")) for item in rejected}),
            "query_meta": query_meta,
            "records_key_sha256": records_key_sha256,
            "schema": "{records:[...], meta:{...}}",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    output_path.write_bytes(encoded)

    summary = {
        "phase": "done",
        "output": str(output_path),
        "bytes": len(encoded),
        "sha256": _sha256_bytes(encoded),
        "normalized_count": len(valid),
        "rejected_count": len(rejected),
        "records_key_sha256": records_key_sha256,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = DEFAULT_OUTPUT
    if args:
        out = Path(args[0])
    acquire(output_path=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
