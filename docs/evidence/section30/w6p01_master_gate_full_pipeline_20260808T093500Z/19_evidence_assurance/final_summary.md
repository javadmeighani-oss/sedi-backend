# W6-P01 Master Gate Evidence Assurance Pack (sanitized)

RECORDED_AT_UTC=2026-08-08T09:35:00Z
GATE_ID=I5-W6-P01-MASTER-FULL-GOVERNED-PIPELINE
JAVAD_MASTER_GATE_APPROVAL=EXPLICIT (this chat Master Execution Gate)
GATE_RESULT=PASS

## Authority
- Master Gate supersedes historical W6-P01 PROHIBITED **/* planning pause for named operations only
- Do not rewrite historical planning matrices
- First-cycle source only: nhs_uk_live_well / NHS sleep URL
- Cadence: 10080 minutes
- Retention: RAW_MINIMAL_EVIDENCE_ONLY (no full body in artifacts)
- Formal % locked at §164.2 until validation Gate

## Git
- STARTING_HEAD=76563e6b3e318b77c2f58256c00bfa5cd374d28a
- FINAL_TECH_SHA=65c56c3a20bf012c3cd0ea5419c1d984e9d23f32 (deployed image)
- FEATURE_TIP_AT_DOCS_PREP=ac80623454684369773f89dd91e07bbeb98adafb
- MAIN_WORKFLOW_SHA=6d3f059dabb5a79d4fed7fd4e23190ae45b5eb91
- DEPLOYED_SHA != FINAL_DOCS_HEAD by design (docs-only follow-on OK)

## CI / Tests
- Migration parity CI: 31248659561 on 65c56c3a20bf012c3cd0ea5419c1d984e9d23f32
- Mandatory real-network E2E: 31248658080 artifact 9019299217 digest sha256:2cadaef29a3e4855f9935f8282c54b82c9225019ebebc515dd9ed10a93625683
- Offline W6-P02 E2E: 31248556860 (prior tip; path still green)
- REAL_FETCH_SKIPPED=NO

## Production
- Preflight: 31248882645; alembic before=049; image before=2a5dc53d...
- Migration verify: 31249367963; after=056_i5_w2_p02_conflict_safety
- Backup: ***/backups/postgres/sedi_db_pre_w6p01_056_20260808_084526.sql.gz size~31404 integrity PASS
- Image build: 31248722611; digest=sha256:09f80fc1c9ad216fa2640cb7c67e82aebdbd966d7036078a55035e6e951f9a89
- Deploy: 31249435562; tag=65c56c3a20bf012c3cd0ea5419c1d984e9d23f32; digest=sha256:09f80fc1c9ad216fa2640cb7c67e82aebdbd966d7036078a55035e6e951f9a89
- Activate: 31250816722 SUCCESS
- First real scheduled fetch (network=True): activate attempt 31250041916 weekly_job_1 FULL_SUCCESS governed_raw_ku_provenance_persisted run_id=1
- Final activate proof: weekly_job_1/2 ALREADY_SUCCESSFUL_TERMINAL network=False; idempotent_db_counts raw=1 ku=1 prov=1 runs=1
- Scheduler: weekly_international_knowledge_crawler registered interval_min=10080 enabled=True
- SEDI_DISABLE_SCHEDULER cleared to false (was blocking APScheduler)
- Scope: disabled non-NHS fetch slug=nhs_sleep_live_well_v1; enabled_slugs=nhs_uk_live_well count=1
- Env backup: ***/backups/env/sedi-backend.env.w6p01_pre_activate_20260808_093312

## Governed persistence (IDs/counts only; no body)
- WeeklyKnowledgeRun run_id=1
- I5RawEvidence count=1
- KnowledgeUnit count=1 (DRAFT / PENDING_REVIEW / NOT_ELIGIBLE / conflict=NONE / freshness=UNKNOWN)
- KnowledgeProvenance count=1
- Knowledge Memory write for unapproved KU=NO

## Continuity
- Master log append §261 CRLF_ONLY
- External handoff v552 = exact v551 prefix + new section LF_ONLY
- FORMAL_I5 remains 21.79487179%

## Explicit non-secrets policy
No passwords, tokens, full env, DB credentials, or NHS page body stored.
