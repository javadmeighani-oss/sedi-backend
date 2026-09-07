# SEDI Cursor Authoritative Handoff - v748

Device-reported vital status canonicalization — **PASS**. Do not modify v747 / §454.

```
VERSION=v748
STATUS=CURRENT
LOGICAL_PREDECESSOR=v747
v747_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§455
GATE=SEDI-V1-BE-I9-I10-DEVICE-REPORTED-VITAL-STATUS-CANONICALIZATION-01
SCENARIO_ID=SEDI-V1-REAL-FAMILY-CARE-E2E-01
GATE_RESULT=PASS
OFFICIAL_CERT_TOTAL=104
OFFICIAL_COMPLETED=22
OFFICIAL_REMAINING=82
REBASELINE_APPLIED=NO
APPROVED_BY=JAVAD
BRANCH=feature/section15/backend-continuity-foundation
START_HEAD=4b47745b2e4603abff1fd21958ae46e858c3976d
IMPLEMENTATION_COMMIT=cc828de5a1d32d56838df7d2a48b9772710804f0
IMPLEMENTATION_FINAL_HEAD=bf908f3737a5bbb71727d034836f987b54f91dbe
DOCS_COMMIT=pending_push
POSTGRESQL_VERSION=16.x (CI pgvector/pgvector:pg16)
ALEMBIC_HEAD=080_i9_device_reported_vital_status
SCHEMA_MUTATION=YES
MIGRATION_MUTATION=YES
MIGRATION_REVISION=080_i9_device_reported_vital_status
SMART_RAG_CHANGED=NO
CLINICAL_RULES_CHANGED=NO
REAL_FCM_CHANGED=NO
PRODUCTION_CHANGED=NO
FRONTEND_CHANGED=NO
FORCE_PUSH=NO
NEXT_GATE_AUTHORIZED=NO
```

## Phase A

```
EXISTING_CANONICAL_ENTITY_REUSABLE=NO
ENTITY=DeviceReportedVitalStatus (new)
WHY=DeviceReportedCardiacEvent is cardiac-event-only; PhysiologicalMeasurement.quality_state is not STABLE|UNSTABLE SoT; JSON/provenance must not be final authority.
```

## Canonical contract

```
INPUT_OBSERVATION_TYPE=device_reported_vital_status
STATUS_VOCABULARY=STABLE|UNSTABLE
SOURCE_CLASS=DEVICE_REPORTED
GADGET_DECIDES_STATUS=YES
BACKEND_RECOMPUTES_STATUS=NO
MAD_PATH_RETAINED_FOR_OTHER_USE=YES
MAD_PATH_MOTHER_GADGET_AUTHORITY_REMOVED=YES
RAG_LLM_IN_STATUS_PATH=NO
ACTIVE_CLINICAL_DEVICE_RULE_COUNT=0
EXPECTED_DEVICE_INTERVAL=UNDECIDED
DATA_GAP_TIMEOUT=UNDECIDED
```

## Delivered

- Migration `080_i9_device_reported_vital_status` → table `device_reported_vital_statuses`
- I9 ingest observation + immutable historical rows; effective status by `detected_at` (out-of-order safe)
- I10 `device_reported_vital_status_producer` transition/dedupe notify via care-network chain
- `care_subject_status_facts` Mother gadget monitoring authority = DEVICE_REPORTED only
- Focused PG16 suite `test_i9_i10_device_reported_vital_status.py` (28+ cases incl. UDU)

## CI (required)

| Suite | Run | Result |
|------|-----|--------|
| DeviceReportedVitalStatus PG16 | 34143229564 / 34144799595 | success |
| Stage B family | 34143229635 / 34144603015 / 34144633226 | success |
| Nonclinical vital stability | 34143885240 | success (after B14 repair) |
| Stage A I1–I10 | 34143885148 | success |
| I10 B15-A02 | 34143885217 | success |
| SCIS-01 | 34143885280 | success |

## Failed CI chronology (recorded)

1. First push head-assert failures (079→080) on B15/I8/SCIS/DB03/KNOW — repaired for impacted workflows
2. Nonclinical/Stage A: `test_baseline_not_clinical_normal` expected MAD `DATA_INSUFFICIENT` — repaired to DEVICE_REPORTED awaiting semantics
3. **OPEN (non-blocking / out-of-required-scope):** DB-03 `34143885145` — 056 synthetic seed uses current Device ORM (`owner_account_user_id`) against 056 schema
4. **OPEN (collateral I5 KNOW):** KNOW-01/05 frozen test head asserts still `068_*`; KNOW-04 unrelated I8 planner persistence string — not DRVS path

## Still open (unauthorized)

1. Smart-RAG activation (vendor/model selected elsewhere; this Gate must not change it)
2. Real FCM
3. Mother Chat HS-target / accountless Mother I7
4. Official 104 remaining packages
5. DB-03 056 ORM seed skew (separate harness gate)
6. I5 KNOW frozen-head test cleanup (separate)

```
BACKEND_READY_FOR_SMART_RAG_GATE=YES
BACKEND_READY_FOR_REAL_FCM_GATE=NO
BACKEND_READY_FOR_FINAL_FREEZE=NO
FRONTEND_UNLOCK=NO
NEXT_GATE_AUTHORIZED=NO
```
