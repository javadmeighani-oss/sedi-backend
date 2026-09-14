# SEDI Cursor Authoritative Handoff - v821

A3 Smart Notifications G14 — **numeric + confirmation policy design / PO signoff matrix only**. Append-only after v820 / Master Log §522. **No runtime mutation. Numerics remain unapproved.**

```
VERSION=v821
STATUS=CURRENT
LOGICAL_PREDECESSOR=v820
MASTER_LOG=§523
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G14-I9-VITAL-NUMERIC-AND-CONFIRMATION-POLICY-SIGNOFF-01
GATE_RESULT=PASS
MODE=FAST_READ_ONLY_POLICY_DESIGN
RUNTIME_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CREATED=NO
POLICY_ROWS_CREATED=0
RULE_ROWS_CREATED=0
INTERPRETER_IMPLEMENTED=NO
I10_ABSOLUTE_PRODUCER_IMPLEMENTED=NO
LEGACY_CHANGED=NO
DEPLOY=NO
NUMERIC_POLICY_STATUS=PROPOSED_NOT_APPROVED
CONFIRMATION_POLICY_STATUS=PROPOSED_NOT_APPROVED
PO_SIGNOFF_REQUIRED=YES
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Authority inputs (latest only)

| Source | Role |
|---|---|
| G6 / §515 / v813 | Clinical evidence DRAFT_1 (AHA, FDA, MedlinePlus, NHS/CDC) |
| G7 / §516 / v814 | Nonnumeric policy **APPROVED**; numeric **NOT_APPROVED** |
| G13 / §522 / v820 | Context persistence: PM quality CONNECTED; activity/altitude/temp_method NOT_AVAILABLE; confirmation NOT_IMPLEMENTED; HealthData quality UNKNOWN; symptom ±24h not clinical authority |

Legacy numerics **not authority:** 100/60/95/37.5 ; device 50/120/38/39.5.

## Policy layers (do not merge)

| Layer | Meaning |
|---|---|
| GENERAL_ADULT_DEFAULT | Population absolute bands + required context/confirmation (this gate’s candidate) |
| PERSONAL_BASELINE | I9 MAD / personal deviation — **distinct**; never substitute for absolute cutoffs |
| CLINICIAN_CONFIGURED | Provider floors/ceilings — CONDITIONAL; not hardcoded disease rules |

## Current runtime → fail-closed implications

| Fact | Policy consequence |
|---|---|
| PM quality available | Device path may satisfy quality gate **for that PM only** |
| HealthData quality UNKNOWN | HealthData → **NO_GOVERNED_ALERT** |
| activity UNKNOWN | HR absolute governed alert → **NO_GOVERNED_ALERT** until resting/activity authority exists |
| altitude UNKNOWN | SpO2 absolute governed alert → **NO_GOVERNED_ALERT** until altitude or governed disease-baseline exception |
| temperature_method UNKNOWN | Temp absolute governed alert → **NO_GOVERNED_ALERT** until method/site authority |
| symptoms EXPLICIT_ONLY (±24h heuristic not authority) | SpO2 escalation needing symptoms → fail closed unless explicit observation-linked symptom |
| medication OPTIONAL_PARTIAL | Exception path only; never infer physiological effect |
| confirmation producer absent | All GOVERNED_ALERT → **NO_GOVERNED_ALERT** until confirmation contract + PO numeric version |

```
HEALTHDATA_PATH_ELIGIBLE=NO
PM_PATH_POTENTIALLY_ELIGIBLE=YES   # quality only; still blocked on context/confirmation/numeric approval
```

---

## Heart rate — candidate

**Model (G7 signed nonnumeric):** Absolute + personal-baseline **combined** (C). Absolute never alone on single uncontextualized read.

### A. Numeric bands

| Band | Candidate | STATUS | Evidence |
|---|---|---|---|
| REFERENCE_RANGE (display/education only) | Adult resting commonly ~60–100 bpm | SUPPORTED_CANDIDATE (reference only — **not** notify authority) | AHA (G6) |
| GOVERNED_ALERT absolute BPM cutoffs | Any fixed notify trigger (incl. legacy 100/60) | UNSIGNED_INSUFFICIENT_EVIDENCE | AHA supports context; does **not** map 1:1 to push notify |
| PERSONAL_BASELINE | I9 MAD / resting deviation | Separate contract — not absolute | Existing I9 MAD (nonclinical) |
| CLINICIAN_CONFIGURED | Provider floors/ceilings | UNSIGNED pending product path | G7 CONDITIONAL |

### B–F

| Item | Candidate |
|---|---|
| Required context | Resting **or** explicit activity/sleep state KNOWN (GENERAL_ADULT). Medication inventory may annotate exception; effect never inferred |
| Required quality | YES — PM `quality_state` KNOWN; HealthData → fail closed |
| Confirmation | YES for GOVERNED_ALERT (see Confirmation section) |
| Fail closed | Unknown activity; unknown quality; no confirmation; no PO-approved numeric version; subject mismatch; conflicting confirmed reads |
| Escalation class (concept) | OBSERVE_OR_RECHECK → GOVERNED_ALERT → URGENT_ESCALATION_CANDIDATE (symptom-aware + sustained resting abnormality). No diagnosis labels |

**HR_CONFIRMATION:** REQUIRED=YES for GOVERNED_ALERT; COUNT concept ≥2 valid same-subject same-metric readings; WINDOW=UNSIGNED; conflicting → NO_GOVERNED_ALERT

---

## SpO2 — candidate

**Model (G7):** Context-gated absolute (B). No reference-floor single-read alarm.

### A. Numeric bands

| Band | Candidate | STATUS | Evidence |
|---|---|---|---|
| REFERENCE_RANGE | Often ~95–100% in many healthy individuals | SUPPORTED_CANDIDATE (reference only) | FDA / MedlinePlus (G6) |
| Universal alarm at 95% | — | UNSIGNED_INSUFFICIENT_EVIDENCE (reject as universal notify) | G6: reference ≠ alarm |
| Seek-care guidance examples ≤92 / ≤88 | Home guidance bands only | UNSIGNED_INSUFFICIENT_EVIDENCE for Sedi auto-notify | MedlinePlus examples — **not** auto-Sedi thresholds (G6) |
| PERSONAL_BASELINE / CLINICIAN floor | Provider/disease baseline | UNSIGNED pending governed config | G7 DISEASE_CONTEXT=YES_GOVERNED_ONLY |

### B–F

| Item | Candidate |
|---|---|
| Required context | Quality + repeat; altitude **or** clinician/disease baseline exception; symptoms EXPLICIT for escalation tiers |
| Required quality | YES |
| Confirmation | YES for GOVERNED_ALERT |
| Fail closed | Unknown quality; unknown altitude without clinician exception; heuristic-only symptoms for escalation; no confirmation; no PO numeric version |
| Escalation class | OBSERVE_OR_RECHECK (transient dip) → GOVERNED_ALERT (sustained low + gates) → URGENT_ESCALATION_CANDIDATE (seek-care class + symptoms). No diagnosis wording |

**SPO2_CONFIRMATION:** REQUIRED=YES; COUNT ≥2; WINDOW=UNSIGNED; same-subject+metric; quality acceptable; altitude/context consistent across reads; conflict → fail closed

---

## Temperature — candidate

**Model (G7):** Context-gated, method/site-aware (B).

### A. Numeric bands

| Band | Candidate | STATUS | Evidence |
|---|---|---|---|
| Adult fever reference / candidate absolute | ≥38.0°C (method-aware) | SUPPORTED_CANDIDATE | NHS / CDC (G6) |
| Alternate cutoff 37.8°C | — | UNSIGNED_INSUFFICIENT_EVIDENCE | G6 notes alternate exists; which product cutoff = PO |
| Legacy 37.5°C | — | UNSIGNED_INSUFFICIENT_EVIDENCE (explicitly rejected as evidence-approved) | G6 |
| Device 38 / 39.5 | — | UNSIGNED_INSUFFICIENT_EVIDENCE | Legacy device path — not authority |

### B–F

| Item | Candidate |
|---|---|
| Required context | Measurement site/method KNOWN; symptoms CONDITIONAL for escalation |
| Required quality | YES |
| Confirmation | YES for GOVERNED_ALERT |
| Fail closed | Unknown method/site; unknown quality; no confirmation; no PO numeric version |
| Escalation class | OBSERVE_OR_RECHECK → GOVERNED_ALERT (fever-class + method) → URGENT_ESCALATION_CANDIDATE (fever-class + concerning explicit symptoms). No diagnosis wording |

**TEMP_CONFIRMATION:** REQUIRED=YES; COUNT ≥2; WINDOW=UNSIGNED; same method preferred — if method differs across reads → fail closed / treat as incomplete; conflict → NO_GOVERNED_ALERT

---

## Confirmation policy (design only — not implemented)

G7 nonnumeric **APPROVED:** single raw reading is **not** universal notification authority; repeat/confirmation required before governed absolute alert.

| Rule | Spec |
|---|---|
| CONFIRMATION_REQUIRED | YES for GOVERNED_ALERT / URGENT (all three metrics). CONDITIONAL for OBSERVE_OR_RECHECK (PO may allow single-read in-app observe only — unsigned product choice) |
| Valid readings | ≥2 structurally valid observations (concept from G7 single-read prohibition) |
| Confirmation window | **UNSIGNED** — evidence does not lock minutes/hours |
| Same HealthSubject | REQUIRED |
| Same metric | REQUIRED |
| Acceptable quality | Each confirming read must pass quality gate (PM quality KNOWN; HealthData ineligible) |
| Context consistency | Required contexts for the metric must remain KNOWN and non-conflicting across confirming reads |
| Conflicting readings | Do **not** promote to GOVERNED_ALERT; remain OBSERVE / fail closed |
| Not allowed | “Two arbitrary rows exist”; time-window invention; cross-subject; cross-metric; PM quality transferred to HealthData |

```
CONFIRMATION_PRODUCER=ABSENT (runtime)
CONFIRMATION_WINDOW=UNSIGNED
CONFIRMATION_COUNT_CONCEPT=GE_2_VALID_SAME_SUBJECT_SAME_METRIC
CONFIRMATION_POLICY_STATUS=PROPOSED_NOT_APPROVED
```

---

## PO signoff matrix

| metric | candidate_rule | evidence_basis | required_context | confirmation_rule | fail_closed_conditions | STATUS | PO_DECISION_REQUIRED |
|---|---|---|---|---|---|---|---|
| HR | REFERENCE 60–100 resting display only | AHA | resting/activity/sleep | ≥2 / WINDOW=UNSIGNED | activity unknown; quality unknown; no confirm; no signed numeric | SUPPORTED_CANDIDATE (ref only) | YES — whether to adopt ref display; **reject** legacy 100/60 notify |
| HR | Absolute notify BPM cutoffs | insufficient for notify | same | same | same | UNSIGNED_INSUFFICIENT_EVIDENCE | YES — supply signed bands or keep blocked |
| SpO2 | REFERENCE ~95–100% display only | FDA/MedlinePlus | quality; altitude or clinician baseline; symptoms for escalate | ≥2 / WINDOW=UNSIGNED | quality/altitude unknown; heuristic symptoms for escalate | SUPPORTED_CANDIDATE (ref only) | YES |
| SpO2 | Auto-notify at 95% or ≤92/≤88 | guidance ≠ product threshold | same | same | same | UNSIGNED_INSUFFICIENT_EVIDENCE | YES — choose governed bands or keep blocked |
| Temp | ≥38.0°C method-aware GOVERNED_ALERT candidate | NHS/CDC | temperature_method; quality | ≥2 / WINDOW=UNSIGNED | method/quality unknown; no confirm | SUPPORTED_CANDIDATE | YES — approve/reject 38.0 + method gate |
| Temp | 37.8°C or legacy 37.5°C | ambiguous / rejected | same | same | same | UNSIGNED_INSUFFICIENT_EVIDENCE | YES — reject 37.5; choose 38.0 vs 37.8 |

```
NUMERIC_POLICY_STATUS=PROPOSED_NOT_APPROVED
CONFIRMATION_POLICY_STATUS=PROPOSED_NOT_APPROVED
PO_SIGNOFF_REQUIRED=YES
POLICY_PROPOSAL_ID=SEDI-I9-ABSOLUTE-VITAL-ADULT-DRAFT-2-G14
POLICY_VERSION=DRAFT_2_G14
```

## Unsigned inventory

```
UNSIGNED_NUMERIC_ITEMS=HR_ABSOLUTE_NOTIFY_BPM;SPO2_AUTO_NOTIFY_PCT;TEMP_37_8_VS_38_0_PRODUCT_CHOICE;LEGACY_100_60_95_37_5;DEVICE_50_120_38_39_5
UNSIGNED_CONFIRMATION_ITEMS=CONFIRMATION_WINDOW_MINUTES_OR_HOURS;OBSERVE_SINGLE_READ_PRODUCT_EXCEPTION
```

## Next (not authorized)

PO numeric + confirmation window signoff → then interpreter/activation gates remain separately authorized.

```
BASELINE_HEAD=a2ecb25cdd71a40f1b8df3a0b35f51d9abdfa047
CODE_HEAD=7724d7133227b271bfcd872fbc25e05e863e4e6c
ALEMBIC_HEAD=086_i9_vital_observation_context_authority
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v821_FA.md
```
