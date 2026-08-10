# ADR Pack — SEDI RAG FREEZE-01 (ADR-RAG-001 … 020)

```text
GATE = SEDI-V1 FINAL PROFESSIONAL RAG ARCHITECTURE DESIGN FREEZE-01
PARENT = docs/architecture/rag-freeze-01/SEDI_V1_FINAL_PROFESSIONAL_RAG_ARCHITECTURE_DESIGN_FREEZE_01.md
STATUS = FROZEN
```

Each ADR: Context / Options / Evidence / Decision / Why / Rejected / Tradeoffs / Risks / Implementation consequence / Revisit trigger.

---

## ADR-RAG-001 — Retrieval source-of-truth boundary

**Context:** Risk that vector index becomes SoT.  
**Options:** (A) Index as SoT (B) DB authorities as SoT, index disposable.  
**Evidence:** Existing I5/KU/`knowledge_chunk_embeddings`; Stage17 `rag_embeddings` marked NONCANONICAL.  
**Decision:** **(B)** DB governed authorities are SoT; retrieval index rebuildable.  
**Why:** Provenance, retraction, governance.  
**Rejected:** Index-as-SoT.  
**Tradeoffs:** Rebuild cost vs safety.  
**Risks:** Stale index if publication lag.  
**Impl:** Index version + consistency checks.  
**Revisit:** Material scale where rebuild SLA fails.

---

## ADR-RAG-002 — Personal/global retrieval-plane separation

**Context:** Merging personal + global corpora invites leakage and false medical grounding.  
**Options:** (A) Single corpus (B) Two planes + fusion.  
**Evidence:** Gate invariants; separate tables (`user_memory_facts` vs `knowledge_units`).  
**Decision:** **(B)** Personal Context Plane ≠ Global Knowledge Plane; controlled fusion only.  
**Why:** Isolation + correct epistemic labeling.  
**Rejected:** Undifferentiated RAG corpus.  
**Tradeoffs:** Dual pipelines.  
**Risks:** Fusion bugs.  
**Impl:** Separate resolvers + labeled assembly.  
**Revisit:** Never merge planes without new Gate.

---

## ADR-RAG-003 — Search/vector backend

**Context:** pgvector not installed; Production PG 16; KCE has EXTERNAL_VECTOR_DEFERRED.  
**Options:** (A) PG+pgvector+FTS hybrid (B) Dedicated vector DB (C) Managed search SaaS only (D) Lexical-only forever.  
**Evidence:** [pgvector](https://github.com/pgvector/pgvector/) hybrid FTS+RRF docs (access 2026-08-10); Production already PG16; ops continuity after DB-PROD-01B.  
**Decision:** **(A)** PostgreSQL 16 + pgvector + FTS + RRF. Install only in implementation Gate.  
**Why:** Fits current topology, metadata filter co-location, lower new HA surface for V1.  
**Rejected:** B/C for V1 (ops/deadline); D insufficient for multilingual semantics.  
**Tradeoffs:** ANN scale limits vs dedicated.  
**Risks:** Extension upgrade discipline.  
**Impl:** Wave A migration + role grants for `sedi_migration_admin`.  
**Revisit:** Knowledge volume/latency evidence exceeds PG ANN comfort.

---

## ADR-RAG-004 — Embedding strategy

**Context:** EN/FA/AR + medical vocab; personal PHI privacy.  
**Options:** (A) Cohere multilingual v3 global (B) OpenAI text-embedding-3-large dims=1024 (C) Local OSS only (D) Embed personal+global same external API.  
**Evidence:** Cohere Embed Multilingual v3.0 1024-d ([docs.cohere.com/docs/cohere-embed](https://docs.cohere.com/docs/cohere-embed)); OpenAI embeddings dims truncation ([developers.openai.com](https://developers.openai.com/api/docs/guides/embeddings)); access 2026-08-10.  
**Decision:**  
- **Global:** Primary **Cohere `embed-multilingual-v3.0` (1024)**; alternate OpenAI `text-embedding-3-large` @1024.  
- **Personal:** **No default external embedding of PHI**; structured+lexical V1.  
**Why:** Multilingual family + privacy boundary.  
**Rejected:** D; single-language English-only embedders as sole path.  
**Tradeoffs:** Vendor dependency; dual-index on switch.  
**Risks:** Billing/region availability (OPEN_NONCRITICAL).  
**Impl:** Versioned `embedding_model`/`embedding_version`; dual-index migration.  
**Revisit:** Privacy Gate for personal embeddings; vendor SLA failure.

---

## ADR-RAG-005 — Chunking strategy

**Context:** Arbitrary fixed chunk size harms clinical atomicity.  
**Options:** (A) Fixed tokens (B) KU/section-aware (C) Semantic-only splitter.  
**Evidence:** KU model + RawEvidence provenance requirements.  
**Decision:** **(B)** KU-aware + section-aware; contraindications atomic; parent/child optional.  
**Why:** Provenance + safety.  
**Rejected:** Universal fixed size as sole strategy.  
**Tradeoffs:** More complex chunker.  
**Risks:** Over-chunking long guidelines.  
**Impl:** Wave A; sizes TO_BE_BASELINED.  
**Revisit:** Eval shows recall failure on long docs.

---

## ADR-RAG-006 — Hybrid retrieval

**Context:** Medical terms + FA/AR variants + semantics.  
**Options:** (A) Vector-only (B) Lexical-only (C) Hybrid RRF.  
**Evidence:** pgvector official hybrid+RRF guidance.  
**Decision:** **(C)** Hybrid lexical + vector with RRF.  
**Why:** Exact terms + semantic recall.  
**Rejected:** A/B as sole V1 strategies.  
**Tradeoffs:** Dual query cost.  
**Risks:** FA/AR FTS dictionary quality (OPEN_NONCRITICAL).  
**Impl:** Wave A.  
**Revisit:** Eval MRR plateau.

---

## ADR-RAG-007 — Reranking

**Context:** Quality vs latency/cost.  
**Options:** (A) Required Cohere/OpenAI rerank (B) Deferred optional (C) Never.  
**Evidence:** No Sedi latency baseline yet.  
**Decision:** **(B)** Deferred optional; RRF first; measure lift in Wave D.  
**Why:** Avoid premature cost/latency without baseline.  
**Rejected:** A as hard V1 dependency.  
**Tradeoffs:** Possible quality gap.  
**Risks:** Medical ranking miss → mitigated by eligibility+grounding.  
**Impl:** Interface stub; enable behind flag.  
**Revisit:** Eval shows material lift within budget.

---

## ADR-RAG-008 — Multilingual retrieval

**Context:** Product EN/FA/AR; design English.  
**Options:** (A) Translate-all-to-EN (B) Same-lang prefer + multilingual embeds (C) Separate monolingual indexes only.  
**Decision:** **(B)** Prefer same-language; multilingual embeds for global; preserve source language in evidence assembly.  
**Why:** Reduce meaning loss.  
**Rejected:** Uncontrolled translate-as-authority.  
**Tradeoffs:** Multi-index complexity.  
**Risks:** Cross-lang medical mistranslation.  
**Impl:** language metadata filters.  
**Revisit:** Cross-lang eval failure.

---

## ADR-RAG-009 — Context fusion

**Context:** Observation vs evidence vs inference confusion.  
**Options:** (A) Flat concat (B) Labeled epistemic fusion.  
**Decision:** **(B)** Labeled classes in assembly (USER_FACT, MEASUREMENT, GLOBAL_KNOWLEDGE, MODEL_INFERENCE, UNKNOWN…).  
**Why:** Safety + audit.  
**Rejected:** Undifferentiated dump.  
**Tradeoffs:** Prompt tokens for labels.  
**Risks:** Mislabel bugs.  
**Impl:** Fusion assembler contract.  
**Revisit:** New context class needed.

---

## ADR-RAG-010 — Medical safety routing

**Context:** Post-only validation insufficient.  
**Options:** (A) Post-gen only (B) Pre-retrieval + post-gen.  
**Decision:** **(B)** Safety/urgency classification before retrieval/generation; no invented clinical windows.  
**Why:** Gate §11.  
**Rejected:** A.  
**Tradeoffs:** Router complexity.  
**Risks:** Over/under routing.  
**Impl:** Safety route enum + policy packs.  
**Revisit:** Clinical policy authorization Gate.

---

## ADR-RAG-011 — Provenance/citation

**Context:** Healthcare auditability.  
**Options:** (A) No citations (B) Full chain with internal always + user-visible when UX allows.  
**Decision:** **(B)** Full chain required internally.  
**Why:** Invariants.  
**Rejected:** A.  
**Tradeoffs:** Storage/logging discipline.  
**Risks:** Broken links on rebuild — mitigate with KU ids.  
**Impl:** Evidence IDs in observability.  
**Revisit:** UX citation product Gate.

---

## ADR-RAG-012 — Index lifecycle

**Context:** Weekly I5 + governance changes.  
**Options:** (A) Mutate in place blindly (B) Versioned publish/rebuild/rollback.  
**Decision:** **(B)** Versioned index generations; blue/green via embedding/index version.  
**Why:** Retraction/supersession.  
**Rejected:** A.  
**Tradeoffs:** Dual storage briefly.  
**Risks:** Drift.  
**Impl:** publication jobs + consistency verify.  
**Revisit:** Publish lag SLA.

---

## ADR-RAG-013 — I5 publication contract

**Context:** Crawler must not publish directly.  
**Decision:** Governed path only: RawEvidence→KU→governance→runtime eligibility→index. Iran directory ≠ medical KU.  
**Why:** I5 identity.  
**Rejected:** Direct crawler indexing.  
**Impl:** Wave E.  
**Revisit:** New source class.

---

## ADR-RAG-014 — I6 memory integration

**Context:** I6 service not implemented; DB precursor exists.  
**Decision:** RAG reads LTM only via Personal Context Resolver; writes/corrections/supersession owned by future I6 Gate. Consent + cross-user isolation mandatory.  
**Why:** Separation of duties.  
**Rejected:** RAG writing memory ad hoc.  
**Impl:** Wave B interfaces.  
**Revisit:** I6 product Gate.

---

## ADR-RAG-015 — I7 longitudinal integration

**Context:** `user_period_summaries` DAILY/WEEKLY/MONTHLY/YEARLY.  
**Decision:** I7 is compression for longitudinal context — not SoT; prefer facts/measurements on conflict.  
**Why:** Avoid false truth.  
**Impl:** Wave C.  
**Revisit:** Summary quality eval.

---

## ADR-RAG-016 — I8 recommendation integration

**Context:** Recs must not be nearest-neighbor only.  
**Decision:** Authorized context + goals + state + governed knowledge + safety + history + preferences; incomplete → ask/lower confidence/avoid personalization/higher-safety.  
**Impl:** Wave F.  
**Revisit:** Domain-specific rec policies.

---

## ADR-RAG-017 — Smart notification integration

**Context:** Proactive Sedi must share SCIS, not silo.  
**Decision:** Same planes + safety + eligibility; reaction feedback loop; caregiver escalation not activated.  
**Impl:** Wave G.  
**Revisit:** Fatigue policy Gate.

---

## ADR-RAG-018 — Device/telemetry boundary

**Context:** HR ~5 min; `physiological_measurements`.  
**Decision:** Observations labeled; no diagnosis from device alone; staleness/quality/out-of-order labeled; no invented baselines/windows.  
**Impl:** Personal Context Resolver physio pack.  
**Revisit:** New gadget types (separate Gate).

---

## ADR-RAG-019 — Security/privacy

**Context:** External providers + PHI.  
**Decision:** Global public governed text may use external embed; personal PHI not externally embedded by default; least privilege `sedi_app_runtime`; no sensitive raw logs.  
**Rejected:** Assume blanket third-party PHI processing approval.  
**Impl:** Privacy checks in pipelines.  
**Revisit:** Product-owner privacy Gate.

---

## ADR-RAG-020 — Evaluation/observability

**Context:** Cannot ship without proof harness.  
**Decision:** Mandatory eval suites + metrics with thresholds TO_BE_BASELINED; required telemetry fields without PHI dumps.  
**Impl:** Wave D (+ skeleton in Wave A Gate).  
**Revisit:** After first baseline run.
