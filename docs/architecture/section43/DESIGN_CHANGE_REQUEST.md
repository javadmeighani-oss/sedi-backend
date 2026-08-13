# DESIGN_CHANGE_REQUEST — Section43 lifelong memory gaps

```text
GATE=SEDI-V1 SECTION43
STATUS=RECORDED_NOT_IMPLEMENTED
SCHEMA_CHANGE_REQUIRED=YES
MIGRATION_REQUIRED=YES
IMPLEMENTED=NO
```

Protected changes this Gate must not make:

## DCR-01 Compact long-term user profile
- Current: no compact derived profile table. Habits/goals/restrictions exist as Gate-2 rows; I7 yearly JSON is compression only.
- Problem: 50–100 year continuity needs a reconstructable compact profile without scanning all facts.
- Proposed: derived `user_lifelong_profile` (versioned, I6-sourced, not SoT).
- Ownership: I7 derived / I6 remains SoT.
- Privacy/security: user-scoped, consent-gated, no cross-user, no scientific merge.
- Medical safety: must not store diagnosis; HISTORY_IS_NOT_DIAGNOSIS.
- Migration/rollback: additive table; drop on rollback; no backfill of inferred clinical state.

## DCR-02 Physical HOT/WARM/ARCHIVE + chat prune
- Current: all memory rows live in primary tables; `memory` chat has no prune.
- Problem: 100-year raw conversation is forbidden and unbounded.
- Proposed: retention_until / archive job + optional archive schema.
- Ownership: I7 retention.
- Rollback: keep HOT only; do not auto-delete without user policy.

## DCR-03 Memory export artifact store
- Current: `export_memory_bundle` is ephemeral JSON.
- Problem: durable export/delivery/audit needs object storage + receipt table.
- Proposed: export job + artifact metadata table.

## DCR-04 Competing fact stacks
- Current: `user_facts`, `kc_user_facts`, `user_profile_facts` vs canonical `user_memory_facts`.
- Problem: multiple SoT candidates.
- Proposed: read-only freeze + merge into UMF (already DB-03 intent). No new clinical inference.

## DCR-05 Unified lifelong event timeline
- Current: events split across several tables.
- Problem: “user life story” requires a governed union, not a new clinical graph.
- Proposed: SQL view or projection table with source provenance. View-only preferred.

None of the above is implemented in this Gate.
