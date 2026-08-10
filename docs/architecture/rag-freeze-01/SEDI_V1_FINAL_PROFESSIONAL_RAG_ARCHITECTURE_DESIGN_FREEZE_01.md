# SEDI-V1 FINAL PROFESSIONAL RAG ARCHITECTURE DESIGN FREEZE-01

```text
GATE = SEDI-V1 FINAL PROFESSIONAL RAG ARCHITECTURE DESIGN FREEZE-01
STATUS = AUTHORIZED / EXECUTED
RECORDED_AT_UTC = 2026-08-10T16:40:00Z
MODE = DESIGN FREEZE ONLY (NO IMPLEMENTATION)
GATE_RESULT = PASS
FINAL_RAG_ARCHITECTURE = FROZEN
```

## 0. Authority reconstruction (FACT)

```text
WORKSPACE = D:/Rimiya Design Studio/Sedi/software/Sedi-v-1/workspace
BRANCH = feature/section15/backend-continuity-foundation
LOCAL_HEAD = 91637678bfc5ef5867a7402a113b97eee9189e88
REMOTE_HEAD = 91637678bfc5ef5867a7402a113b97eee9189e88
AHEAD_BEHIND = 0/0
DIRTY = docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md (append-only continuity; intentional)

MASTER_LOG_TIP = §273
MASTER_LOG_SIZE = 2933546
MASTER_LOG_SHA256 = D4AF47604B79F362DC1A9E7A727362E6026F21A60AAF126C3EE2879FA09B35AB
MARKER = DB_PROD_01B_PASS_PRODUCTION_DATA_PLATFORM_GREEN
PRODUCTION_DATA_PLATFORM_GREEN = YES

CURSOR_HANDOFF = references/authoritative/Sedi_Master_Handoff_Section72_DBPROD01B_RuntimeCutoverGreen_v564_FA.md
HANDOFF_SIZE = 2179
HANDOFF_SHA256 = C08B6750A08F4ABDF7697B6357123AE1516E574F02AE615DF88D31C754FE9C40

CHATGPT_CONTINUITY_BASELINE = v574 (reconciled; no material contradiction)
ALEMBIC = 060_db03_w4_w6_scale_inspect_roles
APP_DB_RUNTIME = sedi_app_runtime
PGVECTOR_TODAY = NO
RAG_EMBEDDINGS_TODAY = NO
RAG_ACTIVATED = NO
CRAWLER_ACTIVATED = NO
```

`RULES_IN_FORCE_CHECK = PASS`

---

## 1. Mission (ARCHITECTURE DECISION)

Sedi V1 RAG is **not** “LLM + embeddings + vector DB”.

It is a **health-grade Context Intelligence Architecture**:

```text
AUTHORIZED PERSONAL CONTEXT
+ GOVERNED GLOBAL HEALTH KNOWLEDGE
+ SAFETY / CONSENT / PROVENANCE POLICY
→ GROUNDED CHAT / CARE / LIFESTYLE / NOTIFICATION BEHAVIOR
```

Frozen name:

```text
SEDI CONTEXT INTELLIGENCE STACK (SCIS)
```

---

## 2. Non-negotiable invariants (FROZEN)

```text
USER MEMORY != GLOBAL MEDICAL KNOWLEDGE
DEVICE DATA != MEDICAL TRUTH
RAW CRAWLER DATA != GOVERNED KNOWLEDGE
RAG INDEX != SOURCE OF TRUTH
RAW SOURCE != DIRECT RAG AUTHORITY
PERSONALIZATION SIGNAL != MEDICAL EVIDENCE
CAREGIVER RELATIONSHIP != AUTHORIZATION
NO INVENTED CLINICAL GOLDEN-WINDOW VALUES
ack_window_seconds / escalation_window_seconds remain NULL unless clinically authorized
```

Canonical knowledge flow (must not be bypassed):

```text
Source → Source Version → Raw Evidence → Parse/Extract → KnowledgeUnit
→ Knowledge Version/Memory → Governance/Safety → Runtime Eligibility
→ Retrieval Index → Grounded Context → Response
```

---

## 3. Layered control-flow (FROZEN)

```text
USER / CHAT / EVENT
        │
        ▼
INTENT + DOMAIN + SAFETY ROUTER
        │
        ├──────────────────────────────┐
        ▼                              ▼
PERSONAL CONTEXT PLANE          GLOBAL KNOWLEDGE PLANE
(structured + lexical +         (governed KU / chunks /
 optional deferred personal      hybrid lexical+vector)
 semantic index)
        │                              │
        ▼                              ▼
PERSONAL CONTEXT RESOLVER       GOVERNED RETRIEVAL + ELIGIBILITY
        │                              │
        └──────────────┬───────────────┘
                       ▼
              CONTROLLED CONTEXT FUSION
                       ▼
              RRF / optional rerank (deferred)
                       ▼
                 CONTEXT ASSEMBLY
                       ▼
                  LLM / REASONING
                       ▼
          GROUNDING + SAFETY VALIDATION
                       ▼
        CHAT | RECOMMENDATION | NOTIFICATION
                       ▼
                 USER REACTION → MEMORY / I7 / CARE
```

---

## 4. Personal Context Plane (FROZEN)

### Responsibilities
`PersonalContextResolver` selects **minimum sufficient authorized** user context — never dump full history.

### Context classes (V1)
| Class | Authority | Retrieval mode |
|---|---|---|
| Identity/profile | `users` + profile knowledge | Structured |
| Consent | `user_consents`, `user_consent_scopes` | Structured gate |
| LTM facts | `user_memory_facts` | Structured + relevance filter |
| Chat short-term | `memory` | Recent window |
| Period summaries | `user_period_summaries` (I7) | Structured by type/recency |
| Care | `care_episodes`, links, policies | Structured |
| Physio | `physiological_measurements` (+ rollups later) | Structured recent/trend |
| Notifications | `notifications`, feedback | Structured recent |
| Devices | `devices`, `device_events` | Structured lifecycle |
| Caregiver auth | relationships + consent scopes | Authorization gate only |

### Policies (FROZEN)
- Cross-user isolation mandatory (`user_id` scoped queries only).
- Consent checked before sensitive classes enter prompt.
- Missing info → labeled `UNKNOWN` — never invented.
- Temporal: prefer recency; I7 for longitudinal compression.
- Size: hard token budget with priority order (safety > care > LTM > physio > prefs > I7 > notif history).
- Personal semantic embeddings: **DEFERRED / PRIVACY-GATED** (see ADR-004). V1 personal retrieval is primarily structured SQL + lexical over user-owned text fields.

---

## 5. Global Knowledge Plane (FROZEN)

### Authorities
| Role | Table/service |
|---|---|
| Source identity | `governed_source_profiles` + versions |
| Raw evidence | `i5_raw_evidence` |
| Structured knowledge | `knowledge_units` + provenance/conflicts/safety reviews |
| Knowledge-memory | `knowledge_memory_items` (≠ user LTM) |
| Chunk index metadata | `knowledge_chunks` + `knowledge_chunk_embeddings` |
| Curated companion | Gate3 documents/chunks (bridge; not crawler SoT) |
| Iran local services | `iran_doctors/laboratories/hospitals` (directory-only; not medical KU) |

### Runtime eligibility
Must pass `runtime_eligibility_gate` / governance before index publication or retrieval.

### Metadata filters (logical; map to existing columns where present)
domain, population applicability, language, evidence/source authority, jurisdiction, version date, review/runtime eligibility, superseded/retracted/conflict, provenance locator, embedding/index version.

---

## 6. Retrieval pipeline stages (FROZEN V1)

| # | Stage | V1 | Failure |
|---|---|---|---|
| 1 | Conversation resolution | Required | Use last N turns; else fail closed on ambiguous medical rewrite |
| 2 | Intent + domain routing | Required | Default `general_safe` |
| 3 | Medical safety classification | Required | Escalate policy class; restrict recs |
| 4 | Query transform (rewrite) | Required | Preserve original query for audit |
| 5 | Personal context retrieval | Required | Empty personal pack OK if labeled |
| 6 | Knowledge eligibility filter | Required | Zero ineligible rows |
| 7 | Lexical candidate retrieval | Required | Empty → continue to vector/no-result |
| 8 | Vector candidate retrieval | Required (after vector enablement wave) | Fallback lexical-only |
| 9 | Hybrid fusion (RRF) | Required | Lexical-only / vector-only fallback |
| 10 | Metadata/governance filter | Required | Drop unsafe |
| 11 | Rerank | **Deferred optional** | Skip |
| 12 | Diversity / conflict detect | Required lightweight | Surface conflict label |
| 13 | Context budgeting | Required | Truncate by priority |
| 14 | Evidence assembly | Required | Labeled sections |
| 15 | Generation | Required | Model call |
| 16 | Grounding validation | Required | Refuse unsupported medical claims |
| 17 | Safety validation | Required | Safe degradation |
| 18 | Response / action | Required | Chat / rec / notif decision |

---

## 7. Safety routing (FROZEN)

Pre-retrieval classes (no clinical numeric thresholds invented):

```text
EMERGENCY_OR_URGENT_SYMPTOM
SELF_HARM_RISK
MEDICATION_SAFETY
DIAGNOSIS_SEEKING
ROUTINE_LIFESTYLE
DIRECTORY_LOCAL_SERVICE
GENERAL_HEALTH_EDUCATION
INSUFFICIENT_CONTEXT
```

Behavior principles:
- Urgent/self-harm → safety-first retrieval policy + restricted recommendation behavior + crisis-safe language.
- Device HR alone never diagnoses.
- Clinical windows remain NULL until authorized clinical Gate.

---

## 8. Fusion model (FROZEN)

Separate planes; fusion labels every item:

```text
USER_FACT | USER_PREFERENCE | USER_GOAL | USER_REPORTED_SYMPTOM
USER_MEASUREMENT | DERIVED_SIGNAL | CARE_CONTEXT | CAREGIVER_CONTEXT
GLOBAL_KNOWLEDGE | CLINICAL_GUIDANCE | LIFESTYLE_GUIDANCE | MODEL_INFERENCE | UNKNOWN
```

LLM must never treat `USER_MEASUREMENT` or `MODEL_INFERENCE` as `GLOBAL_KNOWLEDGE`.

---

## 9. I5 / I6 / I7 / I8 contracts (FROZEN; not implemented here)

### I5
Crawler → RawEvidence → KU → governance → **index publication**.  
Index is disposable. No direct crawler→runtime. Iran directory remains local-service discovery only.

### I6
Write/read/correct/supersede/invalidate LTM on `user_memory_facts` with consent + provenance.  
RAG reads via Personal Context Resolver only.

### I7
Consume `user_period_summaries` as compression layer, not SoT. Prefer facts/measurements when conflict.

### I8
Recommendations require authorized user context + goals + governed knowledge + safety constraints.  
Never vector-similarity alone. Incomplete context → ask / lower confidence / avoid personalization / higher-safety route.

---

## 10. Smart notifications contract (FROZEN)

```text
Event → Trigger → Context resolve → Knowledge retrieve → Policy/Safety
→ Eligibility → Personalized notification → Delivery → Reaction → Memory/Care feedback
```

Caregiver escalation requires relationship + consent + scope + policy — **not activated in this Gate**.

---

## 11. Heart-rate / telemetry boundary (FROZEN)

- Canonical: `physiological_measurements` (`measured_at` / `received_at`).
- Context may use: recent raw readings, rollups when present, quality flags, staleness labels, device trust.
- Must not invent baselines or clinical thresholds.
- Out-of-order / missing → labeled, not guessed.

---

## 12. Conversation continuity (FROZEN)

- Keep original user text + rewritten retrieval query.
- Resolve pronouns/ellipsis using recent turns + personal context.
- Re-run safety classification after rewrite.
- Medical meaning-preserving rewrite only; else ask clarify.

---

## 13. Chunking (FROZEN)

Not a universal char size.

Priority:
1. **Knowledge-unit-aware** chunks aligned to KU boundaries.
2. **Section-aware** for long guidelines (contraindications kept atomic).
3. Parent/child optional for long docs.
4. Overlap modest; preserve provenance locator to RawEvidence/SourceVersion.
5. Re-chunk on source/parser/chunker/knowledge version change → new index version.

Exact max/min sizes: `TO_BE_BASELINED` in implementation Wave A.

---

## 14. Technology freeze

### Search / vector backend — ADR-003
**Decision:** PostgreSQL 16 + **pgvector** (install only in implementation Gate) + native PostgreSQL FTS + **RRF hybrid**.

Evidence:
- Production already PostgreSQL 16.14; operational continuity.
- Official pgvector documents hybrid with Postgres FTS and RRF ([pgvector GitHub](https://github.com/pgvector/pgvector/), access 2026-08-10).
- Existing Sedi path already encodes `knowledge_chunk_embeddings.backend_kind ∈ {JSON_INLINE, EXTERNAL_VECTOR_DEFERRED}`.

Rejected for V1: dedicated managed vector DB (ops/HA/cost/deadline) unless scale evidence later.

**Not installed now.** `PGVECTOR_INTRODUCED` remains false until implementation Gate.

Stage17 `rag_embeddings` remains **NONCANONICAL / DEPRECATE**.

### Embedding strategy — ADR-004
**Global governed knowledge (default):**
- Primary freeze: **Cohere `embed-multilingual-v3.0`** (1024-d) — official Cohere docs explicitly list Persian (`fa`) and Arabic (`ar`) ([docs.cohere.com/docs/cohere-embed](https://docs.cohere.com/docs/cohere-embed), access 2026-08-10).
- Wave A may **evaluate** Cohere `embed-v4.0` @1024 (latest official model; truncatable dims) and pin only after EN/FA/AR medical retrieval eval — not silently substituted here.
- Alternate/fallback: OpenAI `text-embedding-3-large` with `dimensions=1024` ([OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings), access 2026-08-10).

**Personal/PHI plane:**
- V1: **no external embedding of raw personal content by default**.
- Personal retrieval = structured + lexical.
- Optional personal embeddings require explicit privacy Gate / product-owner approval.

Freeze fields: `embedding_model`, `embedding_dim`, `embedding_version`, L2-normalize policy, batch/retry, dual-index migration on model change.

Final provider pin for Production global index: **confirm secrets/billing availability in implementation Wave A** (architecture frozen; vendor account wiring is ops).

### Hybrid retrieval — ADR-006
**Required:** lexical (Postgres FTS; language configs for en + best-effort fa/ar) + vector + RRF.

### Reranking — ADR-007
**Deferred optional** for V1 MVP. Measure lift in eval harness; enable only if latency/cost budget allows.

---

## 15. Provenance / citations (FROZEN)

```text
Claim → ContextItem → Chunk → KU/Version → RawEvidence → SourceVersion → Source
```

Healthcare responses: auditable internal provenance required; user-visible citations where product UX allows.

---

## 16. Stale / superseded / retracted (FROZEN)

Ineligible knowledge must not enter final context. Index rebuild/publication is the mechanism; DB authorities remain SoT.

---

## 17. Multilingual EN/FA/AR (FROZEN)

- Prefer same-language retrieval when source language matches.
- Multilingual embeddings for global plane.
- Preserve source language in citations; response language follows user.
- Uncontrolled translation of clinical meaning forbidden; if translate for retrieval, keep original evidence text in assembly.

---

## 18. Context assembly labels (FROZEN)

```text
SAFETY CONSTRAINTS
USER FACTS / PREFERENCES / GOALS
RECENT USER STATE / CARE CONTEXT
DEVICE OBSERVATIONS
GOVERNED MEDICAL KNOWLEDGE
GOVERNED LIFESTYLE KNOWLEDGE
EVIDENCE / PROVENANCE
UNKNOWN / MISSING
```

Token budget priority as §4. No raw DB row dumps.

---

## 19. Grounding / fallback (FROZEN)

Unsupported medical claim → refuse/degrade.  
No results / provider failure → safe educational-or-clarify path — **never ungrounded clinical generation**.

---

## 20. Security / privacy (FROZEN)

- Tenant isolation via `user_id` + role `sedi_app_runtime`.
- Consent-aware retrieval.
- No PHI in logs by default; trace IDs only.
- External embed/rerank: **global public governed text only** unless privacy Gate expands.
- Secrets via existing Production secret mechanism.

---

## 21. Evaluation framework (FROZEN)

Required suites: clinical factual, care, nutrition/exercise/lifestyle, EN/FA/AR, multi-turn, personal relevance, consent/cross-user isolation (=0 leakage), stale/retracted exclusion (=0), safety routing, HR context, citations, no-result fallback.

Metrics: Recall@K, Precision@K, MRR/nDCG, groundedness, citation correctness, unsupported claim rate, leakage=0, latency p50/p95, cost/query.  
Numeric thresholds: `TO_BE_BASELINED` in Wave D.

---

## 22. Observability (FROZEN)

trace_id, intent, domain, safety_route, strategy, candidate/eligible/filtered counts+reasons, evidence IDs, KU/embedding/index versions, context size, model versions, grounding result, fallback, latency, cost, error class — without sensitive raw content.

---

## 23. Index lifecycle (FROZEN)

initial → incremental → weekly I5 update → version/governance changes → rebuild/rollback → consistency verify.  
Blue/green index versions via `embedding_version` / index generation id.

---

## 24. Current → target reconciliation

| Component | Disposition |
|---|---|
| `knowledge_chunk_embeddings` JSON_INLINE | KEEP → EXTEND to pgvector backend_kind |
| `kb_hybrid_retrieval` / `kb_embedding_service` | KEEP → EXTEND hybrid RRF |
| `runtime_knowledge_retrieval` + eligibility gate | KEEP |
| I5 GSP / RawEvidence / KU / knowledge_memory | KEEP |
| `user_memory_facts` / consents | KEEP; I6 package NEW |
| `user_period_summaries` | KEEP; I7 jobs/API NEW |
| Gate3 care recommendations | KEEP; I8 NEW beside |
| Notifications + Gate4 | KEEP; proactive RAG contract EXTEND |
| `physiological_measurements` | KEEP |
| Stage17 `rag_embeddings` / local_rag vector_provider | DEPRECATE / remove from runtime path |
| `services/rag.py` stubs | REPLACE with SCIS interfaces |
| `rag_context` builder | EXTEND as Personal+Fusion assembler |
| Iran directory | KEEP directory-only |

---

## 25. Implementation waves (DEFINED)

```text
Wave A — Core SCIS contracts, chunk/embed pipeline, pgvector enablement (impl Gate)
Wave B — Personal Context Resolver + I6 interfaces
Wave C — I7 longitudinal consumption
Wave D — Eval harness + safety + observability
Wave E — I5 governed index publication
Wave F — I8 recommendation integration
Wave G — Smart notification proactive context
Wave H — Frontend / E2E
```

Parallelism: A∥D early; B∥C after A contracts; E after A eligibility; F/G after B+E; H last.

Critical path: **A → B → E → D green → F/G → H**

```text
END_OF_MORDAD_RISK_BEFORE = HIGH (RAG undefined)
END_OF_MORDAD_RISK_AFTER  = MODERATE (architecture frozen; implementation remains)
PARALLELIZATION_GAIN = QUALITATIVE (waves B/C/D parallelizable after A contracts)
```

---

## 26. Next implementation Gate (EXACT — NOT AUTHORIZED)

```text
TITLE =
SEDI-V1 SCIS-01 CORE RETRIEVAL CONTRACTS
+ CHUNK/EMBED PIPELINE
+ PGVECTOR ENABLEMENT
+ HYBRID RRF
+ EVAL HARNESS SKELETON-01

GOAL =
Implement Wave A (+ eval skeleton) without activating crawler/RAG in Production.

ALLOWLIST =
repository backend services/tests/migrations for pgvector + KCE backend_kind extension;
CI rehearsal; no Production apply without separate Production Gate.

DENYLIST =
crawler activation; Production RAG on; caregiver escalation; clinical window invention;
Stage17 rag_embeddings revival; unrelated features.

NEXT_GATE_AUTHORIZED = NO
```

---

## 27. Verdict fields

```text
AUTHORITY_RECONCILED = YES
DATA_PLATFORM_BASELINE_PRESERVED = YES
FINAL_RAG_ARCHITECTURE = FROZEN
PERSONAL_CONTEXT_ARCHITECTURE = FROZEN
GLOBAL_KNOWLEDGE_ARCHITECTURE = FROZEN
USER_KNOWLEDGE_FUSION = FROZEN
MEDICAL_SAFETY_ARCHITECTURE = FROZEN
MULTILINGUAL_ARCHITECTURE = FROZEN
PROVENANCE_ARCHITECTURE = FROZEN
I5_RAG_CONTRACT = FROZEN
I6_RAG_CONTRACT = FROZEN
I7_RAG_CONTRACT = FROZEN
I8_RAG_CONTRACT = FROZEN
SMART_NOTIFICATION_RAG_CONTRACT = FROZEN
TELEMETRY_CONTEXT_BOUNDARY = FROZEN
EVALUATION_FRAMEWORK = FROZEN
SECURITY_PRIVACY_BOUNDARY = FROZEN
TECHNOLOGY_STACK_FROZEN = YES
IMPLEMENTATION_WAVES_DEFINED = YES
NEXT_IMPLEMENTATION_GATE_DEFINED = YES
RAG_ACTIVATED = NO
CRAWLER_ACTIVATED = NO
PRODUCTION_CHANGED = NO
OPEN_CRITICAL_FINDINGS = 0
OPEN_NONCRITICAL_FINDINGS = 2
  (1) exact global embedding vendor pin pending secrets/billing confirmation in Wave A
  (2) FA/AR FTS dictionary quality TO_BE_BASELINED
END_OF_MORDAD_RISK = MODERATE
GATE_RESULT = PASS
```
