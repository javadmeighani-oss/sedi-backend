from backend.app.services.i5.autonomous_source_governance import (
    ACTIVATION_HARD_BLOCK,
    run_foundation_pipeline,
)

r = run_foundation_pipeline(live=False, include_wave02_gaps=False)
print("counts", r["status_after"])
print("before/after/new", r["candidate_before"], r["candidate_after"], r["new_candidates"])
targets = {"D08", "D10", "D11", "D13", "D14", "D15"}
for c in r["candidates"]:
    d = str(c.get("target_dxx_kd") or "")
    cid = str(c.get("candidate_id") or "")
    if d in targets or cid in ACTIVATION_HARD_BLOCK or any(
        x in cid for x in ["nidcd", "owh", "child", "ncezid", "gard", "nichd", "who"]
    ):
        print(
            "|".join(
                [
                    cid,
                    d,
                    str(c.get("qualification_status")),
                    str(c.get("canonical_domain")),
                    str(c.get("candidate_url_family") or c.get("url_family")),
                    f"act={c.get('activation')}",
                ]
            )
        )
