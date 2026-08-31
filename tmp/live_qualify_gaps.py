"""Live qualify gap-target candidates (no activation)."""
from __future__ import annotations

import json

from backend.app.services.i5.autonomous_source_governance import (
    _live_http_probe,
    qualify_candidate,
    seed_to_candidate,
)
from backend.app.services.i5.candidate_qualification_registry import candidate_rows

TARGETS = {
    "nidcd_hearing_balance": "https://www.nidcd.nih.gov/health",
    "owh_womens_health": "https://www.womenshealth.gov",
    "cdc_child_development": "https://www.cdc.gov/ncbddd/childdevelopment/",
    "cdc_ncezid_infectious": "https://www.cdc.gov/ncezid/",
    "gard_rare_diseases": "https://rarediseases.info.nih.gov",
    "nichd_rehabilitation": "https://www.nichd.nih.gov/health",
    "who_fact_sheets": "https://www.who.int/news-room/fact-sheets",
}

rows = {str(r.get("candidate_id")): r for r in candidate_rows()}
# Ensure seed rows exist for missing ones via discovery merge fields
from backend.app.services.i5.autonomous_source_governance import discover_candidates, merge_discovered_into_registry

merged, _ = merge_discovered_into_registry(discover_candidates(include_wave02_gaps=False), base_rows=list(candidate_rows()))
by_id = {str(r.get("candidate_id")): r for r in merged}

out = {}
for cid, url in TARGETS.items():
    row = by_id.get(cid)
    if row is None:
        out[cid] = {"error": "missing"}
        continue
    row = dict(row)
    row["candidate_url_family"] = url
    row["url_family"] = url
    probe = _live_http_probe(url, timeout=8.0)
    # Temporarily clear CDC/OWH qualify downgrade by using live qualify path
    q = qualify_candidate(row, live=True)
    out[cid] = {
        "status": q.get("qualification_status"),
        "reason": (q.get("qualification_reason") or "")[:240],
        "robots": q.get("robots_state"),
        "access": q.get("access_state"),
        "rights": q.get("rights_state"),
        "activation": q.get("activation"),
        "probe_http": probe.get("http_status"),
        "probe_robots": probe.get("robots_allowed"),
        "probe_contained": probe.get("domain_contained"),
        "probe_ct": probe.get("content_type"),
        "probe_err": probe.get("error"),
        "final_url": probe.get("final_url"),
    }

print(json.dumps(out, indent=2, sort_keys=True))
