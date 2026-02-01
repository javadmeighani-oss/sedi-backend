# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, Text
from datetime import datetime
from app.database import Base


# -------------------- User --------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True, unique=False)  # User name (NOT unique - multiple users can have same name)
    secret_key = Column(String, nullable=False, unique=False)      # رمز شخصی (NOT unique - multiple users can have same password)
    preferred_language = Column(String, default="en", nullable=False, server_default="en")  # زبان انتخابی کاربر (NOT nullable - always has default)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # زمان ثبت‌نام (NOT nullable - always has default)


# -------------------- Memory --------------------
class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_message = Column(String, nullable=False)
    sedi_response = Column(String, nullable=True)
    language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.utcnow)


# -------------------- HealthData --------------------
class HealthData(Base):
    __tablename__ = "health_data"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # CASCADE delete when user deleted
    heart_rate = Column(String, nullable=True)
    temperature = Column(String, nullable=True)
    spo2 = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


# -------------------- Notification --------------------
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # CASCADE delete when user deleted, indexed for queries
    type = Column(String, nullable=False)  # e.g. HEALTH, REMINDER, INSIGHT
    title = Column(String, nullable=True)
    body = Column(String, nullable=False)  # Notification body/message content
    priority = Column(String, nullable=False, default="normal")  # low | normal | high | critical
    is_read = Column(Boolean, default=False, nullable=False)
    is_sent = Column(Boolean, default=False, nullable=False)  # Track if notification has been sent (for scheduler integration)
    scheduled_for = Column(DateTime, nullable=True)  # For scheduler integration - when notification should be sent
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- MedicalCondition --------------------
class MedicalCondition(Base):
    __tablename__ = "medical_conditions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=True, unique=True)  # Unique code (e.g. "ALS", "MS", "DIABETES_T2") - for seed script lookup
    name = Column(String, nullable=False, unique=True)  # e.g. "Diabetes Type 2", "Hypertension"
    description = Column(String, nullable=True)  # Brief description of the condition (can store JSON for keywords, severity, chronic flag)
    category = Column(String, nullable=True)  # e.g. "chronic", "acute", "cardiovascular"
    embedding_id = Column(String, nullable=True)  # For RAG integration - vector embedding ID (nullable, optional)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- Medication --------------------
class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Medication name
    generic_name = Column(String, nullable=True)  # Generic name if available
    dosage_form = Column(String, nullable=True)  # e.g. "tablet", "capsule", "injection"
    default_dosage = Column(String, nullable=True)  # e.g. "500mg", "10ml" (can also store dosage_info here)
    condition_id = Column(Integer, ForeignKey("medical_conditions.id", ondelete="SET NULL"), nullable=True)  # Link to condition (optional)
    embedding_id = Column(String, nullable=True)  # For RAG integration - vector embedding ID (nullable, optional)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- UserCondition --------------------
class UserCondition(Base):
    __tablename__ = "user_conditions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    condition_id = Column(Integer, ForeignKey("medical_conditions.id", ondelete="CASCADE"), nullable=False)
    diagnosed_date = Column(DateTime, nullable=True)  # When condition was diagnosed
    severity = Column(String, nullable=True)  # e.g. "mild", "moderate", "severe"
    notes = Column(String, nullable=True)  # Additional notes about user's condition
    embedding_id = Column(String, nullable=True)  # For RAG integration - vector embedding ID (nullable, optional)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- DailyMemorySummary --------------------
class DailyMemorySummary(Base):
    __tablename__ = "daily_memory_summaries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    summary = Column(Text, nullable=False)  # Daily summary text
    mood = Column(String, nullable=True)  # User mood (e.g., "happy", "neutral", "tired")
    context = Column(Text, nullable=True)  # Additional context information
    last_interaction = Column(DateTime, nullable=True)  # Last interaction timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- UserMemoryFact --------------------
class UserMemoryFact(Base):
    __tablename__ = "user_memory_facts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    domain = Column(String, nullable=False, index=True)  # e.g., "lifestyle", "medical", "preferences"
    key = Column(String, nullable=False, index=True)  # e.g., "sleep_duration_hours", "hydration_ml"
    value_json = Column(Text, nullable=False)  # JSON string storing the value
    confidence = Column(Float, default=0.7, nullable=False)  # Confidence score (0.0 to 1.0)
    source = Column(String, nullable=False)  # Source: "chat" | "device" | "manual"
    last_seen_at = Column(DateTime, nullable=True)  # When this fact was last observed/updated
    embedding_id = Column(String, nullable=True)  # For RAG integration - vector embedding ID
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
