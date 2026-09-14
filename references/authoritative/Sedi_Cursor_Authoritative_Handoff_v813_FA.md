# SEDI Cursor Authoritative Handoff - v813

A3 Smart Notifications G6 — absolute vitals **clinical policy evidence design only**. Append-only after v812 / Master Log §514. **CLINICAL_POLICY_STATUS=PROPOSED_NOT_APPROVED.**

```
VERSION=v813
STATUS=CURRENT
LOGICAL_PREDECESSOR=v812
CONTINUITY_BASELINE_CHATGPT=v815
MASTER_LOG=§515
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G6-ABSOLUTE-VITALS-CLINICAL-POLICY-EVIDENCE-01
GATE_RESULT=PASS
MODE=READ_ONLY_EVIDENCE_POLICY_DESIGN
RUNTIME_MUTATION=NO
NUMERIC_THRESHOLDS_RUNTIME_AUTHORIZED=NO
PRODUCT_OWNER_POLICY_APPROVAL_REQUIRED=YES
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Evidence boundary

Official/primary sources used in this gate (reference only — **not** Sedi approved thresholds):

| Source | Use in gate |
|---|---|
| AHA | Adult resting HR context; tachycardia/bradycardia definitions; athletic/medication/sleep exceptions |
| FDA | Pulse oximetry accuracy limits; SpO2 context; do not rely on oximeter alone |
| MedlinePlus (NIH) | SpO2 reference bands; home seek-care examples; device vs true O2 difference; altitude/lung disease |
| NHS / CDC | Adult fever commonly ≥38°C; method/context; alternate cutoffs (e.g. 37.8°C) in guidance |

No blogs or commercial health sites as authority. Legacy repo numerics (100/60/95/37.5; device 50/120/38/39.5) remain **not approved**.

## Reference vs Sedi policy (per metric)

| Layer | HR | SpO2 | Temperature |
|---|---|---|---|
| REFERENCE_RANGE | AHA resting ~60–100 bpm (context-dependent) | FDA/MedlinePlus often cite ~95–100% in many healthy individuals (not universal alarm) | NHS/CDC high fever often ~≥38°C (method-dependent) |
| CLINICAL_DEFINITION | Tachycardia/bradycardia terms require clinical context | Hypoxemia is clinical diagnosis, not single oximeter read | Fever interpretation depends on site/method |
| SEEK_CARE_GUIDANCE | Provider evaluation when symptomatic or sustained abnormal resting HR | MedlinePlus home guidance uses lower bands for contact/urgent care with symptoms | Seek care per NHS/CDC when fever + concerning symptoms |
| DEVICE_LIMITATION | Wearable/measurement motion artifact | FDA: pigmentation, circulation, nail polish, accuracy limits | Site (oral/tympanic/etc.) affects reading |
| SEDI_ALERT_POLICY | **Not defined in this gate** — candidate model below | **Not defined** | **Not defined** |

## Policy levels (conceptual — not schema)

| Level | Evidence type | Confirmation | Quality | Context exceptions | I9 downstream (future) | I10 may notify |
|---|---|---|---|---|---|---|
| NORMAL_REFERENCE | Population reference only | N/A | Valid read preferred | Athlete HR, altitude SpO2, chronic disease baselines | None / informational only | NO |
| OBSERVE_OR_RECHECK | Reference deviation + weak signal | Repeat measurement; time window | Quality gate pass | Activity not resting; single transient read | OBSERVE candidate (no alert authority) | NO or low-friction in-app only (PO) |
| GOVERNED_ALERT | PO-approved policy version + evidence bundle | Repeat or sustained pattern per policy | Required valid/quality state | Documented exceptions in policy version | ABSOLUTE_VITAL_ALERT_STATUS (governed) | YES per I10 policy |
| URGENT_ESCALATION_CANDIDATE | Seek-care guidance + severe sustained + symptoms | Multi-read + symptom attestation if product supports | High quality required | Never bypass clinician-configured ceilings/floors | Escalation class (governed) | YES with strict caps |

## Heart rate — proposed model

**HR_POLICY_MODEL=C** (absolute + personal-baseline combined; absolute never alone on single uncontextualized read)

**Not A** (no universal absolute alert): AHA resting band does not map 1:1 to push notification at 100/60.

**Candidate policy (DRAFT_1 — not approved):**

| Block | Content |
|---|---|
| A. observation/reference | Display/reference: AHA adult resting commonly 60–100 bpm |
| B. candidate alert trigger | **BLOCKED_PENDING_CLINICAL_REVIEW** for any fixed BPM notify trigger; evidence supports context-gated bands only after PO signs version |
| C. confirmation/context | Resting vs activity; sleep state; repeat within window; device quality/provenance |
| D. escalation | Symptom-aware + sustained resting abnormality + repeat confirmation |
| E. exceptions | Athletic conditioning, beta-blockers, sleep, personal MAD deviation (I9 nonclinical) |
| F. evidence | AHA resting HR / tachycardia / bradycardia context |
| G. confidence | High for “context required”; **Low** for adopting legacy 100/60 as notify authority |

**Alert condition attributes (HR):**

- EVIDENCE_SUPPORT= Strong for context; weak for universal numeric alarm
- CONTEXT_REQUIRED=YES (resting/activity/sleep/medication)
- MEASUREMENT_QUALITY_REQUIRED=YES
- REPEAT_CONFIRMATION_REQUIRED=YES
- SYMPTOM_CONTEXT_REQUIRED=CONDITIONAL (escalation tiers)
- PERSONAL_BASELINE_EXCEPTION_REQUIRED=YES (combine with I9 MAD)
- HIGH_RISK_EXCEPTION_REQUIRED=CONDITIONAL (clinician-configured later)

## SpO2 — proposed model

**SPO2_POLICY_MODEL=B** (context-gated absolute alert; no universal single-read alarm at reference floor)

**Candidate policy (DRAFT_1 — not approved):**

| Block | Content |
|---|---|
| A. observation/reference | Many healthy individuals 95–100% (FDA/MedlinePlus) — reference only |
| B. candidate alert trigger | **BLOCKED_PENDING_CLINICAL_REVIEW** for universal 95% alarm; evidence favors lower seek-care bands only with symptoms + repeat (MedlinePlus examples ≤92 / ≤88 are **guidance**, not auto-Sedi thresholds) |
| C. confirmation/context | Repeat reading; quality-valid; altitude; known cardiopulmonary disease baseline |
| D. escalation | Symptom-aware; sustained low vs single dip |
| E. exceptions | Altitude, chronic lung disease, provider-set baseline |
| F. evidence | FDA pulse ox limitations; MedlinePlus SpO2 home guidance |
| G. confidence | High for quality/repeat/symptom; **Low** for 95% as universal notify |

**Alert condition attributes (SpO2):**

- CONTEXT_REQUIRED=YES
- MEASUREMENT_QUALITY_REQUIRED=YES
- REPEAT_CONFIRMATION_REQUIRED=YES
- SYMPTOM_CONTEXT_REQUIRED=YES for escalation tiers
- PERSONAL_BASELINE_EXCEPTION_REQUIRED=YES
- HIGH_RISK_EXCEPTION_REQUIRED=YES (cardiopulmonary context — governed config, not hardcoded disease rules)

## Temperature — proposed model

**TEMP_POLICY_MODEL=B** (context-gated absolute alert)

**Legacy 37.5°C vs evidence:** NHS/CDC commonly cite **≥38°C** (some 37.8°C) for adult fever — **37.5°C is not evidence-approved as Sedi alert cutoff** in this gate.

**Candidate policy (DRAFT_1 — not approved):**

| Block | Content |
|---|---|
| A. observation/reference | Adult high temperature commonly ~≥38°C (NHS/CDC) |
| B. candidate alert trigger | **BLOCKED_PENDING_CLINICAL_REVIEW** for 37.5; numeric candidates for PO table only if evidence-supported (e.g. 38.0 contextual) — **not authorized here** |
| C. confirmation/context | Measurement site/method; repeat; symptoms |
| D. escalation | Fever + concerning symptoms per seek-care guidance |
| E. exceptions | Individual variation, recent exertion, environment |
| F. evidence | NHS/CDC fever thresholds (method/context) |
| G. confidence | Medium for “≥38°C reference”; **Low** for 37.5 notify |

**Alert condition attributes (Temp):**

- CONTEXT_REQUIRED=YES (site/method/time)
- MEASUREMENT_QUALITY_REQUIRED=YES
- REPEAT_CONFIRMATION_REQUIRED=YES
- SYMPTOM_CONTEXT_REQUIRED=CONDITIONAL
- PERSONAL_BASELINE_EXCEPTION_REQUIRED=OPTIONAL
- HIGH_RISK_EXCEPTION_REQUIRED=CONDITIONAL

## Personalization / high-risk

```
GENERAL_ADULT_DEFAULT_POLICY_REQUIRED=YES
PERSONALIZED_BASELINE_OVERRIDE_REQUIRED=YES
CLINICIAN_CONFIGURED_POLICY_REQUIRED=CONDITIONAL
DISEASE_CONTEXT_POLICY_REQUIRED=YES
```

Universal policy alone is **insufficient** for SpO2 and HR; disease-specific numeric rules **must not** be hardcoded without governed evidence + PO approval.

## Versioned policy proposal (not implementation)

```
POLICY_PROPOSAL_ID=SEDI-I9-ABSOLUTE-VITAL-ADULT-DRAFT-1
POLICY_VERSION=DRAFT_1
STATUS=PROPOSED_NOT_APPROVED
```

Per-metric POLICY_DECISION: HR/SpO2/Temp numeric **notify triggers** = **BLOCKED_PENDING_CLINICAL_REVIEW** until PO approves a signed version with explicit numerics and context gates.

## Product owner decision table

| METRIC | PROPOSED_POLICY_MODEL | NUMERIC_CANDIDATES_IF_EVIDENCE_SUPPORTED | MANDATORY_CONTEXT | EXCEPTIONS | EVIDENCE | CURSOR_RECOMMENDATION | PO_APPROVAL_REQUIRED |
|---|---|---|---|---|---|---|---|
| HR | C (absolute + personal baseline) | None authorized; PO may later adopt context-gated resting BPM bands | Resting, repeat, quality, MAD | Athlete, meds, sleep | AHA | Reject legacy 100/60 as notify authority; require DRAFT_2 with signed numerics | YES |
| SpO2 | B (context-gated) | None authorized; PO may consider sustained low + repeat (not 95% single-read) | Quality, repeat, symptoms, altitude/disease baseline | Altitude, chronic lung, clinician floor | FDA, MedlinePlus | Reject legacy 95% universal alarm | YES |
| Temp | B (context-gated) | None authorized; reference discussion ≥38°C — not 37.5 | Site/method, repeat, symptoms | Exertion, environment | NHS, CDC | Reject legacy 37.5; align future policy to method-aware ≥38-class only if PO approves | YES |

## G5 alignment

Future I9 `ABSOLUTE_VITAL_ALERT_STATUS` must consume **POLICY_PROPOSAL_ID** version only after PO approval; I10 notifies from governed I9 result without threshold math.

```
REPOSITORY_BASELINE=2886be66a1977d3b35053755c2d606fb64d6a494
PRODUCT_CODE_HEAD=9a4f1f0408e670eb3b13f2d2b92d1e6eaca559c1
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v813_FA.md
```
