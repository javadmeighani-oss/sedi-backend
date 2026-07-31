# PKG-EXT-E2-BOUNDED-01-R1 Evidence Pack

## Package identity
- PACKAGE_ID: PKG-EXT-E2-BOUNDED-01-R1
- AUTHORITY: §167 + Javad authorization for bounded network collection
- REPOSITORY_HEAD: af1d583df55a8df8284105917e86caf6342eb089
- BRANCH: feature/section15/backend-continuity-foundation
- CREATED_AT_UTC: 2026-07-29T06:45:33Z

## Approved network scope
- Six primary publisher-family ECUs / nine candidates
- Official hosts only per §167
- H1 per ECU then H2 only if H1 allows
- Frozen URL allowlist before first request
- Rights-aware retention; append-only master log §168

## Non-authorizations
- No overlay approval; no dry-run; no Stage 5; no P2
- No EO-C11 closure; no crawler/source activation
- No git add/commit/push
- No nlm.nih.gov / generic nih.gov fetches
- No CAPTCHA/auth bypass; no search engines

## H1/H2 model
- H1: landing + robots (+ linked terms when available)
- H2: same-host governance paths only after H1 pass
- Independent ECU fail-closed (CDC 403 and APA anti-bot did not stop other ECUs)
- POST-AUDIT (R1-POST-AUDIT-02): no ECU has EXPLICITLY_SUPPORTED_FOR_R1_H2
- Completed H2 evidence = COLLECTED_BUT_GOVERNANCE_USE_RESTRICTED
- Javad authorization != publisher permission; HTTP 200 != automation permission
- OVERLAY_APPROVAL_ELIGIBLE_COUNT = 0; R1_FINAL_ACCEPTANCE = NO

## Retention policy
- robots.txt: RAW_RETAINED_TECHNICAL_POLICY where retrieved
- HTML: hash + minimal excerpt; raw deleted when rights unknown
- Ability to download ≠ retention permission

## Directory layout
- url_allowlist.json, request_ledger.json, manifest.json
- ecu/, candidate_packs/, decision_matrices/, retention_ledger/
- Post-audit matrices: permission_dimension_matrix.json, r1_post_audit_findings.json, evidence_file_inventory.json

## Hash verification
```powershell
Get-FileHash -Algorithm SHA256 docs/evidence/section29/pkg_ext_e2_bounded_01_r1/manifest.json
Get-FileHash -Algorithm SHA256 docs/evidence/section29/pkg_ext_e2_bounded_01_r1/request_ledger.json
Get-FileHash -Algorithm SHA256 docs/evidence/section29/pkg_ext_e2_bounded_01_r1/url_allowlist.json
```

## Limitations
- Successful retrieval is not legal/clinical/product approval
- Future source/crawler automation remains UNKNOWN_FAIL_CLOSED
- Bounded R1 one-time H2 may be SUFFICIENT_FOR_R1_H2 without future automation approval
- OVERLAY_APPROVAL_ELIGIBLE_COUNT = 0

## Weekly International Knowledge Crawler Final Law (FIX3)

LAW_ID = I5-WEEKLY-INTERNATIONAL-KNOWLEDGE-CRAWLER-FINAL-LAW
PACKAGE = SECTION29-WEEKLY-INTERNATIONAL-KNOWLEDGE-CRAWLER-FINAL-LAW-FIX3
RECORDED_AT_UTC = 2026-07-31T07:05:38Z

- International trusted sources supply all clinical/medical/psychology/lifestyle knowledge.
- Iranian sources are directory-only (doctors, labs, hospitals, treatment centers) unless Javad decides otherwise.
- Knowledge-Database-First runtime is mandatory.
- Knowledge Gap Priority Queue feeds the weekly international crawler.
- Crawler eligibility is not activation.
- Publisher approval is not a universal prerequisite.

## Conceptual Knowledge Use and Memory Law (FIX4)

LAW_ID = I5-CONCEPTUAL-KNOWLEDGE-USE-AND-MEMORY-LAW
PACKAGE = SECTION29-CONCEPTUAL-KNOWLEDGE-USE-LAW-FIX4
RECORDED_AT_UTC = 2026-07-31T07:32:59Z

- Direct publisher approval is not a universal knowledge-use prerequisite.
- Source content is input for conceptual learning, not default response text.
- Structured Knowledge Database and Knowledge Memory are mandatory and separate.
- Independent Sedi synthesis is mandatory.
- Knowledge-Database-First runtime is mandatory.
