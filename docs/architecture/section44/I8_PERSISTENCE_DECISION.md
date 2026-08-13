# I8 persistence architecture — DEFERRED for V1/Pilot

```text
I8_DCR_DECISION=PERSISTENCE_DEFERRED
I8_PERSISTENCE=DEFERRED
V1_EPHEMERAL_ONLY=YES
PILOT_PERSISTENCE_MANDATORY=NO
I8_IS_RAG=NO
IMPLEMENTED=NO
```

Section42 shipped ephemeral fail-closed `plan_nutrition` via
`retrieve_knowledge_context` (service boundary, not vector tables).

## V1 needs

V1/Pilot can ship without persisted meal plans. Safety does not require storing
plans. Offline/mobile can cache the last ephemeral payload client-side.

Canonical if later persisted:

- generated plan = draft
- **accepted plan** = user-owned historical artifact
- applicability snapshots = derived from I6 facts + I5 ELIGIBLE knowledge ids
- user edits/feedback = events on the accepted plan
- knowledge change does **not** rewrite history; old plans stay historical with
  `knowledge_snapshot_ids` + `knowledge_status_at_generation`
- revocation/staleness of source knowledge marks plan `knowledge_stale` for
  *future* use, not silent deletion of history
- substitutions/revisions = new version, prior superseded

## Later schema (not this Gate, not V1-mandatory)

- `user_nutrition_plans` (id, user_id, status draft|accepted|superseded|stale,
  plan_json, knowledge_ref_json, i6_fact_ids_json, generator_version,
  created_at, accepted_at)
- optional `user_nutrition_plan_feedback`
- do **not** create `user_clinical_feature_index` until a clinical I8 Gate;
  that table is high medical-safety risk (must not become diagnosis storage)

Retention: accepted plans WARM 5y BASE then ARCHIVE; drafts HOT 30d.

I8 never queries `knowledge_chunk_embeddings` / pgvector directly.
RAG not required for correctness. Do not promote knowledge here.

PRODUCTION_I8_ACTIVATION=NO
