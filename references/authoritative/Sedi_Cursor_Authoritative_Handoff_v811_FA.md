# SEDI Cursor Authoritative Handoff - v811

A3 Smart Notifications G4 — legacy vitals clinical authority **decision audit only**. Append-only successor after v810 / Master Log §512. **RECOMMENDATION_NOT_IMPLEMENTATION.**

```
VERSION=v811
STATUS=CURRENT
LOGICAL_PREDECESSOR=v810
CONTINUITY_BASELINE_CHATGPT=v813
MASTER_LOG=§513
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G4-LEGACY-VITALS-CLINICAL-AUTHORITY-DECISION-01
GATE_RESULT=PASS
MODE=READ_ONLY_DECISION_AUDIT
RUNTIME_MUTATION=NO
PRODUCT_OWNER_FINAL_DISPOSITION_APPROVAL_REQUIRED=YES
LEGACY_NUMERIC_THRESHOLDS_NEWLY_APPROVED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Authority map (unchanged)

- I9 = physiological/device facts + governed interpretation (DRVS STABLE|UNSTABLE; MAD HR stability; device vitals normalization)
- I10 = notification policy / canonical intake (DEVICE_STATUS for evaluate_health_data path post-G2)
- Gate4 = delivery/prefs
- A3 Flutter = presentation only — no vitals thresholds

## Trace summary (evaluate_health_data only)

Source: `models.HealthData` (string vitals) via `POST /health/add` → `DecisionEngine.evaluate_health_data` → `health_alert` payload → `enqueue_self_scheduler_notification` (I10SemanticFamily.DEVICE_STATUS, HEALTH_SENSITIVE) → optional `Notification`; fallback `create_health_alert(health_data_update)` when None.

Parallel **non-I9-equivalent** governed path (out of scope for replacement): device packets → `vitals/rule_alerts.py` (different numeric bands, e.g. HR 50/120, temp 38/39.5) → decision engine executor → I10 health_alert.

## Per-rule disposition (recommendation only)

| Rule | I9 equivalent | Governed clinical evidence for legacy numeric | Recommendation |
|---|---|---|---|
| HR > 100 | NO | NO | GOVERN_UNDER_I9 |
| HR < 60 | NO | NO | GOVERN_UNDER_I9 |
| SpO2 < 95 | NO | NO | GOVERN_UNDER_I9 |
| Temp > 37.5 | NO | NO | GOVERN_UNDER_I9 |

Counts: RETIRE=0, REPLACE_WITH_I9=0, GOVERN_UNDER_I9=4, BLOCKED=0

## Evidence notes

- I9 MAD HR (`nonclinical_vital_stability.py`, `hr_stability.py`, `hr_stability_producer.py`): personal-pattern change vs baseline — **not** single-sample tachycardia/bradycardia at 100/60.
- I9 DRVS (`device_reported_vital_status.py`): gadget-reported STABLE|UNSTABLE only; backend must not recompute from absolute BPM/SpO2/temp.
- Legacy numerics also appear in `medical.py` condition heuristics (insight context) — **not** approved I9 clinical policy; do not treat as governance approval.

## Next gate (not authorized)

Implementation gate after PO approves disposition and any new I9 authority design (without auto-copying 100/60/95/37.5).

```
BACKEND_AUDIT_HEAD=9a4f1f0408e670eb3b13f2d2b92d1e6eaca559c1
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v811_FA.md
```
