# Gate 3H — Automatic Trusted Knowledge Source Catalog

**Gate:** 3H (pre–Gate 4)  
**Status:** Documentation + catalog proposal — no production execution  
**Production baseline:** SHA `ed007d8693f77dc55a850661e9d3756e82b4260a`, Alembic `036_gate3g_kb_fetch_review`, KB empty

## Purpose

Populate Sedi V1 knowledge from **allowlisted trusted sources** with AI first-pass review and **Javad/admin final approval** — without blind crawling, user-triggered fetch, or live web in chat.

## Deliverables

| File | Description |
|------|-------------|
| `backend/config/gate3h/trusted_source_catalog_v1.yaml` | Structured source catalog (16 proposed sources) |
| `backend/docs/gate3h/RISK_AND_APPROVAL_POLICY_V1.md` | Risk tiers and approval rules |
| `backend/docs/gate3h/INITIAL_SEED_BATCH_V1.md` | First 8–10 pages for controlled fetch |
| `backend/docs/gate3h/PRODUCTION_KB_POPULATION_RUNBOOK.md` | Step-by-step production procedure (not executed) |

## Code assessment summary

| Option | Verdict |
|--------|---------|
| A. Runbook only | Sufficient for first 1–3 manual cycles |
| **B. Static YAML + runbook** | **Recommended for V1** — current `POST /knowledge-base/sources` accepts all fields |
| C. Bulk admin endpoint | Not needed yet |
| D. Management command | Optional later if source count > 20 |

No code changes required for Gate 3H start. Optional follow-up (needs approval): dry-run import script that prints curl payloads from YAML.

## Next gate

Gate 4 should begin only after at least one approved active chunk exists and `/knowledge-base/search` returns results under JWT.
