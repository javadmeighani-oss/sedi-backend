# SEDI Cursor Authoritative Handoff - v731

I9→I10 nonclinical heart-rate MAD-band stability (PO Option 1) — **PASS TRUE-GREEN**.

```
VERSION=v731
STATUS=CURRENT
LOGICAL_PREDECESSOR=v730
v730_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§438
GATE=SEDI-V1-BE-I9-I10-NONCLINICAL-VITAL-STABILITY-CONTRACT-02
GATE_RESULT=PASS
APPROVED_BY=JAVAD
BRANCH=feature/section15/backend-continuity-foundation
HEAD=49ba205d06b3846fdc27868042919c0824b6ac0b
ALEMBIC_HEAD=079_i10_cni_owner_provenance_nullable
SCHEMA_MUTATION=NO
CI_RUN=33968339750
CI_RESULT=SUCCESS
POSTGRESQL=16
PYTEST=95 passed / 0 failed / 0 skipped
```

## PO rule (frozen)

- heart_rate only; daily_median vs ESTABLISHED baseline
- limit = 4.4478 × raw MAD (= 3 × 1.4826 × MAD)
- ≤ limit → NONCLINICAL_STABLE; > → NONCLINICAL_CHANGED
- PROVISIONAL / NONE / MAD=0 / PARTIAL → DATA_INSUFFICIENT
- STALE / NO_DATA → CARE_DATA_GAP (never STABLE)
- STABLE ≠ healthy/safe; CHANGED ≠ danger/diagnosis

## Delivered

- I9: `nonclinical_vital_stability.py` + `compute_daily_median_for_subject`
- I10: consume I9 status in B14 facts/digest metadata/copy
- Fleet scan: CAREGIVER **or** MANAGER (distinct HS)
- Tests: `test_i9_i10_nonclinical_vital_stability.py` + B14/B06/B15-A02 regressions
- Workflow: `.github/workflows/i9-i10-nonclinical-vital-stability-pg16.yml`

## Still open (unchanged)

- Son I8 routine/lifestyle PARTIAL
- Smart-RAG separate
- Clinical danger / I4×B16 / S02 freshness separate

```
NEXT_GATE_AUTHORIZED=NO
FRONTEND_FINAL_REDESIGN_ALLOWED_NOW=NO
```
