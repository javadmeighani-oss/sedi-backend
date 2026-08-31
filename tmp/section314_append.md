
§314 - SEDI-V1 I5-S49 CRAWLER-TO-KNOWLEDGE / SOURCE-REGISTRY AUDIT-01
--------------------------------------------------------------------------------
GATE=SEDI-V1 I5-S49 CRAWLER-TO-KNOWLEDGE / SOURCE-REGISTRY AUDIT-01
APPROVED_BY=Javad Meighani
RECORDED_AT_UTC=2026-08-18T04:30:00Z
RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS
TOKEN_EFFICIENT_EXECUTION=PASS
PRODUCTION_MUTATION=NO
TECHNICAL_RETEST=NO
NEW_MIGRATION=NO
NO_DEPLOY=YES
NO_FLAG_CHANGE=YES
AUTO_REMEDIATION_CYCLES=0/2

GATE_RESULT=PASS
FULL_GATE_CLOSURE=PASS
HARD_STOP=NO
BASELINE_DELTA=CHATGPT gate declares v620; repo physical tip remains v619 (v620 file absent/unverified per v615 lineage). Cursor v604 + Master Log §313 verified.

AUTHORITY_AT_START=
CHATGPT_PHYSICAL_TIP=v619
CHATGPT_GATE_DECLARED=v620
CURSOR_PHYSICAL_TIP=v604
MASTER_LOG_TIP=§313

SOURCE_REGISTRY_CURRENT=
CANONICAL_AUTHORITY=DATABASE governed_source_profiles + i5_source_registry_extensions + i5_source_registry_roles (KNOW-01)
OPERATIONAL_WEEKLY_ALLOWLIST=backend/config/i5/multisource_activation_allowlist_v1.yaml (4 activation:YES rows)
BOOTSTRAP_SEEDS=backend/app/services/i5/know01/seed_registry.py GLOBAL_SEEDS (23 keys; listing!=activation)
DESIGN_ONLY=docs/architecture/i5-final-knowledge-architecture-freeze-01/design_only_yaml/trusted_source_registry_seed_v1.yaml
PARALLEL_REGISTRIES=YES (YAML allowlist + Python seeds + DB overlay; no single Javad-facing canonical file today)

CRAWLER_ENTRY_POINTS=
SCHEDULER=backend/app/core/scheduler.py job_id weekly_international_knowledge_crawler interval_min=10080
W6P01_RUNTIME=backend/app/services/i5/governed_weekly_runtime.py
W3P02_ORCHESTRATOR=backend/app/services/i5/weekly_orchestrator.py
KNOW05_ORCHESTRATOR=backend/app/services/i5/know05/orchestrator.py
MULTISOURCE_LOADER=backend/app/services/i5/multisource_activation.py
FLAGS=SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED + SEDI_I5_SOURCE_ACTIVATION_ENABLED + SEDI_I5_MULTISOURCE_ENABLED

LATEST_GENUINE_WEEKLY_EVIDENCE=
EVIDENCE_DATE=2026-08-13
G305_AUDIT=latest_weekly_id=7 status=COMPLETED weekly_run_count=6 scope=NHS_ONLY_BOUNDED multisource=false
DRIFT_AUDIT=latest_weekly_id=3 status=COMPLETED weekly_run_count=3 scope=4_allowlisted multisource=true created_at_latest=2026-08-09

PRODUCTION_COUNTS_G305_2026-08-13=
gsp_count=17
allowlist_activation_yes=4
weekly_active_gsp_eligible=4
catalog12_gsp=12
catalog12_weekly_enabled_gsp=0
raw_evidence_count=22
scientific_artifact_count=13
ku_count=22
provenance_count=22
kce_count=0
knowledge_memory_count=0
ku_runtime_eligible=0
ku_draft_not_reviewed=22
orphan_provenance=0

PRODUCTION_COUNTS_DRIFT_2026-08-13=
weekly_source_results=9 extracted=7 blocked=1 failed=1
unknown_source_result_count=0
scientific_artifact_count=0
raw_evidence_count=9
ku_count=9
ku_runtime_eligible=0

PIPELINE_DUAL_PATH=YES
PATH_A=W6-P01 PUBLIC_WEB_FETCH weekly: allowlist→GSP→raw_evidence→knowledge_units+provenance (no i5_scientific_artifacts)
PATH_B=KNOW-04/05 connectors: GSP registry→i5_scientific_artifacts/versions→KU via i5_knowledge_unit_evidence_links

SOURCE_KNOWLEDGE_TRACE=PARTIAL
TRACE_1=pubmed_ncbi_eutils connector→artifact_id=1 ku_id=10 pmid=42581131 (i5_know05_canary.log 2026-08-13)
TRACE_2=GSP id=1 canonical_key=nhs_uk_live_well→weekly_run_id=1 attempt_id=1 result_status=EXTRACTED (drift audit; no artifact row)
TRACE_3=GSP id=2 medlineplus_consumer_health→weekly_run_id=3 attempt_id=3 result_status=EXTRACTED (drift audit; raw/KU path)

UNTRACEABLE_SOURCES=0 (drift unknown_source_result_count=0; all results map to 4 allowlist canonical_keys)

JAVAD_REGISTRY_REQUIREMENT=EXTEND_EXISTING
RATIONALE=Reuse GSP+registry overlay as SoT; expose ONE human-editable governed file (extend multisource_activation_allowlist_v1.yaml pattern or DB-backed export/import) — eliminate parallel Python seed authority for runtime activation

I7_FTS_BOUNDARY_CONFLICT=NO
SERVING_BLOCKED_BY=ku_runtime_eligible=0 kce_count=0 production_rag=NO review_state=NOT_REVIEWED publication_state=DRAFT
SCIS_LEXICAL=backend/app/services/scis/lexical.py FTS on kce.search_tsv requires eligible KCE

EXACT_GAPS=
G1=No single canonical human-editable trusted-source file governing all crawler activation
G2=Dual ingestion paths (raw_evidence weekly vs scientific_artifact connector) without unified artifact accounting
G3=0 servable/indexed KU in production evidence; crawler→knowledge conversion proven, serving chain not
G4=No verified production weekly observation after 2026-08-13 (Aug-21 fire pending per v619)
G5=ChatGPT v620 physical continuity file not in repo

RUNTIME_EVIDENCE_REQUIRED=YES
RUNTIME_EVIDENCE_NEXT_GATE=SEDI-V1 I5-S49 PRODUCTION READ-ONLY DB OBSERVE-02 (weekly_run/artifact/ku/kce counts + 3-ID lineage post-2026-08-21 fire)

CURSOR_HANDOFF=v605
CHATGPT_CONTINUITY=v620
NEXT_GATE=SEDI-V1 I5-S49 CANONICAL TRUSTED-SOURCE REGISTRY DESIGN + PRODUCTION OBSERVE-02 (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
SHA256_BEFORE_APPEND=5A9C86284649B151B4F10F2D1B2BBF2C120520F3CBBF4398244984F05E1BFBFC
NOTE=post-§314 final master-log whole-file self-SHA is NOT embedded inside §314.
