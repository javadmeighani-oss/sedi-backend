# Gate 3H — Risk and Approval Policy (V1)

**Status:** Proposal — aligns with `backend/app/services/gate3/constants.py` and `source_review_policy.py`.  
**Final approver (V1):** Javad (admin). No formal scientific team until V2+.

---

## 1. Review pipeline

```
Curated allowlisted fetch (admin only)
  → SSRF + robots check
  → Parse + AI/rule review (KnowledgeAIReviewService)
  → pending_review ingestion run (default for sensitive)
  → Javad admin approve/reject
  → active document + chunks
  → searchable only when source active + fresh + document active
```

---

## 2. Category risk tiers

### Tier 1 — Low-risk (first population batch eligible)

| Category | Auto-approve in V1? | Javad review |
|----------|---------------------|--------------|
| `lifestyle` | Only if explicit `auto_approve_low_risk=true` **and** AI scores pass | Recommended for batch 1 |
| `daily_planning` | Same | Recommended |
| `habit_change` | Same | Recommended |
| `exercise` | **No** (not in LOW_RISK list — fails safe) | **Required** |
| `sleep` | **No** | **Required** |
| `nutrition` | **No** | **Required** |

Gate 3G code: only `lifestyle`, `daily_planning`, `habit_change`, `culture`, `sports`, `science`, `beauty_wellness`, `other` are in `LOW_RISK_AUTO_APPROVE_ELIGIBLE_CATEGORIES`. Even then, auto-approve needs high AI scores and `auto_approve_low_risk=true`.

**V1 policy:** Set `auto_approve_low_risk=false` on **all** catalog sources. Javad approves every activation cycle.

### Tier 2 — Sensitive (always human review)

Enforced by `SENSITIVE_REVIEW_REQUIRED_CATEGORIES` — `normalize_source_review_policy()` forces `review_required=true`, `auto_approve_low_risk=false`:

- `mental_wellbeing`, `psychological_support`, `emotional_support`, `stress_management`
- `health_care`, `prevention`, `caregiving`, `chronic_care`, `elderly_care`
- `medical_condition`, `medication_education`, `clinical_guideline`, `emergency_education`
- `diet_program`, `exercise_program`
- `provider_directory`, `lab_directory`, `local_services`

### Tier 3 — Never auto-approve in V1 (reject or defer)

- All Tier 2 categories
- Any content with crisis terms (self-harm, suicide) → AI recommends **reject**; use emergency safety flow in chat only
- Clinical guidelines, medication dosing, diagnosis language
- Iran provider/lab directories until legal + robots review complete
- `nice.org.uk` clinical guidance pages (deferred)

---

## 3. Mental wellbeing rules (Group B)

| Rule | Implementation |
|------|----------------|
| Non-diagnostic | Reject pages with diagnosis/prescription language in AI review |
| No therapist replacement | Reject promotional or directive treatment language |
| Crisis content | `psychological_risk_level=critical` → reject from KB; chat uses emergency template |
| `review_required` | Always `true` |
| `auto_approve_low_risk` | Always `false` |
| Low-risk self-help exception | Only **page-level** after Javad reads extracted preview — not category-level auto-approve |

Topic tags (`sleep_psychology`, `grief_support`, etc.) are planning metadata; API `category` must use `KB_CATEGORIES` literals.

---

## 4. Iran provider/lab rules (Group C)

| Rule | Detail |
|------|--------|
| Official vs operational | IRMIC = verification reference; appointment sites = directory only |
| No “best doctor/lab” | Ranking phrases stripped in search; forbidden in output validation |
| No fabricated fields | No license, price, availability, insurance unless explicitly in source text |
| No booking/coordination | V1: citation + curated options only |
| Cross-check | Prefer listing providers with verifiable identifiers when both sources exist |
| Fetch default | `source_fetch_enabled=false` until robots/terms/legal sign-off |
| Scraping disallowed | Mark `robots_terms_status: disallowed`; pursue API/partnership |

---

## 5. Future auto-approve (post-V1, not now)

After **3–5 successful manual cycles** per source with zero critical findings:

- May consider `auto_approve_low_risk=true` **only** for Tier-1 categories in `LOW_RISK_AUTO_APPROVE_ELIGIBLE_CATEGORIES`
- Never for mental wellbeing, provider directories, or clinical content
- Requires explicit written approval from Javad per source

---

## 6. Safety constraints (confirmed)

| Constraint | Status in Gate 3G code |
|------------|------------------------|
| No live web answers in chat | No runtime fetch in chat tests; KB retrieval from DB only |
| No runtime crawler during chat | `KnowledgeUpdateService` admin-only |
| No user-triggered fetch | Admin `X-Admin-Token` only |
| No scheduled crawler (production) | `SEDI_KB_SCHEDULED_FETCH_ENABLED` unset; `kb_scheduler` is no-op hook |
| Approved active KB only in search | `document.status=active` + `source.ingestion_status=active` + freshness |
| `pending_review` excluded | Chunks created only on `_activate_run` after approve |
| Javad approval required V1 | All catalog entries `approval_owner: Javad` |
