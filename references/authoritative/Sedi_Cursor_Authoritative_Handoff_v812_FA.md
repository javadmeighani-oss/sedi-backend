# SEDI Cursor Authoritative Handoff - v812

A3 Smart Notifications G5 — I9 vitals alert authority **architecture design only**. Append-only after v811 / Master Log §513. **DESIGN_NOT_IMPLEMENTATION.**

```
VERSION=v812
STATUS=CURRENT
LOGICAL_PREDECESSOR=v811
MASTER_LOG=§514
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G5-I9-VITALS-ALERT-AUTHORITY-DESIGN-01
GATE_RESULT=PASS
MODE=READ_ONLY_ARCHITECTURE_DESIGN
RUNTIME_MUTATION=NO
NUMERIC_THRESHOLDS_APPROVED=NO
PRODUCT_OWNER_IMPLEMENTATION_APPROVAL_REQUIRED=YES
CLINICAL_POLICY_GATE_REQUIRED=YES
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Preflight

- Branch: `feature/a3-authority-chat-stream-profile-foundation-be` → remote `feature/a3-authority-chat-stream-profile-foundation`
- REPOSITORY_TIP / HEAD: `5c18ee576f871ee3d56338a1284d502ae92fcf56` (docs after product `9a4f1f04`)
- Ahead/behind: 0/0; worktree clean

## 1. Minimal current authority map

### A. Manual/API HealthData
- INPUT= string vitals on `models.HealthData` via `POST /health/add`
- CURRENT_INTERPRETATION_OWNER= `DecisionEngine.evaluate_health_data` (absolute cutoffs)
- OUTPUT= `health_alert` payload + priority
- DOWNSTREAM= I10 `enqueue_self_scheduler_notification` (`DEVICE_STATUS`, `HEALTH_SENSITIVE`)
- AUTHORITY_CLASS= LEGACY_PARALLEL_ABSOLUTE (not I9)

### B. Gadget/device measurements
- INPUT= device events / packets → `vital_registry.validate_event` → normalized payload; I9 path also → `PhysiologicalMeasurement`
- CURRENT_INTERPRETATION_OWNER= split: RAW persist I9 (`device_packet_service`); absolute alerts `vitals/rule_alerts.compute_alert_actions`; DRVS separate
- OUTPUT= normalized numeric + optional `CreateHealthAlertAction`
- DOWNSTREAM= Decision Engine executor → notification_engine / I10 health_alert
- AUTHORITY_CLASS= RAW_FACT (I9) + LEGACY_PARALLEL_ABSOLUTE (rule_alerts)

### C. I9 MAD / personal HR stability
- INPUT= subject HR series + baseline MAD
- CURRENT_INTERPRETATION_OWNER= I9 (`nonclinical_vital_stability` / `hr_stability`)
- OUTPUT= NONCLINICAL_STABLE | CHANGED | DATA_INSUFFICIENT (canonical HR stability)
- DOWNSTREAM= I10 `hr_stability_producer` (DEVICE_STATUS family; not absolute BPM bands)
- AUTHORITY_CLASS= PERSONAL_BASELINE_DEVIATION

### D. I9 DEVICE_REPORTED STABLE|UNSTABLE
- INPUT= gadget-reported status on packet (not recomputed from BPM)
- CURRENT_INTERPRETATION_OWNER= I9 `device_reported_vital_status` (normalize/persist only)
- OUTPUT= STABLE | UNSTABLE row
- DOWNSTREAM= I10 `device_reported_vital_status_producer`
- AUTHORITY_CLASS= DEVICE_REPORTED_STATUS

### E. vitals/rule_alerts.py absolute rules
- INPUT= normalized device vitals (HR/BP/glucose/temp; **no SpO2**)
- CURRENT_INTERPRETATION_OWNER= `rule_alerts` (hardcoded bands e.g. HR 50/120/40/160; temp 38/39.5)
- OUTPUT= CreateHealthAlertAction
- DOWNSTREAM= Decision Engine → health_alert persistence
- AUTHORITY_CLASS= LEGACY_PARALLEL_ABSOLUTE

### F. evaluate_health_data absolute rules
- INPUT= HealthData HR/SpO2/temp strings
- CURRENT_INTERPRETATION_OWNER= notification_engine evaluate_health_data (100/60/95/37.5)
- OUTPUT= health_alert via I10 self adapter
- DOWNSTREAM= I10 DEVICE_STATUS
- AUTHORITY_CLASS= LEGACY_PARALLEL_ABSOLUTE

### G. I10 DEVICE_STATUS / HEALTH_SENSITIVE
- INPUT= already-interpreted payloads / I9 DRVS / MAD results / legacy health_alert
- CURRENT_INTERPRETATION_OWNER= I10 intake/policy only (must not own thresholds)
- OUTPUT= Notification candidate / suppress
- DOWNSTREAM= Gate4 delivery
- AUTHORITY_CLASS= NOTIFICATION_POLICY

**PARALLEL_CLINICAL_AUTHORITY_CURRENTLY_EXISTS=YES** (evaluate_health_data ≠ rule_alerts bands; both ≠ I9 MAD/DRVS).

## 2. Canonical I9 model (four kinds — do not collapse)

| Kind | Owner | Allowed sources | Forbidden |
|---|---|---|---|
| 1. RAW/OBSERVED VITAL FACT | I9 fact store / adapters | Device packet → PhysiologicalMeasurement; manual HealthData (adapter) | I10/Flutter reinterpretation |
| 2. PERSONAL_BASELINE_DEVIATION | I9 MAD/HR stability (existing) | Subject-scoped series + baseline | Treating as absolute clinical alert |
| 3. DEVICE_REPORTED_STATUS | I9 DRVS (existing) | Gadget-reported STABLE\|UNSTABLE only | Backend recomputation from vitals |
| 4. ABSOLUTE_VITAL_ALERT_STATUS | **I9 absolute-policy interpreter (new authority)** | RAW fact + **governed policy version** | evaluate_health_data; rule_alerts; I10; Flutter |

Boundary: I9 = facts + governed interpretation; I10 = interruption/notification; Gate4 = delivery; Flutter = presentation.

## 3. Provenance inputs (HR / SpO2 / temperature) — classify only

| Capability | Device path | Manual HealthData |
|---|---|---|
| metric | EXISTING (`measurement_type` / event_type) | EXISTING (column names) |
| normalized value | EXISTING (`numeric_value` / registry) | DERIVABLE_FROM_EXISTING_AUTHORITY (parse string) |
| unit | EXISTING on PhysiologicalMeasurement | MISSING_CONTRACT (implicit) |
| measured_at | EXISTING | PARTIAL→MISSING_CONTRACT (only `created_at`) |
| source_class | DERIVABLE / EXISTING patterns (DEVICE_*) | MISSING_CONTRACT (manual/API) |
| gadget/device identity | EXISTING | N/A / MISSING if claimed device |
| account/user | EXISTING | EXISTING (`user_id`) |
| health_subject_id | EXISTING | MISSING_CONTRACT |
| provenance/evidence ref | EXISTING (packet provenance / idempotency) | MISSING_CONTRACT |
| data-quality/validity | EXISTING (`quality_state`) | MISSING_CONTRACT |

## 4. Absolute alert policy design

```
ABSOLUTE_POLICY_OWNER=I9
POLICY_VERSIONING_REQUIRED=YES
CLINICAL_EVIDENCE_REQUIRED=YES
SOURCE_SPECIFIC_POLICY_ALLOWED=CONDITIONAL
```

RATIONALE: One I9-owned versioned policy authority prevents accidental duplicate bands (`100/60/95/37.5` vs `50/120` / `38/39.5`). Source-specific bands allowed **only** when an explicit governed policy version documents justification; never as parallel code owners. evaluate_health_data, rule_alerts, I10, and Flutter must not hold thresholds. Numerics are **not** chosen or approved in this gate.

## 5. Canonical I9 → I10 output (conceptual; no new enums invented here)

Minimum result I10 consumes without recomputing vitals:

| Attribute | Contract status |
|---|---|
| metric | EXISTING_CONTRACT (vocab heart_rate/spo2/temperature) |
| status/fact kind = ABSOLUTE_VITAL_ALERT_STATUS | MISSING_CONTRACT |
| severity/risk class (map to notify priority later) | PARTIAL — priority strings exist on notifications; governed absolute severity contract MISSING |
| source/provenance | EXISTING for device; MISSING unified for manual |
| health_subject attribution | EXISTING device; MISSING manual HealthData |
| evidence/policy reference (policy_version_id) | MISSING_CONTRACT |
| event timestamp | EXISTING device measured_at; PARTIAL manual |

I10: consume I9 absolute result → DEVICE_STATUS / HEALTH_SENSITIVE policy only.

## 6. Legacy retirement map (design only)

| Path | Future disposition |
|---|---|
| evaluate_health_data absolute rules | MOVE_INTERPRETATION_TO_I9 → RETIRE_AFTER_I9_REPLACEMENT; KEEP_AS_SOURCE_ADAPTER for HealthData ingress + I10 enqueue of **I9 result** |
| vitals/rule_alerts.py absolute rules | MOVE_INTERPRETATION_TO_I9 → RETIRE_AFTER_I9_REPLACEMENT; KEEP_AS_SOURCE_ADAPTER only if reduced to pass-through after I9 (prefer retire interpreter entirely) |

### Safe migration sequence (no gap / no double alert)

1. **Clinical policy gate** — PO + evidence approve a versioned absolute policy (or explicitly defer activation). Numerics not inventable by Cursor.
2. **I9 absolute interpreter** — evaluate RAW facts against policy version; emit ABSOLUTE_VITAL_ALERT_STATUS result (shadow/log mode OK).
3. **I10 consumer** — new producer path consumes I9 absolute result only (no threshold math).
4. **Dual-run suppress** — when I9 absolute fires for same subject/metric/window, suppress legacy evaluate_health_data and rule_alerts emits (or reverse: legacy muted first for covered metrics only after I9 live).
5. **Retire** hardcoded bands from evaluate_health_data and rule_alerts.
6. **Never** retire legacy numerics before step 1–4 for that metric (alert gap).

## 7. Schema / API

```
IMPLEMENTABLE_WITH_CURRENT_SCHEMA=PARTIAL
SCHEMA_CHANGE_REQUIRED=YES
API_CONTRACT_CHANGE_REQUIRED=YES
```

Missing capabilities (describe only; no SQL): durable ABSOLUTE_VITAL_ALERT_STATUS / policy_version authority; HealthData→health_subject + unit/quality/provenance alignment; I10 producer contract for absolute I9 results; SpO2 absolute path absent from rule_alerts today.

## 8. Clinical governance blockers

```
CAN_IMPLEMENT_AUTHORITY_WITHOUT_APPROVING_NUMERIC_THRESHOLDS=YES
CAN_RETIRE_LEGACY_NUMERICS_BEFORE_GOVERNED_REPLACEMENT=NO
CLINICAL_POLICY_GATE_REQUIRED=YES
LEGACY_100_60_95_37_5_APPROVED=NO
DEVICE_50_120_38_39_5_APPROVED=NO
```

Scaffolding (contracts, adapters, shadow evaluation hooks) may be designed without approving cutoffs; **activation and retirement** require governed policy.

## Recommended next gates (not authorized)

1. Clinical policy / evidence gate for absolute vitals (PO)
2. Then implementation: I9 absolute authority + I10 consumer + dual-run suppress + retire legacy interpreters

```
PRODUCT_CODE_HEAD=9a4f1f0408e670eb3b13f2d2b92d1e6eaca559c1
REPOSITORY_BASELINE=5c18ee576f871ee3d56338a1284d502ae92fcf56
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v812_FA.md
```
