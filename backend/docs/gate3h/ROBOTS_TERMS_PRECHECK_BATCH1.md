# Gate 3H — Batch 1 Robots/Terms Pre-Check

**Date:** 2026-07-01  
**Status:** Recorded — documentation only; no production fetch executed  
**Approved by:** Javad (planning sign-off on pre-check report)

---

## A. Scope and method

Manual read-only pre-check for Gate 3H Batch 1 candidate domains and pages listed in:

- `backend/config/gate3h/trusted_source_catalog_v1.yaml`
- `backend/docs/gate3h/INITIAL_SEED_BATCH_V1.md`

**Method:**

- Fetched and read public `robots.txt` per domain (browser/tool — not Sedi production crawler)
- Reviewed public terms/licensing pages where available
- Did **not** call production admin APIs, use `ADMIN_TOKEN`, create KB data, or run `POST .../fetch`

---

## B. User-Agent assumed

Gate 3G production fetch uses:

```text
SediKB/1.0 (+https://sedi.health; curated-knowledge-fetch)
```

Robots interpretation below assumes this User-Agent (not listed on WHO bad-bot blocklist).

---

## C. Batch 1 source/page table

| # | source_key | URL | category | batch1_status |
|---|------------|-----|----------|---------------|
| 1 | `nhs_uk_live_well` | https://www.nhs.uk/live-well/sleep-and-tiredness/ | sleep | **recommended_first_controlled_fetch** |
| 2 | `nhs_uk_live_well` | https://www.nhs.uk/live-well/exercise/ | exercise | approved_for_later_controlled_fetch |
| 3 | `medlineplus_consumer_health` | https://medlineplus.gov/healthyliving.html | lifestyle | deferred_mixed_copyright_review |
| 4 | `medlineplus_consumer_health` | https://medlineplus.gov/exerciseandphysicalfitness.html | exercise | deferred_mixed_copyright_review |
| 5 | `who_global_health_topics` | https://www.who.int/news-room/fact-sheets/detail/physical-activity | lifestyle | deferred_terms_unclear |
| 6 | `cdc_health_lifestyle` | https://www.cdc.gov/physicalactivity/basics/index.htm | exercise | deferred_sensitive_prevention |
| 7 | `nhs_mental_health` | https://www.nhs.uk/mental-health/.../five-steps-to-mental-wellbeing/ | mental_wellbeing | deferred_mental_wellbeing_high_risk |
| 8 | `nimh_nih_mental_health` | https://www.nimh.nih.gov/health/publications/coping-with-stress | stress_management | deferred_mental_wellbeing_high_risk |

---

## D. Robots result table

| Domain | robots URL | Relevant rules | Path result | Status |
|--------|------------|----------------|-------------|--------|
| nhs.uk | https://www.nhs.uk/robots.txt | `User-agent: *` disallows `/Conditions/`, service-search, etc. — **not** `/live-well/` or `/mental-health/` | Batch paths allowed | **robots_allowed** |
| medlineplus.gov | https://medlineplus.gov/robots.txt | Disallow `/cgi/`, `/xml/`, feeds — not batch HTML pages | Batch paths allowed | **robots_allowed** |
| who.int | https://www.who.int/robots.txt | Named bad bots `Disallow: /`; no `User-agent: *` blanket block | Fact sheet path allowed for SediKB/1.0 | **robots_allowed** |
| cdc.gov | https://www.cdc.gov/robots.txt | Disallow travel, templates — **not** `/physicalactivity/` | Batch path allowed | **robots_allowed** |
| nimh.nih.gov | https://www.nimh.nih.gov/robots.txt | Disallow `/core/`, `/search/`, `/admin/` — **not** `/health/publications/` | Batch path allowed | **robots_allowed** |

---

## E. Terms/licensing result table

| Source | Policy summary | Ingestion assessment |
|--------|----------------|----------------------|
| NHS | OGL v3.0; attribution required; refresh cached copy ≤7 days | **allowed_with_attribution** |
| MedlinePlus | Public-domain summaries with required attribution; mixed copyrighted sections (A.D.A.M., drugs) | **allowed_with_attribution** — caution on mixed pages |
| WHO | Mostly CC BY-NC-SA 3.0 IGO (non-commercial) | **unclear_needs_review** for commercial product use |
| CDC | Public domain; attribution + non-endorsement disclaimer | **allowed_with_attribution** |
| NIMH | Public domain text; attribution; no misleading edits | **allowed_with_attribution** — high content sensitivity |

---

## F. Recommended YAML status updates

Recorded in `trusted_source_catalog_v1.yaml` (`catalog_version: 3h-v1.1`):

| source_key | `robots_terms_status` |
|------------|----------------------|
| `nhs_uk_live_well` | `approved_for_controlled_fetch` |
| `medlineplus_consumer_health` | `approved_for_controlled_fetch` (+ mixed-copyright caution) |
| `who_global_health_topics` | `deferred_terms_unclear` |
| `cdc_health_lifestyle` | `approved_for_controlled_fetch` (not first cycle) |
| `nhs_mental_health` | `deferred_until_lifestyle_cycle_success` |
| `nimh_nih_mental_health` | `deferred_until_lifestyle_cycle_success` |
| Iran provider/lab (Group C) | `deferred_restricted` |

Per-page statuses in `batch1_pages` section of catalog YAML.

---

## G. Safest first controlled fetch: NHS Sleep

**URL:** https://www.nhs.uk/live-well/sleep-and-tiredness/

| Field | Value |
|-------|-------|
| category | `sleep` |
| risk | low_to_medium |
| robots | allowed |
| terms | allowed_with_attribution |
| license | OGL — "Information from the NHS website" |
| freshness | ≤7 days (`freshness_policy_days: 7`) |
| approval_owner | Javad |

---

## H. Deferred sources/pages and reasons

| Page / source | Reason |
|---------------|--------|
| MedlinePlus healthyliving / exercise | Mixed copyright on page — review Summary-only ingest |
| WHO physical activity | CC BY-NC-SA commercial-use unclear |
| CDC physical activity | `prevention` category sensitive in Gate 3G — not cycle 1 |
| NHS five steps mental wellbeing | `mental_wellbeing` high risk — after lifestyle success |
| NIMH coping with stress | Mental/stress high risk — after lifestyle success |
| Iran directories (Group C) | robots/legal/API/partnership review required |
| NICE clinical guidelines | Excluded from batch 1 |

---

## I. Required constraints before fetch

- [ ] Javad explicit approval for first controlled fetch
- [ ] `source_fetch_enabled=false` on create; enable only for NHS sleep source after approval
- [ ] `freshness_policy_days: 7` for NHS-derived sources
- [ ] `license_notes` and citation in chunks
- [ ] `SEDI_KB_SCHEDULED_FETCH_ENABLED` remains unset
- [ ] Exactly **one** URL per fetch cycle
- [ ] DB backup before first production source creation
- [ ] No mental health, provider, or lab sources in cycle 1

---

## J. Reminder: this is not legal advice

This document records a technical pre-check for internal operations planning. It does not constitute legal advice. Uncertainties (especially WHO non-commercial licensing and MedlinePlus mixed copyright) should be confirmed with qualified counsel before large-scale ingestion.

---

## Related files

- Catalog: `backend/config/gate3h/trusted_source_catalog_v1.yaml`
- Batch list: `backend/docs/gate3h/INITIAL_SEED_BATCH_V1.md`
- Runbook: `backend/docs/gate3h/PRODUCTION_KB_POPULATION_RUNBOOK.md`
