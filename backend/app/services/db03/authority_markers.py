"""DB-03 deprecated / canonical authority markers (§270)."""

DEPRECATED_AUTHORITIES = {
    "health_data": "physiological_measurements",
    "daily_memory_summaries": "user_period_summaries",
    "user_facts": "user_memory_facts",
    "kc_user_facts": "user_memory_facts",
    "user_profile_facts": "user_memory_facts",
    "knowledge_sources_crawler_authority": "governed_source_profiles",
    "stage17_rag_embeddings": "knowledge_chunk_embeddings",
}

# §270.L — ANY (OR) semantics, not ALL
PARTITION_TRIGGERS_ANY = (
    "active_devices >= 1000",
    "physiological_measurements rows >= 50_000_000",
    "p95 user/time range query latency SLO breach (ops Gate)",
)

PARTITIONING_ACTIVATED = False
PGVECTOR_INTRODUCED = False
RAG_EMBEDDINGS_INTRODUCED = False
