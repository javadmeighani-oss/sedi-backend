# app/services/memory/memory_repository.py
"""
Memory Repository - CRUD operations for UserMemoryFact.

Active reads/writes go through canonical I6 semantics (consent, active status,
soft-invalidation, expiry, vocabulary canonicalization). Direct ORM access is
not used for product paths.
"""

from sqlalchemy.orm import Session
from typing import Optional, Any, List

from backend.app.models import UserMemoryFact
from backend.app.services.i6.consent_service import ConsentDenied
from backend.app.services.i6.memory_writes import (
    delete_fact as i6_delete_fact,
    get_readable_fact_or_none,
    list_facts_or_empty,
    write_fact,
)
from backend.app.services.memory.memory_contract import MemoryContract


class MemoryRepository:
    """Repository for UserMemoryFact CRUD operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def upsert_fact(
        self,
        user_id: int,
        domain: str,
        key: str,
        value: Any,
        confidence: float = 0.7,
        source: str = "manual"
    ) -> UserMemoryFact:
        """
        Upsert a memory fact through canonical I6 write_fact (consent-gated).
        """
        domain, key = MemoryContract.canonicalize_key(domain, key)
        return write_fact(
            self.db,
            user_id,
            domain,
            key,
            value,
            source=source,
            provenance_class="USER_STATED",
            commit=True,
        )
    
    def get_fact(
        self,
        user_id: int,
        domain: str,
        key: str
    ) -> Optional[UserMemoryFact]:
        """Get a specific memory fact using canonical I6 read semantics."""
        return get_readable_fact_or_none(self.db, user_id, domain, key)
    
    def get_facts_by_domain(
        self,
        user_id: int,
        domain: str
    ) -> List[UserMemoryFact]:
        """Get active, unexpired, non-invalidated facts for a domain."""
        return list_facts_or_empty(self.db, user_id, domain=domain)
    
    def get_all_facts(
        self,
        user_id: int
    ) -> List[UserMemoryFact]:
        """Get all canonical-readable memory facts for a user."""
        return list_facts_or_empty(self.db, user_id)
    
    def delete_fact(
        self,
        user_id: int,
        domain: str,
        key: str
    ) -> bool:
        """Forget a memory fact through canonical I6 delete (PERM_FORGET)."""
        try:
            return i6_delete_fact(self.db, user_id, domain, key, commit=True)
        except ConsentDenied:
            return False
