# app/services/memory/memory_repository.py
"""
Memory Repository - CRUD operations for UserMemoryFact.

Handles upsert logic (update if exists, insert if not).
"""

from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from datetime import datetime
import json

from app.models import UserMemoryFact
from app.services.memory.memory_contract import MemoryContract


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
        Upsert a memory fact (update if exists, insert if not).
        
        Args:
            user_id: User ID
            domain: Memory domain (e.g., "lifestyle")
            key: Fact key (e.g., "sleep_duration_hours")
            value: Fact value (will be stored as JSON)
            confidence: Confidence score (0.0 to 1.0)
            source: Source of fact ("chat" | "device" | "manual")
        
        Returns:
            UserMemoryFact object
        """
        # Validate domain and key
        is_valid, error_msg = MemoryContract.validate_fact(domain, key)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Convert value to JSON string
        value_json = json.dumps(value)
        
        # Check if fact already exists
        existing = (
            self.db.query(UserMemoryFact)
            .filter(
                UserMemoryFact.user_id == user_id,
                UserMemoryFact.domain == domain,
                UserMemoryFact.key == key
            )
            .first()
        )
        
        if existing:
            # Update existing fact
            existing.value_json = value_json
            existing.confidence = confidence
            existing.source = source
            existing.last_seen_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            self.db.add(existing)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # Create new fact
            new_fact = UserMemoryFact(
                user_id=user_id,
                domain=domain,
                key=key,
                value_json=value_json,
                confidence=confidence,
                source=source,
                last_seen_at=datetime.utcnow(),
                embedding_id=None,  # RAG-ready, not active
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(new_fact)
            self.db.commit()
            self.db.refresh(new_fact)
            return new_fact
    
    def get_fact(
        self,
        user_id: int,
        domain: str,
        key: str
    ) -> Optional[UserMemoryFact]:
        """Get a specific memory fact"""
        return (
            self.db.query(UserMemoryFact)
            .filter(
                UserMemoryFact.user_id == user_id,
                UserMemoryFact.domain == domain,
                UserMemoryFact.key == key
            )
            .first()
        )
    
    def get_facts_by_domain(
        self,
        user_id: int,
        domain: str
    ) -> List[UserMemoryFact]:
        """Get all facts for a user in a specific domain"""
        return (
            self.db.query(UserMemoryFact)
            .filter(
                UserMemoryFact.user_id == user_id,
                UserMemoryFact.domain == domain
            )
            .all()
        )
    
    def get_all_facts(
        self,
        user_id: int
    ) -> List[UserMemoryFact]:
        """Get all memory facts for a user"""
        return (
            self.db.query(UserMemoryFact)
            .filter(UserMemoryFact.user_id == user_id)
            .all()
        )
    
    def delete_fact(
        self,
        user_id: int,
        domain: str,
        key: str
    ) -> bool:
        """Delete a memory fact"""
        fact = self.get_fact(user_id, domain, key)
        if fact:
            self.db.delete(fact)
            self.db.commit()
            return True
        return False
