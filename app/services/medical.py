# app/services/medical.py
"""
Medical Service - Condition Detection & Lookup

Responsibility:
- Detect medical conditions from health data
- Lookup conditions and medications
- Manage user condition assignments
- RAG-ready (embedding_id fields available for future integration)
"""

from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.models import MedicalCondition, Medication, UserCondition, User, HealthData


class MedicalService:
    """Service for medical condition detection and management"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # -------------------- Condition Lookup --------------------
    
    def get_all_conditions(self) -> List[MedicalCondition]:
        """Get all available medical conditions"""
        return self.db.query(MedicalCondition).all()
    
    def get_condition_by_id(self, condition_id: int) -> Optional[MedicalCondition]:
        """Get a medical condition by ID"""
        return self.db.query(MedicalCondition).filter(MedicalCondition.id == condition_id).first()
    
    def get_condition_by_name(self, name: str) -> Optional[MedicalCondition]:
        """Get a medical condition by name (case-insensitive)"""
        return self.db.query(MedicalCondition).filter(
            MedicalCondition.name.ilike(f"%{name}%")
        ).first()
    
    # -------------------- User Condition Management --------------------
    
    def get_user_conditions(self, user_id: int) -> List[UserCondition]:
        """Get all conditions assigned to a user"""
        return (
            self.db.query(UserCondition)
            .filter(UserCondition.user_id == user_id)
            .all()
        )
    
    def assign_condition_to_user(
        self,
        user_id: int,
        condition_id: int,
        diagnosed_date: Optional[datetime] = None,
        severity: Optional[str] = None,
        notes: Optional[str] = None
    ) -> UserCondition:
        """Assign a medical condition to a user"""
        # Check if already assigned
        existing = (
            self.db.query(UserCondition)
            .filter(
                UserCondition.user_id == user_id,
                UserCondition.condition_id == condition_id
            )
            .first()
        )
        
        if existing:
            # Update existing assignment
            if diagnosed_date:
                existing.diagnosed_date = diagnosed_date
            if severity:
                existing.severity = severity
            if notes:
                existing.notes = notes
            self.db.commit()
            self.db.refresh(existing)
            return existing
        
        # Create new assignment
        user_condition = UserCondition(
            user_id=user_id,
            condition_id=condition_id,
            diagnosed_date=diagnosed_date,
            severity=severity,
            notes=notes,
            embedding_id=None  # TODO: RAG integration - generate embedding when RAG is enabled
        )
        self.db.add(user_condition)
        self.db.commit()
        self.db.refresh(user_condition)
        return user_condition
    
    def remove_user_condition(self, user_id: int, condition_id: int) -> bool:
        """Remove a condition assignment from a user"""
        user_condition = (
            self.db.query(UserCondition)
            .filter(
                UserCondition.user_id == user_id,
                UserCondition.condition_id == condition_id
            )
            .first()
        )
        
        if user_condition:
            self.db.delete(user_condition)
            self.db.commit()
            return True
        return False
    
    # -------------------- Condition Detection (Simple Rule-Based) --------------------
    
    def detect_conditions_from_health_data(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Detect potential medical conditions from user's health data.
        
        This is a simple rule-based detection (Plan B).
        TODO: RAG integration - enhance with semantic search when RAG is enabled.
        
        Returns list of detected condition suggestions with confidence scores.
        """
        # Get recent health data
        recent_health = (
            self.db.query(HealthData)
            .filter(HealthData.user_id == user_id)
            .order_by(HealthData.created_at.desc())
            .limit(10)
            .all()
        )
        
        if not recent_health:
            return []
        
        detected = []
        
        # Simple rule-based detection (can be enhanced with RAG later)
        avg_heart_rate = self._calculate_avg_heart_rate(recent_health)
        avg_temperature = self._calculate_avg_temperature(recent_health)
        avg_spo2 = self._calculate_avg_spo2(recent_health)
        
        # Rule: High heart rate consistently
        if avg_heart_rate and avg_heart_rate > 100:
            detected.append({
                "condition_name": "Tachycardia",
                "confidence": 0.6,
                "reason": f"Average heart rate is {avg_heart_rate} bpm (normal: 60-100)"
            })
        
        # Rule: Low SpO2
        if avg_spo2 and avg_spo2 < 95:
            detected.append({
                "condition_name": "Hypoxemia",
                "confidence": 0.7,
                "reason": f"Average SpO2 is {avg_spo2}% (normal: 95-100%)"
            })
        
        # Rule: Elevated temperature
        if avg_temperature and avg_temperature > 37.5:
            detected.append({
                "condition_name": "Fever",
                "confidence": 0.8,
                "reason": f"Average temperature is {avg_temperature}°C (normal: 36.5-37.5°C)"
            })
        
        # TODO: RAG integration - use semantic search to find similar conditions
        # from medical knowledge base when RAG is enabled
        
        return detected
    
    def _calculate_avg_heart_rate(self, health_records: List[HealthData]) -> Optional[float]:
        """Calculate average heart rate from health records"""
        values = []
        for record in health_records:
            if record.heart_rate:
                try:
                    values.append(float(record.heart_rate))
                except (ValueError, TypeError):
                    pass
        return sum(values) / len(values) if values else None
    
    def _calculate_avg_temperature(self, health_records: List[HealthData]) -> Optional[float]:
        """Calculate average temperature from health records"""
        values = []
        for record in health_records:
            if record.temperature:
                try:
                    values.append(float(record.temperature))
                except (ValueError, TypeError):
                    pass
        return sum(values) / len(values) if values else None
    
    def _calculate_avg_spo2(self, health_records: List[HealthData]) -> Optional[float]:
        """Calculate average SpO2 from health records"""
        values = []
        for record in health_records:
            if record.spo2:
                try:
                    values.append(float(record.spo2))
                except (ValueError, TypeError):
                    pass
        return sum(values) / len(values) if values else None
    
    # -------------------- Medication Lookup --------------------
    
    def get_all_medications(self) -> List[Medication]:
        """Get all available medications"""
        return self.db.query(Medication).all()
    
    def get_medication_by_id(self, medication_id: int) -> Optional[Medication]:
        """Get a medication by ID"""
        return self.db.query(Medication).filter(Medication.id == medication_id).first()
    
    def search_medications(self, query: str) -> List[Medication]:
        """Search medications by name (simple text search)"""
        # TODO: RAG integration - use semantic search when RAG is enabled
        return (
            self.db.query(Medication)
            .filter(
                Medication.name.ilike(f"%{query}%") |
                Medication.generic_name.ilike(f"%{query}%")
            )
            .all()
        )
