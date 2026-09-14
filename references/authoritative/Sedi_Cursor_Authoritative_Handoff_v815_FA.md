# SEDI Cursor Authoritative Handoff - v815

A3 Smart Notifications G8 — I9 absolute vital policy **schema scaffold only**. Append-only after v814 / Master Log §516.

```
VERSION=v815
STATUS=CURRENT
LOGICAL_PREDECESSOR=v814
MASTER_LOG=§517
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G8-I9-ABSOLUTE-VITAL-POLICY-SCHEMA-SCAFFOLD-01
GATE_RESULT=PASS
MODE=DELTA_ONLY_IMPLEMENTATION
SCHEMA_FOUNDATION_ONLY=YES
NUMERIC_POLICY_STATUS=NOT_APPROVED
RUNTIME_INTERPRETER_AUTHORIZED=NO
PRODUCTION_ACTIVATION_AUTHORIZED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Preflight

- Baseline HEAD `c148a385` → code `e1c18371`
- Alembic previous head: `084_device_category_setup_code_authority`
- Alembic G8 head: `085_i9_absolute_vital_policy_schema_scaffold` (single head)

## Tables created (exactly 3)

| Table | Purpose | Key constraints |
|---|---|---|
| `i9_absolute_vital_policies` | Versioned policy authority | UNIQUE(policy_key, version) |
| `i9_absolute_vital_policy_rules` | Generic child rules | FK policy ON DELETE CASCADE |
| `i9_absolute_vital_alert_results` | Future ABSOLUTE_VITAL_ALERT_STATUS | UNIQUE(occurrence_key); FK subject RESTRICT; FK policy RESTRICT; FK rule SET NULL; FK physiological_measurement SET NULL |

`confirmation_windows` **not** created. HealthData / physiological_measurements columns **unchanged**.

## Safety

- POLICY/RULE/RESULT rows seeded by migration: **0**
- Numeric thresholds stored: **NO**
- Interpreter / I10 absolute producer / legacy emit changes: **NO**
- Runtime consumers of new tables outside models: **none** (static scan)

## Tests

- `test_a3_g8_i9_absolute_vital_policy_schema_scaffold.py` — 8 passed (static + PG upgrade/downgrade/re-upgrade + FK/uniqueness)
- Related: G2 bypass + G3 vitals authority — 17 passed
- Harness `ALEMBIC_HEAD` advanced to 085; G1 083↔084 cycle assertion updated for successor head

## Remaining gaps (not G8)

- G9: shadow interpreter (nonnumeric gates only)
- G10: numeric PO signoff (separate)
- Later: I10 absolute producer + legacy suppress/retire
- HealthData → I9 observation adapter (schema freeze in G8)
- Missing context authorities (rest/activity/sleep/symptoms/altitude)

```
CODE_COMMIT=e1c18371da84ed6cd044ff9445d184b9c715745c
PRODUCT_CODE_PREVIOUS=9a4f1f0408e670eb3b13f2d2b92d1e6eaca559c1
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v815_FA.md
```
