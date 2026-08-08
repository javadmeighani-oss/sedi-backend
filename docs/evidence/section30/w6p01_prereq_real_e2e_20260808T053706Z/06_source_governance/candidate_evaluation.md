# I5-IMPL-W6-P01 — Source Governance Candidate Evaluation

Status: documentation/evidence only. No `source_fetch_enabled`/`ACTIVE` catalog
change is made by this file. No production Knowledge Source rows are created
or activated by this evaluation. Persistence/activation against the real DB
is explicitly deferred — see "Non-actions" below.

## A. Method

Candidates are drawn from `backend/config/gate3h/trusted_source_catalog_v1.yaml`
(`catalog_version: 3h-v1.1`) and its pre-check record,
`backend/docs/gate3h/ROBOTS_TERMS_PRECHECK_BATCH1.md` (2026-07-01, Javad
planning sign-off). A candidate is treated as **ELIGIBLE** for the W6-P01
controlled live acquisition surface only when ALL of the following hold:

1. `robots_terms_status: approved_for_controlled_fetch` in the catalog (or the
   equivalent per-page `batch1_status: recommended_first_controlled_fetch` /
   `approved_for_later_controlled_fetch`).
2. The Batch-1 robots pre-check table records `Path result: allowed` for the
   candidate's page path (i.e. not covered by a `Disallow` rule for
   `SediKB/1.0 (+https://sedi.health; curated-knowledge-fetch)`).
3. The Batch-1 terms/licensing table records a clear, commercial-use-compatible
   licence (not `unclear_needs_review` / mixed-copyright caution without a
   Summary-only carve-out).
4. `category` falls in `risk_tiers.low_v1_batch_eligible` (lifestyle / sleep /
   exercise / daily_planning / habit_change / nutrition) — not
   `sensitive_always_javad` or `never_auto_approve_v1`.
5. `review_required: true` and `source_fetch_enabled: false` remain the
   catalog defaults (no candidate here is auto-approved for unattended fetch).

Any candidate failing (1)-(4) is **DEFERRED**, not rejected outright — the
catalog and pre-check doc already record the specific reason.

## B. Candidate table

| # | source_key | page (batch1_pages) | category | robots | terms/licence | catalog `robots_terms_status` | Result |
|---|------------|----------------------|----------|--------|----------------|-------------------------------|--------|
| 1 | `nhs_uk_live_well` | `nhs_sleep` — https://www.nhs.uk/live-well/sleep-and-tiredness/ | sleep | `allowed` (nhs.uk `robots.txt` disallows `/Conditions/`, service-search — not `/live-well/`) | OGL v3.0, attribution required ("Information from the NHS website"); `allowed_with_attribution` | `approved_for_controlled_fetch` | **ELIGIBLE** |
| 2 | `nhs_uk_live_well` | `nhs_exercise` — https://www.nhs.uk/live-well/exercise/ | exercise | `allowed` | OGL v3.0, `allowed_with_attribution` | `approved_for_controlled_fetch` (page status: `approved_for_later_controlled_fetch`, not first cycle) | DEFERRED (second-cycle only; see §D) |
| 3 | `medlineplus_consumer_health` | `medlineplus_healthyliving` — https://medlineplus.gov/healthyliving.html | lifestyle | `allowed` | Public-domain summary + mixed copyrighted sections (A.D.A.M., drug monographs); `allowed_with_attribution` with **mixed-copyright caution** | `approved_for_controlled_fetch` (+ mixed-copyright caution) | **DEFERRED** — mixed copyright review (§C) |
| 4 | `who_global_health_topics` | `who_physical_activity` — https://www.who.int/news-room/fact-sheets/detail/physical-activity | lifestyle | `allowed` | CC BY-NC-SA 3.0 IGO (non-commercial); `unclear_needs_review` for commercial product use | `deferred_terms_unclear` | **DEFERRED** — terms unclear (§C) |

## C. Deferred candidates and reasons

- **MedlinePlus — Consumer Health** (`medlineplus_consumer_health`): robots
  allowed and terms are `allowed_with_attribution`, but the catalog explicitly
  flags `mixed_copyright_caution: true` — the `healthyliving.html` /
  `exerciseandphysicalfitness.html` pages mix NLM public-domain summaries with
  copyrighted A.D.A.M./drug-monograph sections. `ROBOTS_TERMS_PRECHECK_BATCH1.md`
  §H records `batch1_status: deferred_mixed_copyright_review` and recommends
  "Summary-only ingest" review before any fetch. No such Summary-only
  extraction policy exists yet in this package, so this candidate stays
  DEFERRED.
- **WHO — Global Health Topics** (`who_global_health_topics`): robots allowed,
  but licensing is CC BY-NC-SA 3.0 IGO — **non-commercial**. Batch-1 doc §E/§H
  record `unclear_needs_review` / `deferred_terms_unclear` for commercial
  product use (Sedi is a commercial product). This is a legal/licensing
  question, not a technical one, and is explicitly out of scope for this
  package (see `ROBOTS_TERMS_PRECHECK_BATCH1.md` §J — "not legal advice").
- **NHS — Live Well / exercise page** (`nhs_uk_live_well`, `nhs_exercise` page):
  robots/terms are equally clear as the sleep page, but the pre-check doc
  explicitly scopes Batch 1 cycle 1 to **one URL** ("Exactly one URL per fetch
  cycle", §I) and names the sleep page as the
  `recommended_first_controlled_fetch`. The exercise page is
  `approved_for_later_controlled_fetch`, i.e. eligible in principle but held
  for a later cycle, not this evaluation.
- Mental-wellbeing sources (`nhs_mental_health`, `nimh_nih_mental_health`,
  `who_mental_health`, `apa_psychology_help`, `medlineplus_mental_health`) and
  all Group C provider/lab directories are `sensitive_always_javad` /
  `never_auto_approve_v1` / `deferred_restricted` in the catalog and are out of
  scope for this evaluation entirely (not re-litigated here).

## D. Result

```
ELIGIBLE_REAL_SOURCE_COUNT=1
ELIGIBLE_SOURCE_KEY=nhs_uk_live_well
ELIGIBLE_PAGE_KEY=nhs_sleep
ELIGIBLE_URL=https://www.nhs.uk/live-well/sleep-and-tiredness/
ALLOWED_DOMAIN=nhs.uk
ALLOWED_URL_PATTERN=^https://www\.nhs\.uk/live-well/.*
TRUST_LEVEL=official
LICENSE=OGL v3.0 — "Information from the NHS website" attribution required
FRESHNESS_POLICY_DAYS=7
APPROVAL_OWNER=Javad
ROBOTS_TERMS_STATUS=approved_for_controlled_fetch
BATCH1_STATUS=recommended_first_controlled_fetch
DEFERRED_CANDIDATES=medlineplus_consumer_health (mixed copyright), who_global_health_topics (terms unclear commercial use)
```

The one ELIGIBLE candidate (`nhs_uk_live_well` sleep page) is exactly the URL
already exercised in the W6-P01 live-acquisition unit tests
(`backend/tests/test_section30_i5_w6_p01_live_acquisition.py`) via the
`allowed_domain`/`allowed_url_patterns` shape it would use in a real
`KnowledgeSource`/`GovernedSourceProfile` row — those tests use a stand-in
`example.org` fixture domain, not this real NHS URL, since unit tests must not
perform real network I/O.

## E. Non-actions (explicitly out of scope here)

- No row is created or modified in `trusted_source_catalog_v1.yaml`.
- No `GovernedSourceProfile` / `KnowledgeSource` row is created, updated, or
  set `ACTIVE` in any database.
- No `source_fetch_enabled` flag is flipped to `true` anywhere.
- No live HTTPS request to `nhs.uk` (or any other domain) is made by this
  evidence package or by the accompanying unit tests.
- Persistence and activation of this ELIGIBLE candidate against a real
  `GovernedSourceProfile`/`KnowledgeSource` row is a separate, later step once
  the migration path referenced in
  `docs/evidence/section30/activation_w6p01_20260808T050921Z/01_authority_manifest/execution_manifest.txt`
  (`HARD_STOP_REQUIRED_MIGRATION_NOT_AUTHORED`) is resolved.

## F. Related files

- Catalog: `backend/config/gate3h/trusted_source_catalog_v1.yaml`
- Pre-check: `backend/docs/gate3h/ROBOTS_TERMS_PRECHECK_BATCH1.md`
- Batch list: `backend/docs/gate3h/INITIAL_SEED_BATCH_V1.md`
- Prior hard-stop record (pre-W6-P01 implementation):
  `docs/evidence/section30/activation_w6p01_20260808T050921Z/`
