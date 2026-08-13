# DCR-01 Compact lifelong profile — APPROVED MODEL

```text
DCR01_DECISION=APPROVE_MODEL
DCR01_TARGET_MODEL=PERSISTED_DERIVED_MATERIALIZED_PROJECTION
DCR01_SCHEMA_CHANGE_REQUIRED=YES
IMPLEMENTED=NO
LONG_TERM_PROFILE_IS_NOT_INDEPENDENT_TRUTH=YES
LONG_TERM_PROFILE_IS_NOT_CLINICAL_TRUTH=YES
```

## What it represents

A compact, rebuildable companion portrait: habits, preferences, successful/failed
approaches, communication style, long-term trends. It is a cache of understanding,
not a second biography.

## Canonical vs derived

Canonical: `user_memory_facts` (I6), consented structured registries
(`user_profile_core`, `user_habits`, `user_goals`, `user_restrictions`),
domain events.

Derived: `user_lifelong_profiles` row(s). Must be reproducible from canonical
inputs + `generator_version`.

## Target entity (later Gate only)

`user_lifelong_profiles`

- `id` PK
- `user_id` FK users ON DELETE CASCADE
- `version` int
- `status` active|superseded|stale|invalidated
- `structured_profile_json` text (habits, preferences, interventions, trends)
- `narrative_compact` text nullable
- `source_fact_ids_json` text
- `source_event_refs_json` text
- `consent_id` FK user_consents SET NULL
- `generator_version` text
- `built_from_period_start/end` timestamptz
- `created_at` / `superseded_at`
- UNIQUE (user_id, version)
- INDEX (user_id, status)

Lifecycle: rebuild → insert new version → mark prior active superseded.
Invalidation: I6 correction/deletion/forget/consent revoke → status=stale then rebuild
or drop. Deletion: user delete cascades; forget clears JSON or tombstones version.

Provenance: every field traces to fact id or event ref. No diagnosis keys.
Conflicting history: profile stores *current compact view* plus pointers; valid-time
history stays on UMF (`valid_from`/`valid_until`). 2026 vegetarian=false and 2032
vegetarian=true remain both historically true; profile current value is 2032.

Deterministic rebuild: same inputs + generator_version → equivalent JSON
(sorted keys).

Not in profile: raw chat, high-frequency vitals, scientific knowledge, other users.

Privacy: user-scoped, consent-gated read/write, no cross-user, no PHI vector merge.

Rollback: DROP TABLE; summaries/facts unchanged.
