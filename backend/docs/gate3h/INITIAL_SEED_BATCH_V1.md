# Gate 3H — Initial Seed Batch (V1)

**Status:** Robots/terms pre-check recorded 2026-07-01 — **do not fetch or ingest in production** until Javad approves first controlled fetch.  
**Pre-check doc:** `ROBOTS_TERMS_PRECHECK_BATCH1.md`

## Selection criteria

- Low-to-medium content risk
- Self-help / lifestyle / general wellbeing
- **Excluded from batch 1 cycle 1:** medication, diagnosis, clinical guidelines, emergency, pregnancy, child, elderly, chronic care, mental wellbeing, provider/lab
- Iran provider/lab: **catalog prepared, population deferred**
- All entries: `ingestion_status=draft`, `source_fetch_enabled=false` until Javad approves fetch

---

## Recommended first batch (8 pages)

| # | source_key | Target URL | API category | Risk | batch1_status |
|---|------------|------------|--------------|------|---------------|
| 1 | nhs_uk_live_well | `https://www.nhs.uk/live-well/exercise/` | `exercise` | medium | **approved_for_later_controlled_fetch** |
| 2 | nhs_uk_live_well | `https://www.nhs.uk/live-well/sleep-and-tiredness/` | `sleep` | low_to_medium | **recommended_first_controlled_fetch** |
| 3 | medlineplus_consumer_health | `https://medlineplus.gov/healthyliving.html` | `lifestyle` | low-medium | **deferred_mixed_copyright_review** |
| 4 | medlineplus_consumer_health | `https://medlineplus.gov/exerciseandphysicalfitness.html` | `exercise` | medium | **deferred_mixed_copyright_review** |
| 5 | who_global_health_topics | `https://www.who.int/news-room/fact-sheets/detail/physical-activity` | `lifestyle` | medium | **deferred_terms_unclear** |
| 6 | cdc_health_lifestyle | `https://www.cdc.gov/physicalactivity/basics/index.htm` | `exercise` | medium | **deferred_sensitive_prevention** |
| 7 | nhs_mental_health | `https://www.nhs.uk/mental-health/self-help/guides-tools-and-activities/five-steps-to-mental-wellbeing/` | `mental_wellbeing` | **high** | **deferred_mental_wellbeing_high_risk** |
| 8 | nimh_nih_mental_health | `https://www.nimh.nih.gov/health/publications/coping-with-stress` | `stress_management` | **high** | **deferred_mental_wellbeing_high_risk** |

### Optional 9–10 (after batch 1 success)

| # | source_key | Target URL | category | Risk |
|---|------------|------------|----------|------|
| 9 | medlineplus_consumer_health | `https://medlineplus.gov/nutrition.html` | `nutrition` | medium |
| 10 | apa_psychology_help | `https://www.apa.org/topics/anger` | `psychological_support` | high |

---

## Per-page pre-check detail

### NHS Sleep (first controlled fetch candidate)

| Field | Value |
|-------|-------|
| URL | https://www.nhs.uk/live-well/sleep-and-tiredness/ |
| category | `sleep` |
| risk | low_to_medium |
| robots | allowed (manual pre-check 2026-07-01) |
| terms | allowed_with_attribution (OGL v3.0) |
| license requirement | Attribution/citation required — "Information from the NHS website" |
| freshness recommendation | ≤7 days (`freshness_policy_days: 7`) |
| first cycle | **recommended** |
| approval_owner | Javad |

### Other pages (summary)

| Page | robots | terms | Notes |
|------|--------|-------|-------|
| NHS Exercise | allowed | allowed_with_attribution | Second cycle after sleep success |
| MedlinePlus Healthy Living | allowed | allowed_with_attribution | Defer — mixed copyright |
| MedlinePlus Exercise | allowed | allowed_with_attribution | Defer — mixed copyright |
| WHO Physical Activity | allowed | unclear_needs_review | Defer — CC BY-NC-SA |
| CDC Physical Activity | allowed | allowed_with_attribution | Defer — prevention sensitive |
| NHS Five Steps | allowed | allowed_with_attribution | Defer — mental wellbeing high risk |
| NIMH Coping with Stress | allowed | allowed_with_attribution | Defer — mental/stress high risk |

---

## Per-page workflow (staging / later production)

1. Register parent **source** from catalog (if not exists) via `POST /knowledge-base/sources`
2. Set `source_fetch_enabled=true` only after Javad approves fetch for that page
3. Run **one** `POST /knowledge-base/sources/{id}/fetch` with URL matching `allowed_url_patterns`
4. Inspect `GET /knowledge-base/ingestion-runs/{id}` — AI review fields
5. Javad: `POST .../approve` or `.../reject`
6. Verify chunks: DB count or admin documents list
7. JWT smoke: `GET /knowledge-base/search?q=<topic>`
8. Document outcome in ops log before next page

---

## Deferred (not batch 1 cycle 1)

- `nice_org_uk_public` — clinical guidelines
- All Group C Iran directories — `deferred_restricted`; robots/legal/API/partnership review
- MedlinePlus `ency/article/*` — too clinical for first crawl
- Any emergency/crisis education pages
- Mental wellbeing pages (#7–8) until lifestyle cycle succeeds
