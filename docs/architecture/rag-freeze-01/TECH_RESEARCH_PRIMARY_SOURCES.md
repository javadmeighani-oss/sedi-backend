# RAG FREEZE-01 — Primary-source technology research notes

```text
ACCESS_DATE = 2026-08-10
GATE = SEDI-V1 FINAL PROFESSIONAL RAG ARCHITECTURE DESIGN FREEZE-01
```

## pgvector / hybrid

| Field | Value |
|---|---|
| OPTION | PostgreSQL + pgvector + FTS + RRF |
| PRIMARY EVIDENCE | https://github.com/pgvector/pgvector (official repo; hybrid search with Postgres full-text; RRF documented) |
| ACCESS | 2026-08-10 |
| Sedi advantages | Co-locates with Production PG 16.14; metadata filters with KU/eligibility; fits `knowledge_chunk_embeddings.backend_kind` |
| Sedi disadvantages | ANN scale ceiling vs dedicated vector DB; extension upgrade discipline |
| Ops | Install only in implementation Gate; no Production change in this Gate |
| Cost | Extension OSS; no new SaaS HA plane |
| Deadline | Lower than introducing new vector SaaS |
| DECISION | FROZEN as V1 direction (ADR-RAG-003) |

## Embeddings — Cohere

| Field | Value |
|---|---|
| OPTION A (primary freeze) | `embed-multilingual-v3.0` @ 1024-d |
| PRIMARY EVIDENCE | https://docs.cohere.com/docs/cohere-embed (official; lists `fa` Persian + `ar` Arabic in supported languages) |
| OPTION A' (Wave A eval) | `embed-v4.0` @ 1024 (latest model; truncatable dims 256/512/1024/1536) — pin only after EN/FA/AR medical eval |
| ACCESS | 2026-08-10 |
| DECISION | Architecture freeze: multilingual-v3.0 primary; v4 pin deferred to Wave A empirical eval |

## Embeddings — OpenAI alternate

| Field | Value |
|---|---|
| OPTION | `text-embedding-3-large` with `dimensions=1024` |
| PRIMARY EVIDENCE | https://developers.openai.com/api/docs/guides/embeddings ; https://developers.openai.com/api/reference/resources/embeddings/methods/create |
| ACCESS | 2026-08-10 |
| NOTE | Native 3072-d; dimensions API shortens (example docs cite 1024) |
| DECISION | Alternate/fallback for global plane (ADR-RAG-004) |

## Personal embeddings privacy

| Field | Value |
|---|---|
| DECISION | No default external embedding of personal/PHI content in V1 |
| CLASS | ARCHITECTURE DECISION + privacy hard-stop if product wants otherwise |

## Rerank

| Field | Value |
|---|---|
| DECISION | Deferred optional; no vendor pin without latency/cost baseline |
| CLASS | ARCHITECTURE DECISION |
