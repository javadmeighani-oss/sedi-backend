# DCR-05 Unified lifelong event timeline — APPROVED MODEL

```text
DCR05_DECISION=APPROVE_MODEL
DCR05_TARGET_MODEL=SERVICE_AGGREGATION_PLUS_OPTIONAL_SQL_UNION_VIEW
SCHEMA_CHANGE_REQUIRED_LATER=YES
DUPLICATED_CANONICAL_EVENT_TABLE=NO
IMPLEMENTED=NO
```

Sedi can reconstruct longitudinal history without copying every event into a
second SoT table. Domain tables remain owners.

## Sources (preserve ownership)

- `user_events` — life/care calendar
- `user_lifestyle_events` — lifestyle
- `interaction_events` — product interactions
- `care_episodes` / care tasks — care
- `notification_feedback` — feedback
- `device_events` / `physiological_measurements` — device/vitals (HOT/WARM, not 100y raw)
- I6 fact status changes — memory changes (derived from UMF history, not a copy)
- I8 plans — none until I8 persistence exists

## Target read model

Optional `user_lifelong_timeline` **VIEW** (not materialized, not writable):

UNION ALL of projected columns:

- event_id (typed: `lifestyle:123`)
- user_id
- event_family
- event_type
- occurred_at
- recorded_at
- source
- provenance_ref
- timezone
- privacy_class
- source_table

Service `list_lifelong_timeline(user_id, from, to)` applies consent, user
isolation, and HOT/WARM filters. Prefer service-first if the view migration is
deferred; view is the SQL contract.

Required properties are projected, not re-owned.

Indexes later only on source tables if missing (occurred_at/user_id). No new
central event heap.

Deletion: source row delete/soft-invalidate disappears from the view.
Privacy: view must not leak other users; always filter user_id in service.
