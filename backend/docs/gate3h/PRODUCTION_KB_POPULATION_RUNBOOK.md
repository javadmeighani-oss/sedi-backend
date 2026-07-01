# Gate 3H — Production KB Population Runbook

**Status:** Prepared for later execution — **DO NOT RUN** until Javad explicitly approves.  
**Prerequisites:** Production on Gate 3G (`036_gate3g_kb_fetch_review`), `ADMIN_TOKEN` set, KB counts currently zero.

---

## Hard rules (every cycle)

- [ ] `SEDI_KB_SCHEDULED_FETCH_ENABLED` remains **unset/false**
- [ ] No blind crawling — only catalog `allowed_domain` + `allowed_url_patterns`
- [ ] One source / one URL per controlled fetch cycle initially
- [ ] Javad approves every sensitive or first-time source activation
- [ ] DB backup before first production source creation (same pattern as Gate 3 deploy)
- [ ] Never expose `ADMIN_TOKEN` in logs or tickets

---

## Phase 0 — Pre-flight (read-only)

```bash
# Health
curl -sS https://api.sedi-ai.com/health
curl -sS https://api.sedi-ai.com/healthz

# Confirm KB empty (SSH on server)
docker exec sedi-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT COUNT(*) FROM knowledge_sources;"
```

Expected: counts = 0, scheduled fetch env unset.

---

## Phase 1 — Robots/terms check (manual, per domain)

Before enabling fetch on a source:

1. Fetch `https://<allowed_domain>/robots.txt` manually (browser or curl from admin workstation — **not** production crawler)
2. Record result in catalog `robots_terms_status`: `allowed` | `disallowed` | `pending_review`
3. If disallowed → keep `source_fetch_enabled=false`; plan API/partnership
4. Update `license_notes` on source with attribution requirements

---

## Phase 2 — Create source (admin)

Use catalog entry from `backend/config/gate3h/trusted_source_catalog_v1.yaml`.

```bash
API="https://api.sedi-ai.com"
# ADMIN_TOKEN from secure store — export locally, never commit

curl -sS -X POST "$API/knowledge-base/sources" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{
    "slug": "nhs-live-well-sleep",
    "name": "NHS — Sleep and tiredness",
    "category": "sleep",
    "trust_level": "official",
    "source_url": "https://www.nhs.uk/live-well/sleep-and-tiredness/",
    "locale": "en",
    "ingestion_status": "draft",
    "source_fetch_enabled": false,
    "allowed_domain": "nhs.uk",
    "allowed_url_patterns": ["^https://www\\.nhs\\.uk/live-well/sleep-and-tiredness/.*"],
    "fetch_method": "html_page",
    "review_required": true,
    "auto_approve_low_risk": false,
    "freshness_policy_days": 180,
    "fetch_interval_hours": 168,
    "license_notes": "NHS Open Government Licence — verify per page",
    "metadata": {"gate3h_source_key": "nhs_uk_live_well", "batch": "3h-v1-01"}
  }'
```

Save returned `id` as `SOURCE_ID`.

**After robots approval**, enable fetch:

```bash
curl -sS -X PATCH "$API/knowledge-base/sources/$SOURCE_ID" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"source_fetch_enabled": true}'
```

---

## Phase 3 — One controlled fetch

```bash
curl -sS -X POST "$API/knowledge-base/sources/$SOURCE_ID/fetch" \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

On policy/security error → expect HTTP 400; inspect `ingestion-runs` for failed audit row.

---

## Phase 4 — Inspect ingestion run

```bash
curl -sS "$API/knowledge-base/ingestion-runs" \
  -H "X-Admin-Token: $ADMIN_TOKEN"

curl -sS "$API/knowledge-base/ingestion-runs/$RUN_ID" \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

Review:

| Field | Action |
|-------|--------|
| `review_status` | `pending_review` → needs Javad |
| `ai_review_status` | `needs_review` / `failed` |
| `psychological_risk_level` | `critical` → **reject** |
| `medical_risk_level` | `high` → careful review |
| `extracted_text_preview` | Read before approve |
| `recommended_action` | `reject` / `pending_review` / `auto_approve` |

---

## Phase 5 — Approve or reject

**Approve (Javad):**

```bash
curl -sS -X POST "$API/knowledge-base/ingestion-runs/$RUN_ID/approve" \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

**Reject:**

```bash
curl -sS -X POST "$API/knowledge-base/ingestion-runs/$RUN_ID/reject" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"reason": "clinical language / crisis content / quality insufficient"}'
```

---

## Phase 6 — Verify chunks and search

**DB (SSH):**

```bash
docker exec sedi-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT COUNT(*) FROM knowledge_chunks;"
docker exec sedi-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT s.slug, d.title, COUNT(c.id) FROM knowledge_sources s
   JOIN knowledge_documents d ON d.source_id = s.id
   JOIN knowledge_chunks c ON c.document_id = d.id
   WHERE d.status = '"'"'active'"'"' GROUP BY s.slug, d.title;"
```

**Search (JWT required — use safe test user only):**

```bash
curl -sS "$API/knowledge-base/search?q=sleep" \
  -H "Authorization: Bearer $TEST_USER_JWT"
```

Expected: `chunks` non-empty, `stale_excluded` documented, citations present.

---

## Phase 7 — Repeat manual cycles

- Complete **3–5 successful** manual fetch → review → approve cycles
- Only then consider limited `fetch_interval_hours` scheduling discussion
- Enabling `SEDI_KB_SCHEDULED_FETCH_ENABLED` requires **separate explicit approval**

---

## Rollback (single source)

1. Set source `ingestion_status=deprecated`
2. Archive documents `status=archived` via admin PATCH
3. Chunks fall out of search (active filter)
4. DB restore only if catastrophic — use pre-population backup

---

## Related files

- Catalog: `backend/config/gate3h/trusted_source_catalog_v1.yaml`
- Risk policy: `backend/docs/gate3h/RISK_AND_APPROVAL_POLICY_V1.md`
- Seed batch: `backend/docs/gate3h/INITIAL_SEED_BATCH_V1.md`
