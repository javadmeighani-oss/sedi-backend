# 06 — ALS / MS / Diabetes P0 Coverage (FROZEN)

```text
RUNTIME_MANIFEST_MUTATED = NO
PROPOSAL_ONLY for Diabetes D20 + MS priority elevation
DESIGN_ONLY YAML = design_only_yaml/p0_coverage_matrix_v1.yaml
```

## P0 decision

| Disease | Priority | Manifest today | Design freeze |
|---|---|---|---|
| ALS | P0-CRITICAL | D18 ALS-TRACK | KEEP |
| MS | P0-CRITICAL | D19 P0-HIGH | **ELEVATE to P0-CRITICAL** (future manifest Gate) |
| Diabetes | P0-CRITICAL | domain only | **ADD D20 DIABETES-TRACK** (future Gate) |

Diabetes subtypes required: Type1, Type2, Gestational, LADA, MODY, secondary, prediabetes + major complications.

## Coverage completeness model

```text
Disease × Knowledge Dimension × Evidence Class × Source Authority Tier × Freshness
→ cell state ∈ {COVERED_CURRENT, COVERED_STALE, PARTIAL, CONFLICTED, MISSING, NOT_APPLICABLE}
→ MISSING/PARTIAL/STALE/CONFLICTED may open KnowledgeGap
```

Never claim `ALL WORLD KNOWLEDGE = COMPLETE`.

## ALS dimensions (machine-checkable)

definition, classification, epidemiology, etiology, genetics, pathophysiology, diagnosis, diagnostic criteria, differential diagnosis, phenotypes, onset patterns, symptoms, progression, ALSFRS-R, respiratory, nutrition, swallowing, speech, mobility, cognition/behavior, pharmacologic Rx, gene-targeted Rx, experimental therapies, respiratory support, nutrition support, rehab/PT, assistive tech, communication, palliative, adverse effects, contraindications, biomarkers, imaging, neurophysiology, genetics tests, clinical trials, eligibility, prognosis, QoL, caregiver, mental health, guidelines, SRs, MAs, RCTs, observational, emerging, negative evidence, conflicting evidence, retractions.

## MS dimensions

diagnosis, 2024 McDonald criteria, CIS, RRMS, SPMS, PPMS, relapse, activity, progression, MRI, CSF, biomarkers, EDSS, functional outcomes, DMTs, comparative efficacy, safety, monitoring, pregnancy, fertility, vaccination, infection risk, JCV/PML, fatigue, mobility, spasticity, pain, cognition, bladder/bowel, sexual health, exercise, rehab, nutrition, mental health, trials, emerging therapies, long-term progression.

## Diabetes dimensions

classification/subtypes, risk, prevention, diagnosis, HbA1c, fasting glucose, OGTT, CGM, autoantibodies, C-peptide, glycemic targets, insulin, non-insulin meds, drug classes, CGM/pump/AID, nutrition, exercise, weight, sleep, behavior, hypo/hyperglycemia, DKA, HHS, CVD, CKD, retinopathy, neuropathy, foot disease, pregnancy, children, older adults, mental health, drug interactions, contraindications, renal/hepatic, trials, emerging drugs, devices, cell therapy, immunotherapy.
