# SEDI Cursor Authoritative Handoff - v814

A3 Smart Notifications G7 — nonnumeric vitals policy **signoff** + I9 scaffold/schema/API **design only**. Append-only after v813 / Master Log §515. **DESIGN_NOT_IMPLEMENTATION.**

```
VERSION=v814
STATUS=CURRENT
LOGICAL_PREDECESSOR=v813
MASTER_LOG=§516
GATE=SEDI-V1-A3-SMART-NOTIFICATIONS-G7-NONNUMERIC-VITALS-POLICY-SIGNOFF-AND-I9-SCAFFOLD-DESIGN-01
GATE_RESULT=PASS
MODE=READ_ONLY_ARCHITECTURE_SIGNOFF
RUNTIME_MUTATION=NO
NONNUMERIC_POLICY_STATUS=APPROVED_BY_PRODUCT_OWNER
NUMERIC_POLICY_STATUS=NOT_APPROVED
RUNTIME_ACTIVATION_AUTHORIZED=NO
SCHEMA_IMPLEMENTATION_AUTHORIZED=NO
NEXT_EXECUTION_GATE_AUTHORIZED=NO
```

## Preflight

- Branch: `feature/a3-authority-chat-stream-profile-foundation-be` → remote `feature/a3-authority-chat-stream-profile-foundation`
- HEAD = G6 tip `39b72452bb0d3d9660e04784585c0296d90ba9cb`; ahead/behind 0/0; worktree clean
- PRODUCT_CODE_HEAD unchanged `9a4f1f0408e670eb3b13f2d2b92d1e6eaca559c1`

## 1. Nonnumeric policy signed (architecture — not numerics)

### Authority map (APPROVED)

| Layer | Owns |
|---|---|
| I9 | Physiological facts + governed interpretation |
| I10 | Notification / interruption policy only |
| Gate4 | Delivery / preferences |
| Flutter | Presentation only |

Cross-cutting (ALL METRICS — APPROVED):

- policy versioning required
- measurement quality required
- context required
- repeat/confirmation required before governed absolute alert
- provenance required
- subject attribution required
- single raw reading is **not** universal notification authority

### Per-metric nonnumeric signoff

| Metric | Signed model | Signed constraints |
|---|---|---|
| HR | Absolute + personal-baseline **combined** | Resting/activity/sleep/medication context; I9 MAD remains **distinct**; no universal single-read alert |
| SpO2 | Context-gated | Quality + repeat + symptoms + altitude + personal/provider baseline; no reference-floor single-read alarm |
| Temperature | Context-gated, method/site-aware | Repeat + symptoms/context; no universal single-read alarm |

Personalization (APPROVED):

```
GENERAL_ADULT_DEFAULT_POLICY=YES
PERSONALIZED_BASELINE_SUPPORT=YES
CLINICIAN_CONFIGURED_POLICY=CONDITIONAL
DISEASE_CONTEXT_POLICY=YES_GOVERNED_ONLY
```

Explicitly preserved:

```
NUMERIC_POLICY_APPROVED=NO
LEGACY_100_60_95_37_5_APPROVED=NO
DEVICE_50_120_38_39_5_APPROVED=NO
```

## 2. Minimal scaffold inventory

| Capability | Classification | Notes |
|---|---|---|
| Scalar vital fact (device) | EXISTS | `PhysiologicalMeasurement` (type/unit/value/measured_at/device/quality/hs) |
| Manual HealthData ingress | EXISTS as legacy | `HealthData` strings; comment marks LEGACY DEPRECATE; still interpretation owner via evaluate_health_data |
| Device-reported STABLE\|UNSTABLE | EXISTS | `DeviceReportedVitalStatus` + I10 DRVS producer |
| MAD / personal HR stability | EXISTS | I9 baselines + hr_stability → I10 |
| Absolute vital policy version authority | NEW_CONTRACT_REQUIRED + SCHEMA_REQUIRED | `CareResponsePolicy` is care-timing, **not** absolute vitals clinical bands |
| Absolute vital alert result | NEW_CONTRACT_REQUIRED (+ optional EXTEND `DerivedHealthSignal`) | No ABSOLUTE_VITAL_ALERT_STATUS today |
| Confirmation/repeat state | NEW_CONTRACT_REQUIRED | No durable confirmation window contract |
| Context facts (rest/activity/sleep/symptoms/altitude/method) | NEW_CONTRACT_REQUIRED / MISSING | No reliable authority for most |
| Clinician/disease override config | NEW_CONTRACT_REQUIRED | Conditional; not present for vitals absolute |
| I10 DEVICE_STATUS intake | EXISTS | `enqueue_i10_notification` / self adapter / DRVS+HR producers |
| I10 absolute-vitals consumer | NEW_CONTRACT_REQUIRED | Must consume I9 result only (no raw threshold math) |
| Governance evidence refs | EXTEND_EXISTING patterns | Knowledge governance columns exist elsewhere; not wired to absolute vitals policy |

Relevant migrations (inspect-only): `058` physiological_measurements; `059` HealthData legacy deprecation comment; `071` hs on PM; `080` DRVS.

## 3. Canonical I9 observation input (HR / SpO2 / temperature)

| Concept | CURRENT_SOURCE | CURRENT_GAP | TARGET_AUTHORITY | SCHEMA_DELTA_REQUIRED |
|---|---|---|---|---|
| metric | PM.measurement_type / HealthData columns | HealthData not unified | I9 observation adapter → PM or equivalent | NO for device; YES for HealthData→subject-aligned fact path |
| normalized_value | PM.numeric_value; HealthData parse | HealthData string-only | I9 | NO device; EXTEND HealthData adapter write-through |
| unit | PM.unit | HealthData implicit | I9 | YES if HealthData path lacks unit |
| measured_at | PM.measured_at | HealthData only created_at | I9 | YES for HealthData measured_at (or derive-with-provenance) |
| source_class | Device patterns; DRVS DEVICE_REPORTED | Manual source_class missing | I9 | YES (on observation or adapter metadata) |
| user/account | PM.user_id / HealthData.user_id | — | I9 | NO |
| health_subject_id | PM nullable; device packets required | HealthData missing | I9 | YES for HealthData path (resolve SELF subject) |
| device identity | PM.device_id | N/A for pure manual | I9 | NO when applicable |
| quality/validity | PM.quality_state | HealthData missing; vocab loose | I9 | EXTEND (quality gate contract) |
| provenance/evidence ref | packet provenance / idempotency | HealthData missing | I9 | YES for manual; EXTEND for absolute result link |

**HealthData future role:** KEEP_AS_SOURCE_ADAPTER only — write/normalize into I9 observation authority; **never** clinical interpretation owner.

Do **not** invent numeric validation bands in this design.

## 4. Versioned policy authority (no cutoffs in G7)

```
POLICY_AUTHORITY_NEW_TABLE_REQUIRED=YES
POLICY_RULE_STORAGE_REQUIRED=YES
```

**RATIONALE:** Absolute vitals need durable identity/version/lifecycle/metric-scope/evidence/approval distinct from `CareResponsePolicy` (ack/escalation timing) and from MAD/DRVS. Generic rule rows may exist later; **numeric contents = NOT_AUTHORIZED_IN_G7**.

Conceptual objects (design only):

1. **i9_absolute_vital_policy** — policy_id, version, status (draft|approved|retired), population/context scope, evidence refs, governance approval ref, effective_from/until, source-applicability flags (manual vs device) when **explicitly governed**.
2. **i9_absolute_vital_policy_rule** — generic versioned rule slots (metric, rule_kind, context_gates JSON, **numeric payload nullable and empty until PO authorizes**). Mark: `NOT_AUTHORIZED_IN_G7` for any cutoff values.

Do not store 100/60/95/37.5 or 50/120/38/39.5 in G7 docs as approved content.

## 5. ABSOLUTE_VITAL_ALERT_STATUS result contract

| Attribute | Contract status |
|---|---|
| health_subject_id | EXTEND_EXISTING (required on result; PM hs often present) |
| metric | EXISTING_CONTRACT (vocab) |
| source measurement/evidence ref | EXTEND_EXISTING (PM id / HealthData id / packet) |
| policy version ref | NEW_CONTRACT_REQUIRED |
| observation timestamp | EXISTING_CONTRACT |
| quality/context validation result | NEW_CONTRACT_REQUIRED |
| confirmation/repeat state | NEW_CONTRACT_REQUIRED |
| governed outcome | NEW_CONTRACT_REQUIRED (conceptual levels from G6; **no enums created now**) |
| severity/risk | EXTEND_EXISTING optional (`DerivedHealthSignal.severity_band` pattern) — only if mapped from governed outcome, not recomputed in I10 |

Prefer new dedicated result table **or** tightly constrained EXTEND of `DerivedHealthSignal` with absolute-specific signal_type + required policy_version FK — implementation gate chooses; design recommends **dedicated table** to avoid conflating MAD-derived vs absolute.

## 6. Context / confirmation ownership (fail closed)

| Requirement | OWNER | CURRENT_SUPPORT | NEW_CONTRACT_REQUIRED |
|---|---|---|---|
| measurement quality | I9 | PARTIAL (PM.quality_state) | YES (gate semantics) |
| repeat confirmation | I9 | NO | YES |
| rest/activity/sleep | MISSING_CONTEXT_AUTHORITY | NO | YES (or fail-closed: no absolute alert without resting attestation) |
| symptom context | MISSING_CONTEXT_AUTHORITY | NO | YES for SpO2 escalation; CONDITIONAL HR/Temp |
| altitude | MISSING_CONTEXT_AUTHORITY | NO | YES or fail-closed exception path |
| personal baseline | I9 MAD (HR) | YES for HR MAD; PARTIAL others | EXTEND for SpO2/temp baselines when governed |
| clinician configuration | MISSING_CONTEXT_AUTHORITY | NO | YES when CONDITIONAL path activated |
| disease context | MISSING_CONTEXT_AUTHORITY | NO | YES_GOVERNED_ONLY — no hardcoded disease rules |

**Fail closed:** if required context for a metric is unknown, I9 absolute interpreter must **not** emit GOVERNED_ALERT / URGENT (shadow-only OBSERVE permitted).

## 7. I9 → I10 seam

```
I9 ABSOLUTE_VITAL_ALERT_STATUS (governed)
  → I10 producer (new): absolute_vital_alert_producer
  → semantic_family=DEVICE_STATUS, privacy=HEALTH_SENSITIVE
  → enqueue_i10_notification (existing intake)
  → Gate4 delivery
  → Flutter presentation
```

Minimum conceptual adapter changes:

- New I10 producer consumes **result id + governed outcome + policy_version + metric + subject** only
- Payload metadata: `source_type=i9_absolute_vital_alert`, `policy_version`, `result_id`
- **I10 MUST NOT receive raw BPM/%/°C for threshold recomputation**
- Dedupe occurrence key concept:  
  `i10:absolute_vital:{health_subject_id}:{metric}:{policy_version}:{confirmation_window_id|result_id}`

## 8. Shadow / migration safety (no activation in G7)

1. Schema/contracts (inactive)
2. I9 interpreter shadow-only
3. Ingest HealthData + device → canonical observation
4. Evaluate approved **nonnumeric** gates in shadow; numeric rules remain empty/unauthorized
5. Compare shadow outcomes vs legacy evaluate_health_data / rule_alerts (observational)
6. Activate I9→I10 consumer **per metric** only after validation **and** numeric PO signoff (separate gate)
7. Suppress corresponding legacy emit for that metric
8. Verify no gap / no double-send (shared occurrence / suppress table)
9. Retire evaluate_health_data thresholds
10. Retire rule_alerts thresholds

Double-alert prevention identity: same subject+metric+policy_version+confirmation_window; legacy suppress keyed to I9 result emission.

## 9. Minimum schema/API delta (conceptual — no SQL)

### Proposed DB objects

| OBJECT | PURPOSE | FIELDS_CONCEPTUALLY | FK/OWNERSHIP | RETENTION | WHY INSUFFICIENT NOW |
|---|---|---|---|---|---|
| i9_absolute_vital_policies | Versioned policy authority | policy_id, version, status, scope, evidence_refs, approval_ref, effective_* | I9-owned | Governance long-lived | CareResponsePolicy ≠ vitals absolute |
| i9_absolute_vital_policy_rules | Generic rules | policy FK, metric, rule_kind, context_gates, **numeric_payload NOT_AUTHORIZED_IN_G7** | I9 | With policy | No place for versioned absolute rules |
| i9_absolute_vital_alert_results | ABSOLUTE_VITAL_ALERT_STATUS | hs, metric, evidence_ref, policy_version, ts, quality/context, confirmation_state, outcome | I9; FK policy + PM/HealthData | Clinical ops retention TBD | DerivedHealthSignal too weak/ambiguous |
| (optional) confirmation_windows | Repeat state | hs, metric, window_id, reading_ids, state | I9 | Short-lived ops | No repeat contract |

### Existing to extend

| OBJECT | PURPOSE |
|---|---|
| PhysiologicalMeasurement | Prefer canonical fact for device; enforce hs for absolute path |
| HealthData | Ingress adapter only; add measured_at/source/hs via adapter write-through (or deprecate write after PM dual-write) |
| I10 producers | New absolute consumer; no threshold math |

### API / internal contracts

| CONTRACT | CURRENT_GAP | PROPOSED_MINIMUM_CHANGE |
|---|---|---|
| HealthData → I9 observation adapter | Interprets in notification_engine | Adapter normalizes to I9 fact; interpretation deferred |
| I9 absolute evaluate (internal) | Missing | Shadow-capable function signature (policy_version, observation_ids) — inactive |
| I10 absolute producer | Missing | Consume result row only |
| External public API | Prefer no new public endpoint in first scaffold | Internal service contracts first |

## 10. Implementation split recommendation

**B preferred:** schema foundation Gate, then runtime interpreter Gate separately. Numeric activation remains a **third** gate.

Recommended next Gates (not authorized):

1. `…-G8-I9-ABSOLUTE-VITAL-POLICY-SCHEMA-SCAFFOLD-01` — tables/contracts empty numerics; no activation
2. `…-G9-I9-ABSOLUTE-VITAL-INTERPRETER-SHADOW-01` — shadow evaluate nonnumeric gates only
3. `…-G10-ABSOLUTE-VITAL-NUMERIC-POLICY-SIGNOFF-01` — PO numeric approval (separate)
4. Later: activate I10 + suppress legacy per metric

```
REPOSITORY_BASELINE=39b72452bb0d3d9660e04784585c0296d90ba9cb
PRODUCT_CODE_HEAD=9a4f1f0408e670eb3b13f2d2b92d1e6eaca559c1
DROPBOX_AUTHORITATIVE_PATH=C:\Users\Javad Meighandi\Dropbox\Sedi\References\Cursor\Sedi_Cursor_Authoritative_Handoff_v814_FA.md
```
