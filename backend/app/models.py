# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, Text, UniqueConstraint
from datetime import datetime
from backend.app.database import Base


# -------------------- User --------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True, unique=False)  # User name (NOT unique - multiple users can have same name)
    secret_key = Column(String, nullable=False, unique=False)      # رمز شخصی (NOT unique - multiple users can have same password)
    preferred_language = Column(String, default="en", nullable=False, server_default="en")  # زبان انتخابی کاربر (NOT nullable - always has default)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # زمان ثبت‌نام (NOT nullable - always has default)
    # Stage 25: OTP auth – unique per user (nullable for legacy users)
    phone = Column(String(32), nullable=True, unique=True, index=True)


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
    type = Column(String, nullable=False)  # e.g. HEALTH, REMINDER, INSIGHT, morning_brief, connection_ping, health_alert
    title = Column(String, nullable=True)
    body = Column(String, nullable=False)  # Notification body/message content
    priority = Column(String, nullable=False, default="normal")  # low | normal | high | critical
    is_read = Column(Boolean, default=False, nullable=False)
    is_sent = Column(Boolean, default=False, nullable=False)  # Track if notification has been sent (for scheduler integration)
    sent_at = Column(DateTime, nullable=True)  # When notification was delivered (set by delivery pipeline)
    scheduled_for = Column(DateTime, nullable=True)  # For scheduler integration - when notification should be sent
    dedupe_key = Column(String(255), nullable=True)  # Release B: Deterministic deduplication key (indexes created via migration)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Stage 16.6 push (additive; nullable for backward compat)
    channel = Column(String(50), nullable=True)  # morning | engagement | health_alert
    language = Column(String(20), nullable=True)
    actions_json = Column(Text, nullable=True)  # [{"id":"like","type":"LIKE"}, ...]
    deeplink_url = Column(String(512), nullable=True)  # sedi://chat?from=notif&id=123
    provider = Column(String(50), nullable=True)  # fcm
    provider_message_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=True)  # queued | sent | failed | delivered
    last_error = Column(Text, nullable=True)
    ttl_seconds = Column(Integer, nullable=True)


# -------------------- PushDevice (Stage 16.6) --------------------
class PushDevice(Base):
    __tablename__ = "push_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(20), nullable=False)  # android
    fcm_token = Column(String(512), nullable=False, unique=True)
    device_id = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- NotificationFeedback (Stage 16.6) --------------------
class NotificationFeedback(Base):
    __tablename__ = "notification_feedback"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # like | dislike | open_chat | dismissed
    meta_json = Column(Text, nullable=True)
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


# -------------------- UserMedication --------------------
class UserMedication(Base):
    """User's medications for scheduled reminder loop (e.g. every 8h)."""
    __tablename__ = "user_medications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    medication_id = Column(Integer, ForeignKey("medications.id", ondelete="CASCADE"), nullable=False)
    interval_hours = Column(Integer, nullable=False, default=8)  # Reminder every N hours
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


# -------------------- DeviceEvent --------------------
class DeviceEvent(Base):
    __tablename__ = "device_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(255), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)  # e.g., "heart_rate"
    payload_json = Column(Text, nullable=False)  # Raw JSON string from device
    recorded_at = Column(DateTime, nullable=True)  # Timestamp from device
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # Server timestamp
    dedupe_key = Column(String(255), nullable=True)  # Deduplication key
    embedding_id = Column(String(255), nullable=True)  # For RAG integration - vector embedding ID


# -------------------- Device --------------------
class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(255), nullable=False, unique=True)  # logical device id (e.g. "Sedi001")
    device_type = Column(String(50), nullable=False, default="heart_rate")
    status = Column(String(20), nullable=False, default="active")  # active | revoked
    token_hash = Column(String(255), nullable=False)  # sha256 hex digest; never store raw token
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)


# -------------------- UserProfileKnowledge --------------------
class UserProfileKnowledge(Base):
    """Stable user baseline: 1 row per user. Used for GPT context."""
    __tablename__ = "user_profile_knowledge"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=True)
    language = Column(String(20), nullable=True)
    baseline_summary = Column(Text, nullable=True)
    goals_json = Column(Text, nullable=True)  # JSON string
    constraints_json = Column(Text, nullable=True)
    preferences_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- UserFactCandidate (Stage 17.1) --------------------
class UserFactCandidate(Base):
    """Candidate facts from chat; pending/accepted/rejected."""
    __tablename__ = "user_fact_candidates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    domain = Column(String(50), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    value_json = Column(Text, nullable=False)
    source_memory_id = Column(Integer, ForeignKey("memory.id", ondelete="SET NULL"), nullable=True)
    confidence = Column(Float, default=0.5, nullable=False)
    is_explicit = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- UserFact --------------------
class UserFact(Base):
    """Key-value facts per user (chat/manual/device). Used for GPT context."""
    __tablename__ = "user_facts"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_facts_user_id_key"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(255), nullable=False, index=True)
    value_json = Column(Text, nullable=True)
    source = Column(String(50), nullable=False, default="manual")  # "chat" | "manual" | "device"
    confidence = Column(Float, default=0.7, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- OtpCode (Stage 25 – Phone OTP) --------------------
class OtpCode(Base):
    """Single active OTP per phone; hashed code, expiry, attempt limit."""
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(32), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    sent_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- RefreshToken (Stage 25 – Persistent refresh tokens) --------------------
class RefreshToken(Base):
    """Refresh token stored hashed; revocable."""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    device_info = Column(String(512), nullable=True)
    ip = Column(String(64), nullable=True)
