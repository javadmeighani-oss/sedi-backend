# SEDI Cursor Authoritative Handoff - v819

A3 Smart Notifications G12 — **i9_vital_observation_contexts** schema scaffold. Append-only after v818 / Master Log §520.

```
VERSION=v819
STATUS=CURRENT
LOGICAL_PREDECESSOR=v818
MASTER_LOG=§521
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G12-I9-VITAL-CONTEXT-AUTHORITY-SCHEMA-MINIMAL-01
GATE_RESULT=PASS
MODE=FAST_DELTA_IMPLEMENTATION
RUNTIME_CONTEXT_PRODUCER_ADDED=NO
NUMERIC_THRESHOLDS_STORED=NO
SYMPTOM_24H_AUTHORITY=NOT_PROVEN_PARTIAL
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Schema

- Alembic: `085` → `086_i9_vital_observation_context_authority`
- Table: `i9_vital_observation_contexts`
- FK: `health_subject_id` RESTRICT; optional `physiological_measurement_id` / `health_data_id` SET NULL
- Idempotency: UNIQUE(`occurrence_key`); UNIQUE(`source_class`,`source_row_id`,`metric`)
- Nullable context fields = UNKNOWN (row ≠ invented authority)
- No seeds; HealthData / physiological_measurements columns unchanged
- No runtime wiring to G9/eligibility/I10

## Symptom ±24h

G11 `_SYMPTOM_LOOKBACK=24h` is adapter heuristic only — **not** proven pre-existing clinical authority (`NOT_PROVEN_PARTIAL`).

## Tests

G12 + G11 + G9 + G8: 29 passed

```
CODE_COMMIT=fae8feae734dbafc77eac67765a4f0cd1b51da6b
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v819_FA.md
```
