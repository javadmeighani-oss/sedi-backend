# DCR-04 Competing fact stacks — APPROVED MODEL

```text
DCR04_DECISION=APPROVE_MODEL
CANONICAL_FACT_OWNER=user_memory_facts
LEGACY_FACT_STACK_DISPOSITION=FREEZE_THEN_NONDESTRUCTIVE_MERGE
MIGRATION_REQUIRED_LATER=YES
DESTRUCTIVE_MERGE_THIS_GATE=NO
IMPLEMENTED=NO
```

Do not merge by name similarity. Valid-time: a later value does not falsify an
earlier period.

## Stack audit

| Table | Owner | Role | Disposition |
|---|---|---|---|
| `user_memory_facts` | I6 | Canonical LTM facts: current + history | KEEP_CANONICAL |
| `user_facts` | legacy GPT KV | current-value only, no valid-time | FREEZE writes; merge to UMF |
| `kc_user_facts` | Knowledge Capture V1 | verified facts with valid_from/to | FREEZE writes; merge to UMF |
| `user_profile_facts` | Gate 1 | identity/profile facts | FREEZE writes; merge to UMF |
| `user_fact_candidates` / `kc_fact_candidates` | staging | not SoT | remain staging; accept path → UMF only |
| `user_profile_core` | Gate 2 identity | demographics/timezone | RETAIN registry; not LTM stack |
| `user_habits` / `user_goals` / `user_restrictions` | Gate 1/2 registries | structured entities | RETAIN; UMF may reference, not replace |

## Concepts (UMF)

- identity: row id + (user_id, domain, key, valid_from)
- type: domain + key
- value: value_json
- valid_from / valid_until (valid_to equivalent)
- source + provenance_class
- confidence
- consent_id
- supersedes_fact_id / fact_status
- correction = new active row + prior superseded (not in-place rewrite)
- deleted_at = soft_invalidated_at + forget
- current truth = active + not expired + not invalidated
- historical truth = all rows including superseded
- contradiction = two active same (domain,key) overlapping valid-time → reject write

## Later work

Use existing `merge_legacy_facts_into_user_memory_facts` in a dedicated Gate:
read-only freeze producers, copy with provenance, never drop conflicts, keep
legacy rows until reconciliation report is green, then read-block legacy.

No medical inference promotion during merge. Diagnosis keys remain blocked.
