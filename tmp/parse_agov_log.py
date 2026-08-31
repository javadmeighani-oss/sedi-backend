import json
import re
from pathlib import Path

text = Path("tmp/agov_ok.log").read_text(encoding="utf-8", errors="replace")
for line in text.splitlines():
    if '"candidate_before"' not in line and '"no_auto_activation"' not in line:
        continue
    idx = line.find("{")
    if idx < 0:
        continue
    raw = line[idx:]
    # GHA may truncate with ...
    if raw.endswith("..."):
        raw = raw[: -3]
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to recover truncated matrix by cutting at last complete key region
        continue
    if "candidate_before" in obj:
        keep = [
            "candidate_before",
            "candidate_after",
            "new_candidates",
            "qualified_total",
            "rejected_total",
            "needs_review_total",
            "discovered_total",
            "owh_status",
            "cdc_child_status",
            "cdc_ncezid_status",
            "active_source_count",
            "strong_domains",
            "moderate_domains",
            "thin_domains",
            "uncovered_domains",
            "monitor_findings_count",
            "duplicate_suppressed",
            "status_after",
            "baseline",
            "d17_elig",
            "d18_als_eligible",
            "d19_ms_eligible",
        ]
        print(json.dumps({k: obj.get(k) for k in keep}, indent=2, sort_keys=True))
        matrix = obj.get("d01_d19_matrix") or []
        print("MATRIX_ROWS", len(matrix))
        for row in matrix:
            print(
                f"{row.get('dxx')}|{row.get('depth_state')}|elig={row.get('eligible')}|pubs={row.get('active_publishers')}|proof={row.get('serving_proof')}"
            )
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))
