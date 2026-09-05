# SEDI Cursor Authoritative Handoff - v728

Managed-subject interactive continuity **design audit only**. Reuse §434/v727 + §435. No implementation.

```
VERSION=v728
STATUS=CURRENT
LOGICAL_PREDECESSOR=v727
v727_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§435
GATE=SEDI-V1-BE-MANAGED-SUBJECT-INTERACTIVE-CONTINUITY-DESIGN-01
GATE_RESULT=PASS
MODE=READ_ONLY_TARGETED_DESIGN_AUDIT
APPROVED_BY=JAVAD
BRANCH=feature/section15/backend-continuity-foundation
HEAD=eb9f875065e1bfd5ec52c7dfdcd604e20685ed08
ALEMBIC_HEAD=079_i10_cni_owner_provenance_nullable
SOURCE_MUTATION=NO
CI_TRIGGERED=NO
```

## Frozen Stage B status (unchanged)

I1/I2/I7/I8=PARTIAL  
MOTHER_CHAT_HEALTH_SUBJECT_TARGET_SUPPORT=PARTIAL  
MOTHER_ACCOUNTLESS_I7_SUPPORT=NOT_IMPLEMENTED

## Current truth (compact)

- Chat actor = JWT Account only (`interact.py` + `ChatRequest`, `extra=forbid`)
- No `target_health_subject_id` on chat contract
- I1/I2 Account-scoped; adapters user_id-keyed
- No Conversation table; `Memory.user_id` NOT NULL; no HS column on I7 tables
- Notif continuation: `source_notification_id` + recipient Account; `Notification.health_subject_id` for access revalidation only — does **not** become chat target
- AHSA sufficient for ACCESS; UserConsent Account-only; NotificationPrefs ≠ consent
- I8 MIXED: optional `health_subject_id` on operational path; proactive Account-native

## Recommended design

**OPTION_C_SPLIT (hybrid)** — not Option A alone.

Why: writing Mother chat turns into `Memory.user_id=Son` would contaminate Son SELF memory. Fail-closed durable managed writes until I7 is HealthSubject-native.

### Proposed implementation sequence (unauthorized)

1. `SEDI-V1-BE-HS-TARGETED-CHAT-I1-I2-01` — target HS on chat; I1/I2 authorize via AHSA; notif continuation target survival; fail-closed managed I7 write  
2. `SEDI-V1-BE-I7-HEALTHSUBJECT-NATIVE-MEMORY-01` — additive HS ownership + consent seam + backfill SELF  
3. I8 residual managed compatibility  
4. PG16 cross-I regression  

## Laws preserved

NO_FAKE_MOTHER_ACCOUNT / NO_ACCOUNT_SUBSTITUTION / MANAGER≠OWNER  
I1 orchestration only / I2 assembly only / I8≠I10  

## Open findings (unchanged)

FINDING_S02_FRESHNESS_POLICY  
FINDING_MANAGED_ACCOUNTLESS_MOTHER_I4_B16_CAREGIVER_E2E  
FINDING_RAG_REAL_RUNTIME  
FINDING_FULL_I1_I10_FAMILY_E2E  

Closed preserved: S02 test-rule seam; B15A01 owner provenance.

```
NEXT_GATE_PROPOSAL=SEDI-V1-BE-HS-TARGETED-CHAT-I1-I2-01
NEXT_GATE_AUTHORIZED=NO
FRONTEND_FINAL_REDESIGN_ALLOWED_NOW=NO
```
