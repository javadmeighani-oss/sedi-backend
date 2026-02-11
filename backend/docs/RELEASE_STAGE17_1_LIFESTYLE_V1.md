# Release Stage 17.1 – Lifestyle Intelligence v1

Controlled, production-grade Lifestyle Intelligence for Sedi.

---

## Scope

### Domains (v1 only)

| Domain | Description | Keys |
|--------|-------------|------|
| sleep | Sleep duration, quality, bedtime, wake time | sleep_duration_hours, sleep_quality, bedtime, wake_time |
| activity | Exercise and steps | activity_level, steps_count, exercise_minutes |
| medication | Medication adherence (only when user explicitly states) | medications |
| mood | Mood/mental wellbeing (explicit, non-diagnostic) | mood, stress_level |

Everything else is ignored.

---

## Candidate Fact Pipeline

1. **Extraction**: `extract_candidates_from_turn(user_id, user_message, assistant_message, language)`  
   - Deterministic regex patterns first (en/fa/ar).  
   - Optional AI assist when `LIFESTYLE_AI_EXTRACT=true` (default false).

2. **Storage**: Candidates stored in `user_fact_candidates` with status `pending`.

3. **Auto-commit rule**:  
   - Only when `is_explicit=true` AND `confidence >= 0.85` AND domain in allowed list.  
   - Committed facts go to `UserMemoryFact` via `MemoryRepository.upsert_fact`.

4. **Admin review**: Pending candidates can be accepted/rejected via admin endpoints.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LIFESTYLE_AI_EXTRACT` | false | Enable AI-assisted extraction (bounded, strict schema) |
| `LIFESTYLE_AI_SUMMARY` | false | Enable AI wording polish for summary (no new facts) |

---

## API

- **GET /lifestyle/summary?user_id=...&lang=en**  
  Returns: `generated_at`, `language`, `sections` (What I know, Recent patterns, Next suggested check-in), `sources_used`.  
  Each section may include optional `sources: [{type, id, label, ts?}]` for explainability (Stage 17.3).

- **GET /lifestyle/admin/candidates?user_id=...&status=pending**  
  Admin: list fact candidates. Requires `X-Admin-Token` if `ADMIN_TOKEN` set.

- **POST /lifestyle/admin/candidates/{id}/decision**  
  Admin: accept or reject candidate. Body: `{"status": "accepted" | "rejected"}`.

- **GET /lifestyle/admin/source_preview?type=...&id=...**  
  Admin: safe preview of a source for debugging and RAG validation. Requires `X-Admin-Token` if `ADMIN_TOKEN` set.  
  Types: `daily_summary`, `user_fact`, `user_memory_fact`, `user_profile_knowledge`, `memory_turn`, `candidate_fact`.

---

## Sources Format (Stage 17.3 – Explainability)

Each section in the summary response may include an optional `sources` array:

```json
"sources": [
  {"type": "user_fact", "id": "42", "label": "sleep_key", "ts": "2026-02-11T12:00:00"},
  {"type": "user_profile_knowledge", "id": "1", "label": "baseline", "ts": "2026-02-10T00:00:00"},
  {"type": "daily_summary", "id": "5", "label": "day_2026-02-10", "ts": "2026-02-10T23:59:59"},
  {"type": "user_memory_fact", "id": "12", "label": "lifestyle/sleep_duration_hours", "ts": null}
]
```

| type | Source table |
|------|--------------|
| `user_fact` | UserFact |
| `user_profile_knowledge` | UserProfileKnowledge (baseline, goals, preferences) |
| `daily_summary` | DailyMemorySummary |
| `memory_turn` | Memory (chat turn) |
| `candidate_fact` | UserFactCandidate |
| `user_memory_fact` | UserMemoryFact |

- `id`: internal numeric/string identifier.
- `label`: short human-readable descriptor (no PHI).
- `ts`: optional ISO timestamp.

**Backward compatibility:** `sources` is optional. Existing clients can ignore it. This format prepares for future `RAGProvider` usage: sources can be resolved via `source_preview` or semantic retrieval over local DB.

---

## RAG Integration (Future)

The existing `RAGProvider` in `notification_runtime` is a placeholder. Lifestyle summary is built locally from:

- UserProfileKnowledge  
- UserMemoryFact  
- UserFact  
- DailyMemorySummary  

Future RAG: `RAGProvider` will support local retrieval first (e.g., semantic search over stored facts). No external retrieval in v1.

---

## Migration

Apply `backend/deployment/migrations/007_stage17_1_user_fact_candidates.sql`.

---

## Related Docs

- `memory_contract.py` — Allowed domains and keys
- `NOTIFICATIONS_V1_FREEZE_GO_NO_GO.md` — Release freeze checklist
