# SEDI Cursor Authoritative Handoff - v820

A3 Smart Notifications G13 — persist authoritative vital context into G12 table + shadow load. Append-only after v819 / Master Log §521.

```
VERSION=v820
STATUS=CURRENT
LOGICAL_PREDECESSOR=v819
MASTER_LOG=§522
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G13-I9-VITAL-CONTEXT-INGRESS-AND-PERSISTENCE-MINIMAL-01
GATE_RESULT=PASS
MODE=FAST_DELTA_IMPLEMENTATION
SCHEMA_CHANGED=NO
MIGRATION_CREATED=NO
ALEMBIC_HEAD=086_i9_vital_observation_context_authority
NUMERIC_POLICY_AUTHORIZED=NO
CLINICAL_INTERPRETER=NO
I10_ABSOLUTE_PRODUCER=NO
NOTIFICATION_BEHAVIOR_CHANGED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Persistence

- Service: `vital_observation_context_persistence.py`
- Table: existing `i9_vital_observation_contexts` (G12 / Alembic 086)
- Idempotent by `occurrence_key`; subject/source mismatch → fail closed
- Prefer no row when all context fields unknown and no useful provenance

## Wired sources

| Field | Status |
|-------|--------|
| PM `quality_state` | CONNECTED (same PM only; device_packet ingress) |
| HealthData quality | UNKNOWN (no transfer from PM) |
| activity / altitude / temp_method | SOURCE_NOT_AVAILABLE |
| confirmation | NOT_IMPLEMENTED / UNKNOWN |
| symptoms | EXPLICIT_ONLY; ±24h heuristic stays UNKNOWN+PARTIAL |
| medication | OPTIONAL_PARTIAL |

## Shadow

G9/G11 shadow eligibility may load persisted context for nonclinical blockers only.
Known PM quality may clear `BLOCKED_MEASUREMENT_QUALITY`.
`BLOCKED_POLICY_NOT_APPROVED` always remains while `NUMERIC_POLICY_AUTHORIZED=False`.

## Tests

G13 + G11 + G9 + G12: 25 passed

```
CODE_COMMIT=7724d7133227b271bfcd872fbc25e05e863e4e6c
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v820_FA.md
```
