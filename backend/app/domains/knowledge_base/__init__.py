"""Knowledge base domain — re-exports current Gate 3 services (no import path break)."""

from backend.app.services.gate3.knowledge_base_service import (  # noqa: F401
    create_source,
    ingest_content,
    list_sources,
)
from backend.app.services.gate3.knowledge_update_service import KnowledgeUpdateService  # noqa: F401
from backend.app.services.gate3.knowledge_retrieval_service import search_knowledge  # noqa: F401
