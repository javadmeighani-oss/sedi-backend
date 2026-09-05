# SEDI Cursor Authoritative Handoff - v729

Caregiver gadget monitoring **scope alignment** (read-only). Reuse §435/v728 + §436. No implementation.

```
VERSION=v729
STATUS=CURRENT
LOGICAL_PREDECESSOR=v728
v728_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§436
GATE=SEDI-V1-BE-CAREGIVER-GADGET-MONITORING-SCOPE-ALIGNMENT-01
GATE_RESULT=PASS
MODE=READ_ONLY_TARGETED_SCOPE_ALIGNMENT_AUDIT
APPROVED_BY=JAVAD
BRANCH=feature/section15/backend-continuity-foundation
HEAD=7c91d48a986b691117b693c08722744428e337d4
ALEMBIC_HEAD=079_i10_cni_owner_provenance_nullable
SOURCE_MUTATION=NO
CI_TRIGGERED=NO
```

## V1 product freeze

- **Primary user** = Son Account (full Sedi)
- **Managed relative** = Mother HS ALS, `linked_user_id=NULL`, gadget=YES → **vital-sign monitoring only**
- Mother Chat / Mother I7 = **not V1 blockers**
- Gateway=Son; health data=Mother HS; recipient=Son

## Repo truth

| Capability | Status |
|---|---|
| Mother gadget → I9 attribution | **V1_COMPLETE** |
| STABLE product status | **NO** |
| UNSTABLE non-clinical status | **NO** |
| DATA_GAP | **YES** (B14 CARE_DATA_GAP) |
| I9→I10 status seam | **YES** (CARE_STATUS_DIGEST) |
| Daily Son delivery | **PARTIAL** (`for_subject` OK; fleet scan CAREGIVER-only may miss MANAGER Son) |
| Clinical danger | **NO** (`ACTIVE_CLINICAL_DEVICE_RULE_COUNT=0`) |

Existing facts: `SUFFICIENT_OBSERVED_DATA|PARTIAL|STALE|NO_DATA` + baseline above/below/similar prose — **not** yet STABLE/UNSTABLE product vocabulary.

## Gap reclassification

- Mother Chat / Mother I7 → `V1_NON_BLOCKING_FUTURE_CAPABILITY`
- Son I8 routine/lifestyle PARTIAL → still **primary-user** gap (do not hide)
- Full family E2E → `V1_REQUIRES_REBASELINED_ACCEPTANCE`
- RAG → `SEPARATE_SMART_RAG_GATE`
- S02 freshness / Mother I4×B16 → `SEPARATE_CLINICAL_GOVERNANCE`

## Recommended next Gate (unauthorized)

`SEDI-V1-BE-I10-NONCLINICAL-VITAL-STATUS-CONTRACT-01`

Map existing B14 facts → non-clinical STABLE/UNSTABLE/DATA_GAP user contract; include MANAGER in digest scan; **no clinical thresholds**.

```
NEXT_GATE_PROPOSAL=SEDI-V1-BE-I10-NONCLINICAL-VITAL-STATUS-CONTRACT-01
NEXT_GATE_AUTHORIZED=NO
FRONTEND_FINAL_REDESIGN_ALLOWED_NOW=NO
```
