# Release Stage 17.5 – Local RAG v1

Local RAG layer that retrieves only from Sedi's internal stores. Gated by feature flags. No external retrieval.

---

## Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_LOCAL_ENABLED` | false | Enable Local RAG. When false, no retrieval; existing flows unchanged. |
| `RAG_LOCAL_TOP_K` | 6 | Max number of chunks to return. |
| `RAG_LOCAL_MAX_CHARS` | 1200 | Total character budget for combined_text. |

---

## Data Sources Used

- **UserFact** – Key-value facts per user
- **UserMemoryFact** – Lifestyle, routines, goals, preferences
- **DailyMemorySummary** – Last 7 days
- **Memory** – Last 10 chat turns (user messages only)
- **UserProfileKnowledge** – Baseline, goals, preferences
- **UserFactCandidate** – Accepted candidates (optional)

---

## Retrieval Strategy (v1)

- **Keyword scoring**: Overlap of normalized tokens (no embeddings).
- **Ranking**: By score descending; take top K chunks.
- **Truncation**: Each chunk capped; total combined_text capped by `RAG_LOCAL_MAX_CHARS`.
- **Output**: `RetrievalResult` with `chunks`, `combined_text`, `sources` (source anchors).

---

## Source Anchors

Matches Lifestyle sources format (Stage 17.3):

```
{ type, id, label, ts? }
```

Types: `user_fact`, `user_memory_fact`, `daily_summary`, `memory_turn`, `user_profile_knowledge`, `candidate_fact`.

---

## Wiring

- **Lifestyle summary** (`summary_service.py`): When `RAG_LOCAL_ENABLED=true`, retrieves with query "lifestyle summary" and enriches Recent patterns; merges sources. Facts unchanged.
- **Chat** (`brain.py`): When enabled, appends `[LOCAL_CONTEXT]` block to GPT prompt (bounded). Optional; no change when disabled.

---

## Limitations

- No embeddings or vector store in v1.
- Simple keyword overlap only.
- No semantic similarity.

---

## Upgrade Path

Future versions can:
- Add embeddings and a vector store.
- Use semantic search for retrieval.
- Keep source anchors for explainability.

---

## Safety Notes

- No sensitive text in logs.
- Token budget is deterministic and bounded.
- Default flags keep RAG disabled; no behavior change without explicit opt-in.
