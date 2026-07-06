# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, Time, Date, ForeignKey, Boolean, Float, Text, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
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
    # Gate 1: normal app user vs dependent managed by caregivers
    account_type = Column(String(16), nullable=False, default="normal", server_default="normal")


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
    # Gate 4-B: traceability (nullable; soft source refs; no polymorphic FK)
    category = Column(String(64), nullable=True)
    source_type = Column(String(64), nullable=True)
    source_id = Column(String(255), nullable=True)
    context_json = Column(Text, nullable=True)
    risk_level = Column(String(16), nullable=True)
    template_key = Column(String(100), nullable=True)


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


# -------------------- InteractionEvent (Gate 4C) --------------------
class InteractionEvent(Base):
    """Unified interaction timeline: chat, notification actions, future voice/call/video."""
    __tablename__ = "interaction_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    source = Column(String(32), nullable=False)
    interaction_channel = Column(String(20), nullable=False, default="text", server_default="text")
    source_notification_id = Column(
        Integer, ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_type = Column(String(64), nullable=True)
    source_id = Column(String(255), nullable=True)
    conversation_id = Column(String(128), nullable=True, index=True)
    thread_id = Column(String(128), nullable=True, index=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


# -------------------- NotificationGuardState (D2.0 Behavior Guard) --------------------
class NotificationGuardState(Base):
    __tablename__ = "notification_guard_state"
    __table_args__ = (UniqueConstraint("user_id", "channel", "rule_id", name="uq_notification_guard_state_user_channel_rule"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)
    rule_id = Column(String(100), nullable=False)
    last_sent_at = Column(DateTime, nullable=False)
    cooldown_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)


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
    """User medication assignment with personal dosage, reminders, and schedule."""
    __tablename__ = "user_medications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    medication_id = Column(Integer, ForeignKey("medications.id", ondelete="CASCADE"), nullable=False)
    interval_hours = Column(Integer, nullable=False, default=8)  # Legacy fallback when no schedule rows
    user_dosage = Column(String(128), nullable=True)
    instructions = Column(Text, nullable=True)
    reminder_enabled = Column(Boolean, nullable=False, default=True)
    timezone = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    schedules = relationship(
        "UserMedicationSchedule",
        back_populates="user_medication",
        cascade="all, delete-orphan",
    )
    medication = relationship("Medication")


class UserMedicationSchedule(Base):
    """Daily intake time for a user medication assignment."""
    __tablename__ = "user_medication_schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_medication_id = Column(
        Integer,
        ForeignKey("user_medications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    time_of_day = Column(Time, nullable=False)
    days_of_week = Column(String(32), nullable=True)  # e.g. "0,1,2,3,4,5,6" (Mon=0); null = daily
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user_medication = relationship("UserMedication", back_populates="schedules")


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
    subject_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    device_id = Column(String(255), nullable=False, unique=True)  # logical device id (e.g. "Sedi001")
    device_type = Column(String(50), nullable=False, default="heart_rate")
    status = Column(String(20), nullable=False, default="active")  # active | revoked
    token_hash = Column(String(255), nullable=False)  # sha256 hex digest; never store raw token
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    # Gate 5-A: Gadget Hub operational metadata (nullable for legacy devices)
    battery_level = Column(Float, nullable=True)
    firmware_version = Column(String(64), nullable=True)
    hardware_version = Column(String(64), nullable=True)
    hub_status = Column(String(32), nullable=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)

    sensors = relationship(
        "DeviceSensor",
        back_populates="hub_device",
        cascade="all, delete-orphan",
        foreign_keys="DeviceSensor.hub_device_id",
    )


# -------------------- DeviceSensor (Gate 5-A) --------------------
class DeviceSensor(Base):
    """Sensor registry reported by a Gadget Hub (Bluetooth peripherals)."""
    __tablename__ = "device_sensors"
    __table_args__ = (
        UniqueConstraint("hub_device_id", "sensor_key", name="uq_device_sensors_hub_sensor_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hub_device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    sensor_key = Column(String(255), nullable=False, index=True)
    sensor_type = Column(String(64), nullable=False, default="unknown", server_default="unknown")
    display_name = Column(String(255), nullable=True)
    connection_status = Column(String(32), nullable=False, default="unknown", server_default="unknown")
    capabilities_json = Column(Text, nullable=True)
    battery_level = Column(Float, nullable=True)
    firmware_version = Column(String(64), nullable=True)
    hardware_version = Column(String(64), nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    last_signal_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    hub_device = relationship("Device", back_populates="sensors", foreign_keys=[hub_device_id])


# -------------------- RawSignalBatch (Gate 5-B) --------------------
class RawSignalBatch(Base):
    """Append-only raw heart/ECG signal batches from Gadget Hub sensors. Store-only; no interpretation."""
    __tablename__ = "raw_signal_batches"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_raw_signal_batches_dedupe_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hub_device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    hub_device_id_str = Column(String(255), nullable=False)
    sensor_id = Column(Integer, ForeignKey("device_sensors.id", ondelete="RESTRICT"), nullable=False, index=True)
    sensor_key = Column(String(255), nullable=False, index=True)
    signal_type = Column(String(32), nullable=False)
    sample_rate_hz = Column(Float, nullable=False)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)
    sample_count = Column(Integer, nullable=False)
    samples_json = Column(JSON, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    quality_metadata_json = Column(JSON, nullable=True)
    client_batch_id = Column(String(128), nullable=False)
    dedupe_key = Column(String(255), nullable=False, unique=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    storage_backend = Column(String(16), nullable=False, default="postgres_json", server_default="postgres_json")
    object_storage_key = Column(String(512), nullable=True)


# -------------------- RawSignalBatchFeature (Gate 5-C) --------------------
class RawSignalBatchFeature(Base):
    """Technical (non-diagnostic) features extracted from a raw signal batch."""

    __tablename__ = "raw_signal_batch_features"
    __table_args__ = (
        UniqueConstraint(
            "raw_signal_batch_id",
            "processing_version",
            name="uq_raw_signal_batch_features_batch_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    raw_signal_batch_id = Column(
        Integer,
        ForeignKey("raw_signal_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    hub_device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    sensor_id = Column(Integer, ForeignKey("device_sensors.id", ondelete="RESTRICT"), nullable=False, index=True)
    signal_type = Column(String(32), nullable=False)
    processing_version = Column(String(32), nullable=False)
    processing_status = Column(String(16), nullable=False)
    features_json = Column(JSON, nullable=True)
    quality_json = Column(JSON, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- MlModelRegistry (Gate 5-E) --------------------
class MlModelRegistry(Base):
    """Internal ML model registry — research/shadow only by default."""

    __tablename__ = "ml_model_registry"
    __table_args__ = (
        UniqueConstraint("model_name", "model_version", name="uq_ml_model_registry_name_version"),
    )

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(128), nullable=False)
    model_version = Column(String(64), nullable=False)
    signal_family = Column(String(64), nullable=False)
    input_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="research", server_default="research")
    training_dataset = Column(String(255), nullable=True)
    metrics_json = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- MlInferenceRecord (Gate 5-E) --------------------
class MlInferenceRecord(Base):
    """Shadow/internal ML inference output — not user-facing by default."""

    __tablename__ = "ml_inference_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(255), nullable=True)
    sensor_id = Column(Integer, ForeignKey("device_sensors.id", ondelete="SET NULL"), nullable=True)
    raw_signal_batch_id = Column(Integer, ForeignKey("raw_signal_batches.id", ondelete="SET NULL"), nullable=True)
    raw_signal_batch_feature_id = Column(
        Integer,
        ForeignKey("raw_signal_batch_features.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_id = Column(Integer, ForeignKey("ml_model_registry.id", ondelete="RESTRICT"), nullable=False, index=True)
    output_type = Column(String(64), nullable=False, index=True)
    score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    features_summary_json = Column(JSON, nullable=True)
    raw_output_json = Column(JSON, nullable=True)
    safety_status = Column(String(32), nullable=False, default="shadow_only", server_default="shadow_only")
    user_visible = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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


# -------------------- UserProfileCore (Knowledge Capture V1) --------------------
class UserProfileCore(Base):
    """1 row per user: health + lifestyle profile (birth_year, sex, height, weight, quiet window)."""
    __tablename__ = "user_profile_core"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    birth_year = Column(Integer, nullable=True)
    birth_day = Column(Integer, nullable=True)
    birth_month = Column(Integer, nullable=True)
    calendar_type = Column(String(16), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    sex = Column(String(32), nullable=True)
    addressing_preference = Column(String(64), nullable=True)
    timezone = Column(String(64), nullable=True)
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    language = Column(String(32), nullable=True)
    quiet_start = Column(Time, nullable=True)
    quiet_end = Column(Time, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- KcFactCandidate (Knowledge Capture V1) --------------------
class KcFactCandidate(Base):
    """Candidate facts (chat/form/import) awaiting verification."""
    __tablename__ = "kc_fact_candidates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(64), nullable=False)  # chat, form, import, chat_extraction_v1
    fact_type = Column(String(128), nullable=False)
    value_json = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    evidence = Column(Text, nullable=True)
    status = Column(String(32), nullable=False)  # pending, accepted, rejected
    metadata_json = Column(Text, nullable=True)  # {"needs_confirmation": true, "source_message_id": "..."}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- KcUserFact (Knowledge Capture V1) --------------------
class KcUserFact(Base):
    """Verified facts with validity window. Multiple rows per (user_id, fact_type) allowed."""
    __tablename__ = "kc_user_facts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fact_type = Column(String(128), nullable=False, index=True)
    value_json = Column(Text, nullable=False)
    verified_by = Column(String(32), nullable=False)  # user, system, clinician
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- KcQuestionPolicyState (Knowledge Capture – Question Fatigue V1) --------------------
class KcQuestionPolicyState(Base):
    """Per-user fatigue state: daily cap, cooldown, burst guard, reject streak."""
    __tablename__ = "kc_question_policy_state"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    day = Column(Date, nullable=False)  # current day marker (UTC)
    asked_count = Column(Integer, nullable=False, default=0)
    last_asked_at = Column(DateTime, nullable=True)
    last_question_type = Column(Text, nullable=True)  # e.g. confirm_candidate, profile_question
    consecutive_rejects = Column(Integer, nullable=False, default=0)
    cooldown_until = Column(DateTime, nullable=True)

    # Optional: no created_at/updated_at in spec; we can add if needed for debugging


# -------------------- UserBehaviorProfile (Behavior Layer V1) --------------------
class UserBehaviorProfile(Base):
    """Per-user behavior state: score, mode, daily initiated count, last initiated/interaction. Tiny table."""
    __tablename__ = "user_behavior_profiles"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    score = Column(Float, nullable=False, default=0.5)  # 0.0–1.0 for mode mapping
    mode = Column(String(32), nullable=False, default="normal")  # low | normal | high
    daily_initiated_count = Column(Integer, nullable=False, default=0)
    last_initiated_at = Column(DateTime, nullable=True)
    last_interaction_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- NotificationPrefs (V1 – Inbox preferences) --------------------
class NotificationPrefs(Base):
    """One row per user: notification channel toggles, quiet hours, engagement level."""
    __tablename__ = "notification_prefs"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    companion_enabled = Column(Boolean, nullable=False, default=True)
    health_alert_enabled = Column(Boolean, nullable=False, default=True)
    reminder_medication_enabled = Column(Boolean, nullable=False, default=True)
    reminder_appointment_enabled = Column(Boolean, nullable=False, default=True)
    reminder_system_enabled = Column(Boolean, nullable=False, default=True)
    quiet_hours_enabled = Column(Boolean, nullable=False, default=False)
    quiet_start = Column(String(5), nullable=True)   # HH:MM
    quiet_end = Column(String(5), nullable=True)   # HH:MM
    daily_notification_time = Column(String(5), nullable=True)  # HH:MM; Gate 4D canonical daily time
    engagement_level = Column(Integer, nullable=False, default=1)  # 0=low, 1=normal, 2=high
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)


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


# -------------------- UserProfileFact (Gate 1) --------------------
class UserProfileFact(Base):
    """Structured identity/profile facts (allergy, occupation, living situation, etc.)."""
    __tablename__ = "user_profile_facts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fact_type = Column(String(64), nullable=False, index=True)
    value_json = Column(Text, nullable=False)
    source = Column(String(32), nullable=False, default="manual")
    confidence = Column(Float, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- UserCaregiver (Gate 1 contact registry) --------------------
class UserCaregiver(Base):
    """Caregiver/relative contact registered by the main user (not necessarily a Sedi account)."""
    __tablename__ = "user_caregivers"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    phone = Column(String(32), nullable=True)
    relationship = Column(String(64), nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    notify_daily_status = Column(Boolean, nullable=False, default=False)
    notify_emergency = Column(Boolean, nullable=False, default=True)
    notify_care_summary = Column(Boolean, nullable=False, default=False)
    can_manage_profile = Column(Boolean, nullable=False, default=False)
    preferred_language = Column(String(16), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- UserCareRelationship (Gate 1 caregiver ↔ dependent) --------------------
class UserCareRelationship(Base):
    """Links a caregiver Sedi user to a dependent user they may manage."""
    __tablename__ = "user_care_relationships"
    __table_args__ = (
        UniqueConstraint(
            "caregiver_user_id",
            "dependent_user_id",
            name="uq_user_care_relationships_caregiver_dependent",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    caregiver_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    dependent_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship = Column(String(64), nullable=True)
    permissions_json = Column(Text, nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- Gate 2: Lifestyle Memory & Unified User Data --------------------


class UserHabit(Base):
    __tablename__ = "user_habits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    frequency = Column(String(64), nullable=True)
    target_json = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active", server_default="active")
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    notes = Column(Text, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserGoal(Base):
    __tablename__ = "user_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(32), nullable=False, default="lifestyle", server_default="lifestyle")
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    target_json = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active", server_default="active")
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    priority = Column(String(16), nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserRestriction(Base):
    __tablename__ = "user_restrictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    restriction_type = Column(String(32), nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(16), nullable=True)
    status = Column(String(32), nullable=False, default="active", server_default="active")
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserDoctor(Base):
    __tablename__ = "user_doctors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    specialty = Column(String(128), nullable=True)
    phone = Column(String(32), nullable=True)
    clinic = Column(String(256), nullable=True)
    notes = Column(Text, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserEvent(Base):
    __tablename__ = "user_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("user_doctors.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    event_domain = Column(String(32), nullable=False, default="other", server_default="other")
    event_type = Column(String(64), nullable=False, default="other", server_default="other")
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)
    timezone = Column(String(64), nullable=True)
    location = Column(String(256), nullable=True)
    status = Column(String(32), nullable=False, default="scheduled", server_default="scheduled")
    importance = Column(String(16), nullable=False, default="normal", server_default="normal")
    reminder_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    reminder_offsets_json = Column(Text, nullable=True)
    recurrence_rule = Column(Text, nullable=True)
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    notes = Column(Text, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserLifestyleEvent(Base):
    __tablename__ = "user_lifestyle_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)
    value_json = Column(Text, nullable=True)
    occurred_at = Column(DateTime, nullable=False)
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserCarePlanItem(Base):
    __tablename__ = "user_care_plan_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="active", server_default="active")
    scheduled_at = Column(DateTime, nullable=True)
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    notes = Column(Text, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# -------------------- Gate 3: Health Care System / Intelligence --------------------


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(128), nullable=False, unique=True)
    name = Column(String(256), nullable=False)
    category = Column(String(64), nullable=False, default="other", server_default="other")
    trust_level = Column(String(32), nullable=False, default="editorial", server_default="editorial")
    source_url = Column(String(512), nullable=True)
    locale = Column(String(16), nullable=False, default="fa", server_default="fa")
    last_checked_at = Column(DateTime, nullable=True)
    freshness_policy_days = Column(Integer, nullable=False, default=180, server_default="180")
    ingestion_status = Column(String(32), nullable=False, default="draft", server_default="draft")
    license_notes = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    source_fetch_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    allowed_domain = Column(String(256), nullable=True)
    allowed_url_patterns_json = Column(Text, nullable=True)
    fetch_method = Column(String(32), nullable=False, default="manual_upload", server_default="manual_upload")
    review_required = Column(Boolean, nullable=False, default=True, server_default="true")
    auto_approve_low_risk = Column(Boolean, nullable=False, default=False, server_default="false")
    last_fetched_at = Column(DateTime, nullable=True)
    last_changed_at = Column(DateTime, nullable=True)
    last_approved_at = Column(DateTime, nullable=True)
    content_hash = Column(String(64), nullable=True)
    crawl_policy_json = Column(Text, nullable=True)
    max_fetch_bytes = Column(Integer, nullable=True, default=2097152)
    fetch_interval_hours = Column(Integer, nullable=True)
    robots_checked_at = Column(DateTime, nullable=True)
    robots_allowed = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    summary = Column(Text, nullable=True)
    category = Column(String(64), nullable=False, default="other", server_default="other")
    locale = Column(String(16), nullable=False, default="fa", server_default="fa")
    region = Column(String(128), nullable=True)
    city = Column(String(128), nullable=True)
    specialty = Column(String(128), nullable=True)
    tags_json = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="draft", server_default="draft")
    published_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, default=0, server_default="0")
    content = Column(Text, nullable=False)
    citation_label = Column(String(256), nullable=False)
    embedding_ref = Column(String(128), nullable=True)
    token_count = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class KnowledgeIngestionRun(Base):
    __tablename__ = "knowledge_ingestion_runs"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(32), nullable=False, default="running", server_default="running")
    chunks_created = Column(Integer, nullable=False, default=0, server_default="0")
    chunks_updated = Column(Integer, nullable=False, default=0, server_default="0")
    error_message = Column(Text, nullable=True)
    run_by = Column(String(64), nullable=True)
    run_type = Column(String(32), nullable=False, default="manual_upload", server_default="manual_upload")
    fetch_url = Column(String(512), nullable=True)
    fetched_content_hash = Column(String(64), nullable=True)
    previous_content_hash = Column(String(64), nullable=True)
    review_status = Column(String(32), nullable=False, default="pending_review", server_default="pending_review")
    fetched_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String(64), nullable=True)
    rejected_reason = Column(Text, nullable=True)
    parser_type = Column(String(32), nullable=True)
    source_snapshot_json = Column(Text, nullable=True)
    extracted_text_preview = Column(Text, nullable=True)
    ai_review_status = Column(String(32), nullable=True)
    review_findings_json = Column(Text, nullable=True)
    source_quality_score = Column(Float, nullable=True)
    parse_quality_score = Column(Float, nullable=True)
    evidence_quality_score = Column(Float, nullable=True)
    medical_risk_level = Column(String(16), nullable=True)
    psychological_risk_level = Column(String(16), nullable=True)
    advertising_risk_level = Column(String(16), nullable=True)
    recommended_action = Column(String(32), nullable=True)
    requires_human_review = Column(Boolean, nullable=True, default=False, server_default="false")
    auto_approve_allowed = Column(Boolean, nullable=True, default=False, server_default="false")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)


class CareRiskAssessment(Base):
    __tablename__ = "care_risk_assessments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_level = Column(String(16), nullable=False)
    reasons_json = Column(Text, nullable=True)
    message_hash = Column(String(64), nullable=True)
    source = Column(String(32), nullable=False, default="api", server_default="api")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CareRecommendation(Base):
    __tablename__ = "care_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(64), nullable=False, default="general", server_default="general")
    title = Column(String(256), nullable=False)
    body = Column(Text, nullable=False)
    safety_level = Column(String(16), nullable=False, default="low", server_default="low")
    status = Column(String(32), nullable=False, default="active", server_default="active")
    source_refs_json = Column(Text, nullable=True)
    source = Column(String(32), nullable=False, default="system", server_default="system")
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class CareFollowUpTask(Base):
    __tablename__ = "care_follow_up_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="open", server_default="open")
    due_at = Column(DateTime, nullable=True)
    linked_recommendation_id = Column(Integer, ForeignKey("care_recommendations.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class HealthQuestion(Base):
    __tablename__ = "health_questions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=True)
    safety_level = Column(String(16), nullable=False, default="low", server_default="low")
    risk_level = Column(String(16), nullable=False, default="low", server_default="low")
    citations_json = Column(Text, nullable=True)
    source = Column(String(32), nullable=False, default="api", server_default="api")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class HealthSymptomReport(Base):
    __tablename__ = "health_symptom_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reported_at = Column(DateTime, nullable=False)
    symptom_label = Column(String(256), nullable=False)
    symptom_code = Column(String(64), nullable=True)
    severity = Column(String(16), nullable=False, default="unknown", server_default="unknown")
    body_area = Column(String(64), nullable=True)
    duration = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    source = Column(String(32), nullable=False, default="manual", server_default="manual")
    status = Column(String(32), nullable=False, default="active", server_default="active")
    resolved_at = Column(DateTime, nullable=True)
    linked_question_id = Column(Integer, ForeignKey("health_questions.id", ondelete="SET NULL"), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
