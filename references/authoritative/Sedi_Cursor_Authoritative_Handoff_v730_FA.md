# SEDI Cursor Authoritative Handoff - v730

I9/I10 nonclinical vital **stability contract** — governed **semantic hard-stop**. Reuse §436/v729. No source/test/schema mutation.

```
VERSION=v730
STATUS=CURRENT
LOGICAL_PREDECESSOR=v729
v729_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§437
GATE=SEDI-V1-BE-I9-I10-NONCLINICAL-VITAL-STABILITY-CONTRACT-01
GATE_RESULT=HARD_STOP_SEMANTIC_RULE_REAPPROVAL_REQUIRED
DECISION=B
MODE=AUTHORIZED_MULTI_STAGE_STAGE0_2_ONLY
APPROVED_BY=JAVAD
BRANCH=feature/section15/backend-continuity-foundation
HEAD=37f2cfb94061b55699370d483567fb47b3f8a39c
ALEMBIC_HEAD=079_i10_cni_owner_provenance_nullable
SOURCE_MUTATION=NO
TEST_MUTATION=NO
SCHEMA_MUTATION=NO
CI_TRIGGERED=NO
```

## Why hard-stop

Repo has heart_rate personal baseline + MAD + quality + daily `avg_value` + B14 data-status/DATA_GAP, but **no governed rule** that defines NONCLINICAL_STABLE vs NONCLINICAL_CHANGED without a new product boundary (e.g. N×MAD). Direction-only above/below must not become UNSTABLE. Cursor must not invent N / % / BPM.

## Stage 1 facts

| Item | Truth |
|---|---|
| SIGNAL_SCOPE | heart_rate only |
| DAILY_COMPARISON_STATISTIC | daily rollup `avg_value` |
| BASELINE / DISPERSION / QUALITY | YES on bounded projection |
| EXISTING_CHANGE_RULE | NO |
| NEW_ARBITRARY_THRESHOLD_REQUIRED | YES |
| MANAGER_FLEET_SCAN_GAP | YES (scan CAREGIVER-only; recipients already include MANAGER) |
| SCHEMA_CHANGE_REQUIRED | NO for app vocabulary |

## Product Owner must choose

1. **MAD_BAND_ESTABLISHED_ONLY** (recommended nonclinical shape) — approve **N** and whether daily stat is avg vs daily median; MAD=0 + PROVISIONAL fail-closed
2. **DEFER_STABLE_CHANGED** — digest + DATA_GAP only; optional separate MANAGER scan Gate
3. **EXACT_EQUALITY_ONLY_STABLE** — no multiplier; weak STABLE emission

`CLINICAL_THRESHOLD_REQUIRED=NO`

## Not done this Gate

MANAGER fleet-scan fix, STABLE/CHANGED implementation, migration 080, clinical rules, Mother Chat/I7.

```
NEXT_GATE_PROPOSAL=SEDI-V1-BE-I9-I10-NONCLINICAL-VITAL-STABILITY-CONTRACT-02
ALT_TINY_GATE=SEDI-V1-BE-I10-DIGEST-FLEET-SCAN-MANAGER-01
NEXT_GATE_AUTHORIZED=NO
FRONTEND_FINAL_REDESIGN_ALLOWED_NOW=NO
```
