# NEXT IMPLEMENTATION GATE — EXACT SPEC (UNAUTHORIZED)

```text
TITLE =
SEDI-V1 SCIS-01 CORE RETRIEVAL CONTRACTS
+ CHUNK/EMBED PIPELINE
+ PGVECTOR ENABLEMENT
+ HYBRID RRF
+ EVAL HARNESS SKELETON-01

GATE_AUTHORIZED = NO
REQUIRES = Explicit Javad authorization
PREDECESSOR = SEDI-V1 FINAL PROFESSIONAL RAG ARCHITECTURE DESIGN FREEZE-01 (PASS / FROZEN)
ARCHITECTURE_AUTHORITY =
  docs/architecture/rag-freeze-01/SEDI_V1_FINAL_PROFESSIONAL_RAG_ARCHITECTURE_DESIGN_FREEZE_01.md
  docs/architecture/rag-freeze-01/ADR_RAG_001_TO_020.md
```

## Goal

Implement Wave A of SCIS (Sedi Context Intelligence Stack): core retrieval contracts, chunk/embed pipeline for **global governed knowledge**, PostgreSQL pgvector enablement, hybrid lexical+vector RRF, and evaluation harness skeleton — **without** activating crawler or Production RAG serving.

## Scope (allowlist)

```text
- backend service interfaces for SCIS stages (router stubs, personal resolver contract, global retrieval, fusion assembler contracts)
- knowledge chunker (KU/section-aware) + embedding writer for global plane
- Alembic migration to enable pgvector + KCE backend_kind extension (JSON_INLINE → VECTOR/pgvector path)
- hybrid RRF retrieval path extending kb_hybrid_retrieval / runtime_knowledge_retrieval
- eval harness skeleton + fixture packs (empty/baselining)
- unit/integration tests + CI job(s)
- documentation updates for SCIS-01 evidence
- CI rehearsal / non-Production apply proofs
```

## Denylist

```text
- crawler activation
- Production RAG activation / Production traffic to new retrieval
- caregiver escalation activation
- invent clinical golden-window values
- revive Stage17 rag_embeddings / local_rag as canonical path
- external embed of personal/PHI content
- unrelated frontend features
- force push / merge to main without separate authority
- Production migration apply without separate Production Gate
```

## Expected files/components

```text
backend/app/services/scis/          (NEW package — contracts + pipeline)
backend/app/services/knowledge/     (EXTEND hybrid/embed)
backend/alembic/versions/061_*      (pgvector + index columns — ONLY in authorized Gate)
backend/tests/test_scis_*
backend/tests/eval/scis_*
.github/workflows/*                 (CI for SCIS-01)
docs/architecture/rag-freeze-01/*   (implementation evidence pointers)
```

## Implementation sequence

```text
1. Land SCIS contracts from frozen ADRs (no behavior activation flags default OFF)
2. Chunker + provenance-preserving chunk identity/version
3. Embedding client (Cohere multilingual-v3.0 primary; OpenAI alternate) + version fields
4. Migration: CREATE EXTENSION vector; KCE vector column / backend_kind; grants via sedi_migration_admin path
5. Hybrid lexical + vector + RRF
6. Eligibility filter before final context
7. Eval harness skeleton + golden fixture stubs
8. CI green; Production apply = SEPARATE Gate
```

## Parallel workstreams

```text
A1 contracts/tests  ∥  A2 chunker design fixtures  ∥  A3 eval harness skeleton
A4 embed client after A1
A5 migration after A1 contracts freeze in code
A6 hybrid after A5
```

## Test plan

```text
- unit: chunk identity, eligibility exclusion, RRF fusion, label fusion
- isolation: cross-user leakage = 0 tests
- retracted/superseded exclusion = 0 tests
- migration rehearsal (non-Production)
- no Production activation flag ON in default config
```

## CI plan

```text
- pytest scis + knowledge hybrid
- alembic heads / rehearsal job
- deny Stage17 rag_embeddings revival assertions retained
```

## Runtime proof (non-Production)

```text
- local/CI DB with pgvector
- sample governed KU indexed → hybrid retrieve → labeled context pack
- RAG_ACTIVATED remains NO in Production
```

## Auto-remediation boundaries

```text
MAX_AUTO_REMEDIATION_CYCLES = 5
In-scope: test/CI/doc/config mistakes within allowlist
Out-of-scope: Production apply, clinical policy invention, privacy expansion
```

## Hard stops

```text
- schema/ORM needed beyond frozen ADR without new design Gate
- requirement to embed PHI externally
- Production apply without Production Gate
- clinical window invention
- authority contradiction with freeze docs
```

## Evidence requirements

```text
commit SHAs, migration identity, CI run IDs, extension present in rehearsal,
backend_kind evidence, hybrid query evidence, eval skeleton paths, EOL/SHA for Master Log append
```

## Continuity closure (at end of SCIS-01)

```text
Master Log append, Cursor handoff successor, ChatGPT continuity bump
NEXT after SCIS-01 = Wave B Personal Context Resolver / I6 interfaces (proposed, unauthorized)
```
