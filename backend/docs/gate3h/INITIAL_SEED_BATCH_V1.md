# Gate 3H — Initial Seed Batch (V1)

**Status:** Proposal only — **do not fetch or ingest in production** until Javad approves this list.

## Selection criteria

- Low-to-medium content risk
- Self-help / lifestyle / general wellbeing
- **Excluded from batch 1:** medication, diagnosis, clinical guidelines, emergency, pregnancy, child, elderly, chronic care
- Iran provider/lab: **catalog prepared, population deferred**
- All entries: `ingestion_status=draft`, `source_fetch_enabled=false` until robots check passes

---

## Recommended first batch (8 pages)

| # | source_key | Target URL (single page) | API category | Risk | Notes |
|---|------------|------------------------|--------------|------|-------|
| 1 | nhs_uk_live_well | `https://www.nhs.uk/live-well/exercise/` | `exercise` | medium | General physical activity guidance |
| 2 | nhs_uk_live_well | `https://www.nhs.uk/live-well/sleep-and-tiredness/` | `sleep` | medium | Sleep hygiene — non-clinical |
| 3 | medlineplus_consumer_health | `https://medlineplus.gov/healthyliving.html` | `lifestyle` | low-medium | Broad healthy living overview |
| 4 | medlineplus_consumer_health | `https://medlineplus.gov/exerciseandphysicalfitness.html` | `exercise` | medium | Consumer exercise info |
| 5 | who_global_health_topics | `https://www.who.int/news-room/fact-sheets/detail/physical-activity` | `lifestyle` | medium | WHO fact sheet — activity |
| 6 | cdc_health_lifestyle | `https://www.cdc.gov/physicalactivity/basics/index.htm` | `exercise` | medium | CDC basics — prevention category if source registered as CDC |
| 7 | nhs_mental_health | `https://www.nhs.uk/mental-health/self-help/guides-tools-and-activities/five-steps-to-mental-wellbeing/` | `mental_wellbeing` | **high** | **Javad required** — priority mental wellbeing |
| 8 | nimh_nih_mental_health | `https://www.nimh.nih.gov/health/publications/coping-with-stress` | `stress_management` | **high** | **Javad required** — coping skills, non-diagnostic |

### Optional 9–10 (after batch 1 success)

| # | source_key | Target URL | category | Risk |
|---|------------|------------|----------|------|
| 9 | medlineplus_consumer_health | `https://medlineplus.gov/nutrition.html` | `nutrition` | medium |
| 10 | apa_psychology_help | `https://www.apa.org/topics/anger` | `psychological_support` | high |

---

## Per-page workflow (staging / later production)

1. Register parent **source** from catalog (if not exists) via `POST /knowledge-base/sources`
2. Set `source_fetch_enabled=true` only after robots.txt check for that domain
3. Run **one** `POST /knowledge-base/sources/{id}/fetch` with URL matching `allowed_url_patterns`
4. Inspect `GET /knowledge-base/ingestion-runs/{id}` — AI review fields
5. Javad: `POST .../approve` or `.../reject`
6. Verify chunks: DB count or admin documents list
7. JWT smoke: `GET /knowledge-base/search?q=<topic>`
8. Document outcome in ops log before next page

---

## Deferred (not batch 1)

- `nice_org_uk_public` — clinical guidelines
- All Group C Iran directories — legal/robots/structure review
- MedlinePlus `ency/article/*` — too clinical for first crawl
- Any emergency/crisis education pages
