# SEDI Cursor Authoritative Handoff - v817

A3 Smart Notifications G10 — vital **context/confirmation authority audit** (read-only). Append-only after v816 / Master Log §518.

```
VERSION=v817
STATUS=CURRENT
LOGICAL_PREDECESSOR=v816
MASTER_LOG=§519
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G10-I9-VITAL-CONTEXT-CONFIRMATION-AUTHORITY-AUDIT-AND-DESIGN-01
GATE_RESULT=PASS
MODE=FAST_READ_ONLY_AUDIT
RUNTIME_MUTATION=NO
NUMERIC_POLICY_APPROVED=NO
CAN_PROCEED_DIRECTLY_TO_NUMERIC_POLICY_SIGNOFF=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Preflight

- HEAD `634918c3` = remote; worktree clean; Alembic single head `085`

## Six-question authority matrix

| Q | Topic | STATUS | SOURCE_OF_TRUTH | MINIMUM_MISSING_CONTRACT | Disposition |
|---|---|---|---|---|---|
| 1 | HR rest/activity/sleep | MISSING | NONE (steps/inactivity ≠ vital resting state) | Observation-scoped activity class: rest\|activity\|sleep | MINIMAL_NEW_CONTRACT |
| 1b | Medication context for HR | PARTIAL | `medications` / `user_medications` / `medication_dose_occurrences` (adherence only) | Vital-observation-linked medication-effect context | EXTEND_EXISTING |
| 2 | Symptom context | PARTIAL | `health_symptom_reports` + Gate3 `health_care_services` (user-scoped manual) | Subject/time-bound symptom state linked to vital observation | EXTEND_EXISTING |
| 3 | Altitude for SpO2 | MISSING | NONE | Authoritative elevation/altitude fact for subject/observation | MINIMAL_NEW_CONTRACT |
| 4 | Temp site/method | MISSING | NONE (`HealthData`/`PhysiologicalMeasurement` lack site/method) | Measurement site/method on temperature observation | MINIMAL_NEW_CONTRACT |
| 5 | HealthData quality | MISSING | NONE on `HealthData` (PM `quality_state` is device-path only) | Governed quality/validity for legacy HealthData observations | EXTEND_EXISTING |
| 6 | Vital repeat/confirmation | MISSING | NONE for vitals (`confirmation_source` is medication-dose only; G8 confirmation_windows deferred) | Vital repeat/confirmation window authority | MINIMAL_NEW_CONTRACT |

## Coherence (preserved)

- I9 = vital fact + governed interpretation
- I10 = notification/interruption only
- Flutter = presentation
- Gadget SELF/OTHER ≠ HealthSubject identity

## Fast path

**CAN_PROCEED_DIRECTLY_TO_NUMERIC_POLICY_SIGNOFF=NO**

Smallest blockers before numeric signoff: (1) activity context, (2) observation-linked symptoms, (3) altitude, (4) temp method, (5) HealthData quality, (6) vital confirmation. Prefer EXTEND symptom/quality/med where tables exist; avoid extra tables unless unavoidable.

```
REPOSITORY_BASELINE=634918c398a19ea8f39ad8ededc63320cb94e0ac
CODE_HEAD=7f1ed0d1a371855e80e717c44c5f10bc07b5801f
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v817_FA.md
```
