# Section43 — 100-year retention model (design only)

```text
LONG_TERM_STORAGE_MODEL=PARTIAL
UNLIMITED_RAW_CONVERSATION=FORBIDDEN
```

Do not store unlimited raw chat. Physical HOT/WARM/ARCHIVE tables are a DCR.

| Horizon | HOT | WARM | ARCHIVE |
|---|---|---|---|
| 1 year | last 7–30d chat + active I6 facts + daily I7 | fact history + weekly I7 + events | — |
| 5 years | same HOT window | monthly I7 + event timeline | yearly I7 + superseded facts |
| 10–50–100 years | same HOT window | recent monthly I7 | yearly I7 + compact derived profile (DCR) |

Mapping to current tables (no new schema):

- HOT: `memory` (chat), active `user_memory_facts`, current-day `user_period_summaries`
- WARM: superseded UMF rows, `user_events`, `user_lifestyle_events`, `interaction_events`, weekly/monthly UPS
- ARCHIVE (logical): yearly UPS + UMF history. No dedicated archive store yet.

Prune policy for `memory` chat turns after N days is a DCR (needs explicit retention column/job contract).
Export preparation exists as `export_memory_bundle` (JSON, not a stored artifact).
