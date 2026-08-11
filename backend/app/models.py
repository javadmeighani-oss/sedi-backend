# app/models.py
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Time, Date, ForeignKey, Boolean, Float, Text, UniqueConstraint, ForeignKeyConstraint, CheckConstraint, JSON, Index, text, func, Identity
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.app.database import Base

# Section 15-I5-IMPL-W1-P01 — persisted-vocabulary enums (documentation/constants only;
# columns below still use plain String literals matching these enum values so that
# CheckConstraint SQL text stays self-contained and avoids any import-time circularity).
from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    ExpiryState,
    FreshnessState,
    GovernanceActorType,
    GovernanceDecisionFamily,
    GovernanceDecisionOutcome,
    GovernanceDecisionType,
    GovernanceEntityType,
    KnowledgeGapPriority,
    KnowledgeGapSeverity,
    KnowledgeGapStatus,
    KnowledgeGapType,
    KnowledgeGapUrgency,
    KnowledgeType,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    MemoryChangeKind,
    MemoryTransitionKind,
    ProhibitedDataState,
    PublicationState,
    RawRetentionMode,
    RawStorageMode,
    RedactionState,
    RegistryState,
    ReviewState,
    RightsTermsState,
    RobotsAccessState,
    RunGapResultType,
    RunSourceResultStatus,
    RuntimeEligibility,
    SafetyReviewQueueStatus,
    SupersessionState,
    WeeklyRunApprovalState,
    WeeklyRunAttemptStatus,
    WeeklyRunStatus,
    WeeklyRunTriggerType,
    WeeklyRunType,
)


def _vocab_sql(column: str, enum_cls) -> str:
    """Build a `column IN ('A', 'B', ...)` CheckConstraint SQL fragment from an enum.

    Keeps CheckConstraint literals in lock-step with the I5 enums (single source
    of truth) while still compiling to a plain string of persisted literals, with
    no SQLAlchemy Enum type and no enum class stored on the mapped Column itself.
    """

    literal_values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return f"{column} IN ({literal_values})"


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
    # DB-03 / §270.P: align ORM with Production ON DELETE CASCADE for chat turns.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
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
    # DB-03 / §270.F — Golden Window delivery fields + care episode linkage
    care_episode_id = Column(
        Integer,
        ForeignKey("care_episodes.id", ondelete="SET NULL", name="fk_notifications_care_episode_id"),
        nullable=True,
        index=True,
    )
    queued_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    decision_at = Column(DateTime(timezone=True), nullable=True)


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


# Partial unique predicate for notification chat_message idempotency (B8).
# Shared by PostgreSQL production index and SQLite test metadata (create_all).
_NOTIF_CHAT_ONCE_PARTIAL_IDX_WHERE = text(
    "event_type = 'chat_message' AND source_notification_id IS NOT NULL"
)


# -------------------- InteractionEvent (Gate 4C) --------------------
class InteractionEvent(Base):
    """Unified interaction timeline: chat, notification actions, future voice/call/video."""

    __tablename__ = "interaction_events"
    # One notification may seed only one chat_message consumption event for a user.
    # conversation_id is intentionally excluded: NULLs are distinct in PostgreSQL UNIQUE
    # and a changed/null→non-null conversation_id must not reopen consumption.
    __table_args__ = (
        Index(
            "uq_interaction_events_notif_chat_once",
            "user_id",
            "source_notification_id",
            unique=True,
            postgresql_where=_NOTIF_CHAT_ONCE_PARTIAL_IDX_WHERE,
            # Tests use Base.metadata.create_all; without sqlite_where SQLAlchemy would
            # compile an unconditional UNIQUE and block notification_ack/open_chat rows
            # that share the same source_notification_id.
            sqlite_where=_NOTIF_CHAT_ONCE_PARTIAL_IDX_WHERE,
        ),
    )

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
    remaining_quantity = Column(Float, nullable=True)
    quantity_unit = Column(String(32), nullable=True)
    refill_threshold = Column(Float, nullable=True)
    last_refill_at = Column(DateTime, nullable=True)
    estimated_end_at = Column(DateTime, nullable=True)
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
    """Canonical LTM fact authority (DB-02/DB-03). Competing stacks merge here."""

    __tablename__ = "user_memory_facts"
    __table_args__ = (
        CheckConstraint(
            "provenance_class IS NULL OR provenance_class IN ("
            "'USER_STATED', 'USER_CONFIRMED', 'CONVERSATION_DERIVED', 'DEVICE_DERIVED', "
            "'SYSTEM_DERIVED', 'CAREGIVER_PROVIDED', 'CLINICIAN_PROVIDED')",
            name="ck_umf_provenance_class_vocab",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    domain = Column(String, nullable=False, index=True)  # e.g., "lifestyle", "medical", "preferences"
    key = Column(String, nullable=False, index=True)  # e.g., "sleep_duration_hours", "hydration_ml"
    value_json = Column(Text, nullable=False)  # JSON string storing the value
    confidence = Column(Float, default=0.7, nullable=False)  # Confidence score (0.0 to 1.0)
    source = Column(String, nullable=False)  # Source: "chat" | "device" | "manual"
    last_seen_at = Column(DateTime, nullable=True)  # When this fact was last observed/updated
    embedding_id = Column(String, nullable=True)  # For RAG integration - vector embedding ID
    provenance = Column(String(64), nullable=True)
    source_interaction_id = Column(Integer, nullable=True)
    extracted_at = Column(DateTime, nullable=True)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    last_confirmed_at = Column(DateTime, nullable=True)
    supersedes_fact_id = Column(Integer, nullable=True)
    fact_status = Column(String(32), nullable=False, default="active", server_default="active")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    # DB-03 / §270.F canonical LTM extensions
    consent_id = Column(
        Integer,
        ForeignKey("user_consents.id", ondelete="SET NULL", name="fk_umf_consent_id"),
        nullable=True,
        index=True,
    )
    sensitivity_class = Column(String(32), nullable=True)
    human_readable_value = Column(Text, nullable=True)
    provenance_class = Column(String(32), nullable=True)
    soft_invalidated_at = Column(DateTime(timezone=True), nullable=True)
    invalidation_reason = Column(Text, nullable=True)


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
    notify_vital_alerts = Column(Boolean, nullable=False, default=False)
    emergency_priority = Column(Integer, nullable=True)
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


# -------------------- Section 10: Caregiver notification intents --------------------
class CaregiverNotificationIntent(Base):
    __tablename__ = "caregiver_notification_intents"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_caregiver_notification_intents_dedupe_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    caregiver_id = Column(Integer, ForeignKey("user_caregivers.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type = Column(String(64), nullable=False)
    source_entity_type = Column(String(64), nullable=True)
    source_entity_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="pending", server_default="pending")
    dedupe_key = Column(String(255), nullable=False)
    payload_metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)


# -------------------- Section 10: Emergency escalation --------------------
class EmergencyEscalationRecord(Base):
    __tablename__ = "emergency_escalation_records"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason_category = Column(String(64), nullable=False)
    policy_version = Column(String(32), nullable=False, default="v1", server_default="v1")
    current_state = Column(String(64), nullable=False, default="monitoring", server_default="monitoring")
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_user_interaction_at = Column(DateTime, nullable=True)
    last_notification_attempt_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_source = Column(String(64), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    # DB-03 / §270.F escalation ledger extensions
    care_episode_id = Column(
        Integer,
        ForeignKey("care_episodes.id", ondelete="CASCADE", name="fk_eer_care_episode_id"),
        nullable=True,
        index=True,
    )
    step_no = Column(Integer, nullable=True)
    from_recipient = Column(String(128), nullable=True)
    to_recipient = Column(String(128), nullable=True)
    consent_evidence_id = Column(
        Integer,
        ForeignKey("user_consents.id", ondelete="SET NULL", name="fk_eer_consent_evidence_id"),
        nullable=True,
        index=True,
    )
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)


# -------------------- Section 10: Voice call requests (provider-neutral) --------------------
class VoiceCallRequest(Base):
    __tablename__ = "voice_call_requests"

    id = Column(Integer, primary_key=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    caregiver_id = Column(Integer, ForeignKey("user_caregivers.id", ondelete="CASCADE"), nullable=False)
    escalation_id = Column(Integer, ForeignKey("emergency_escalation_records.id", ondelete="SET NULL"), nullable=True)
    template_key = Column(String(64), nullable=False)
    language = Column(String(8), nullable=False, default="fa", server_default="fa")
    status = Column(String(32), nullable=False, default="pending", server_default="pending")
    provider = Column(String(64), nullable=True)
    provider_reference = Column(String(128), nullable=True)
    requested_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# -------------------- Section 10 / SCIS-01: KB chunk embedding metadata --------------------
class KnowledgeChunkEmbedding(Base):
    """Canonical retrieval metadata authority (DB-02/SCIS-01). Index rebuildable; not SoT."""

    __tablename__ = "knowledge_chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "model_identifier", name="uq_kb_chunk_embeddings_chunk_model"),
        CheckConstraint(
            "backend_kind IS NULL OR backend_kind IN "
            "('JSON_INLINE', 'EXTERNAL_VECTOR_DEFERRED', 'PGVECTOR')",
            name="ck_kce_backend_kind_vocab",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(Integer, ForeignKey("knowledge_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    model_identifier = Column(String(128), nullable=False)
    vector_dimension = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)
    embedding_status = Column(String(32), nullable=False, default="pending", server_default="pending")
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    embedding_json = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    # DB-03 / §270.F retrieval lineage metadata
    knowledge_unit_id = Column(
        Integer,
        ForeignKey("knowledge_units.id", ondelete="SET NULL", name="fk_kce_knowledge_unit_id"),
        nullable=True,
        index=True,
    )
    immutable_version_id = Column(String(64), nullable=True)
    source_profile_id = Column(
        Integer,
        ForeignKey("governed_source_profiles.id", ondelete="SET NULL", name="fk_kce_source_profile_id"),
        nullable=True,
        index=True,
    )
    raw_evidence_id = Column(
        Integer,
        ForeignKey("i5_raw_evidence.id", ondelete="SET NULL", name="fk_kce_raw_evidence_id"),
        nullable=True,
        index=True,
    )
    index_generation = Column(Integer, nullable=False, default=1, server_default="1")
    backend_kind = Column(String(32), nullable=False, default="JSON_INLINE", server_default="JSON_INLINE")
    runtime_eligibility_snapshot = Column(Text, nullable=True)
    retracted_at = Column(DateTime(timezone=True), nullable=True)
    # SCIS-01 — pgvector + FTS (embedding_vector typed in DB as vector(1024); ORM opaque)
    embedding_provider = Column(String(64), nullable=True)
    embedding_model_version = Column(String(64), nullable=True)
    chunker_version = Column(String(64), nullable=True)
    chunk_version = Column(Integer, nullable=False, default=1, server_default="1")
    section_path = Column(Text, nullable=True)
    content_language = Column(String(16), nullable=True)
    search_document = Column(Text, nullable=True)
    # search_tsv / embedding_vector maintained via SQL in SCIS indexing pipeline


# -------------------- Section 15 I5-B2-P1: Governed source identity + immutable versions --------------------


class GovernedSourceProfile(Base):
    """Current governed source identity and current-version pointer (I5-B2-P1)."""

    __tablename__ = "governed_source_profiles"
    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_governed_source_profiles_canonical_key"),
        UniqueConstraint(
            "legacy_knowledge_source_id",
            name="uq_governed_source_profiles_legacy_knowledge_source_id",
        ),
        UniqueConstraint(
            "locator_kind",
            "normalized_locator",
            name="uq_governed_source_profiles_locator",
        ),
        CheckConstraint(
            "(locator_kind IS NULL AND normalized_locator IS NULL) OR "
            "(locator_kind IS NOT NULL AND normalized_locator IS NOT NULL)",
            name="ck_governed_source_profiles_locator_pair",
        ),
        ForeignKeyConstraint(
            ["id", "current_profile_version_id"],
            [
                "governed_source_profile_versions.profile_id",
                "governed_source_profile_versions.id",
            ],
            name="fk_gsp_current_version_same_profile",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        Index(
            "ix_governed_source_profiles_operational_status",
            "operational_status",
        ),
        CheckConstraint(_vocab_sql("registry_state", RegistryState), name="ck_gsp_registry_state_vocab"),
        CheckConstraint(_vocab_sql("runtime_eligibility", RuntimeEligibility), name="ck_gsp_runtime_eligibility_vocab"),
        CheckConstraint("block_reason IS NULL OR char_length(block_reason) <= 2000", name="ck_gsp_block_reason_length"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_gsp_effective_window_order",
        ),
        Index("ix_gsp_registry_state", "registry_state"),
        Index("ix_gsp_runtime_eligibility", "runtime_eligibility"),
        Index("ix_gsp_last_checked_at", "last_checked_at"),
        Index("ix_gsp_last_reviewed_at", "last_reviewed_at"),
        Index("ix_gsp_registry_runtime", "registry_state", "runtime_eligibility"),
    )

    id = Column(
        Integer,
        Identity(start=1),
        primary_key=True,
        autoincrement="ignore_fk",
        index=True,
    )
    canonical_key = Column(String(256), nullable=False)
    locator_kind = Column(String(64), nullable=True)
    normalized_locator = Column(String(1024), nullable=True)
    legacy_knowledge_source_id = Column(
        Integer,
        ForeignKey("knowledge_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_profile_version_id = Column(Integer, nullable=True)
    operational_status = Column(
        String(32),
        nullable=False,
        default="disabled",
        server_default="disabled",
    )
    row_version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )
    registry_state = Column(String(32), nullable=False, default="DISCOVERED", server_default="DISCOVERED")
    runtime_eligibility = Column(String(32), nullable=False, default="NOT_ELIGIBLE", server_default="NOT_ELIGIBLE")
    block_reason = Column(Text, nullable=True)
    owner_reference = Column(String(512), nullable=True)
    reviewer_reference = Column(String(512), nullable=True)
    approver_reference = Column(String(512), nullable=True)
    topic_coverage = Column(Text, nullable=True)
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    last_discovered_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_reviewed_at = Column(DateTime, nullable=True)
    canonicalization_version = Column(String(32), nullable=False, server_default="v1")


class GovernedSourceProfileVersion(Base):
    """Immutable governed source profile version snapshot (I5-B2-P1).

    Immutable through approved persistence service boundary.
    No DB trigger. Direct ORM/SQL mutation remains outside supported contract.
    """

    __tablename__ = "governed_source_profile_versions"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "version_seq",
            name="uq_gspv_profile_version_seq",
        ),
        UniqueConstraint(
            "profile_id",
            "snapshot_fingerprint",
            name="uq_gspv_profile_snapshot_fingerprint",
        ),
        UniqueConstraint(
            "profile_id",
            "id",
            name="uq_gspv_profile_id_id",
        ),
        CheckConstraint(
            "supersedes_version_id IS NULL OR supersedes_version_id <> id",
            name="ck_gspv_supersedes_not_self",
        ),
        ForeignKeyConstraint(
            ["profile_id", "supersedes_version_id"],
            [
                "governed_source_profile_versions.profile_id",
                "governed_source_profile_versions.id",
            ],
            name="fk_gspv_supersedes_same_profile",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id = Column(
        Integer,
        Identity(start=1),
        primary_key=True,
        autoincrement=True,
        index=True,
    )
    profile_id = Column(
        Integer,
        ForeignKey("governed_source_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_seq = Column(Integer, nullable=False)
    supersedes_version_id = Column(Integer, nullable=True)
    snapshot_schema_version = Column(String(64), nullable=False)
    snapshot_fingerprint = Column(String(64), nullable=False)
    effective_at = Column(DateTime, nullable=False)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )

    # Explicit governance-evidence columns (no authority JSON blob)
    publisher_authority_identity = Column(String(512), nullable=False)
    source_class = Column(String(64), nullable=False)
    authority_evidence_tier = Column(String(64), nullable=False)
    jurisdiction_scope = Column(String(32), nullable=False)
    jurisdiction_country_code = Column(String(16), nullable=True)
    jurisdiction_subdivision_code = Column(String(64), nullable=True)
    jurisdiction_organization_id = Column(String(128), nullable=True)
    primary_language = Column(String(16), nullable=False)
    specialty_domain = Column(String(128), nullable=False)
    license_status = Column(String(32), nullable=False)
    permitted_use_restriction = Column(String(512), nullable=False)
    storage_permission = Column(String(32), nullable=False)
    transformation_permission = Column(String(32), nullable=False)
    display_redistribution_permission = Column(String(32), nullable=False)
    automation_status = Column(String(32), nullable=False)
    verification_method = Column(String(64), nullable=False)
    freshness_policy_days = Column(Integer, nullable=False)
    freshness_status = Column(String(32), nullable=False)
    fetch_policy = Column(String(128), nullable=False)
    iran_first_applicable = Column(Boolean, nullable=False, default=False, server_default="false")
    policy_version_reference = Column(String(128), nullable=False)
    configuration_version_reference = Column(String(128), nullable=False)


# -------------------- Section 15 I5 W1-P01: Weekly governed knowledge continuity --------------------
class WeeklyKnowledgeRun(Base):
    __tablename__ = "weekly_knowledge_runs"
    __table_args__ = (
        UniqueConstraint("logical_run_key", name="uq_weekly_knowledge_runs_logical_run_key"),
        CheckConstraint(_vocab_sql("run_type", WeeklyRunType), name="ck_wkr_run_type_vocab"),
        CheckConstraint(_vocab_sql("trigger_type", WeeklyRunTriggerType), name="ck_wkr_trigger_type_vocab"),
        CheckConstraint(_vocab_sql("approval_state", WeeklyRunApprovalState), name="ck_wkr_approval_state_vocab"),
        CheckConstraint(_vocab_sql("status", WeeklyRunStatus), name="ck_wkr_status_vocab"),
        CheckConstraint("planned_window_end >= planned_window_start", name="ck_wkr_window_order"),
        CheckConstraint("supersedes_run_id IS NULL OR supersedes_run_id <> id", name="ck_wkr_supersedes_not_self"),
        ForeignKeyConstraint(["id", "successful_attempt_id"], ["weekly_knowledge_run_attempts.weekly_run_id", "weekly_knowledge_run_attempts.id"], name="fk_wkr_successful_attempt_same_run", ondelete="RESTRICT", use_alter=True, deferrable=True, initially="DEFERRED"),
        ForeignKeyConstraint(["id", "latest_attempt_id"], ["weekly_knowledge_run_attempts.weekly_run_id", "weekly_knowledge_run_attempts.id"], name="fk_wkr_latest_attempt_same_run", ondelete="RESTRICT", use_alter=True, deferrable=True, initially="DEFERRED"),
        Index("ix_wkr_status_window", "status", "planned_window_start"),
        Index("ix_wkr_schedule_window", "schedule_key", "planned_window_start"),
        Index("ix_wkr_approval_state", "approval_state"),
        Index("ix_wkr_successful_attempt_id", "successful_attempt_id"),
        Index("ix_wkr_latest_attempt_id", "latest_attempt_id"),
        Index("ix_wkr_supersedes_run_id", "supersedes_run_id"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    logical_run_key = Column(String(64), nullable=False)
    canonicalization_version = Column(String(32), nullable=False, default="v1", server_default="v1")
    hash_algorithm = Column(String(32), nullable=False, default="SHA-256", server_default="SHA-256")
    schedule_key = Column(String(128), nullable=False)
    run_type = Column(String(64), nullable=False, default="WEEKLY_GOVERNED", server_default="WEEKLY_GOVERNED")
    trigger_type = Column(String(64), nullable=False)
    planned_window_start = Column(DateTime, nullable=False)
    planned_window_end = Column(DateTime, nullable=False)
    approval_state = Column(String(32), nullable=False)
    source_scope_hash = Column(String(64), nullable=False)
    domain_scope_hash = Column(String(64), nullable=False)
    gap_scope_hash = Column(String(64), nullable=False)
    config_version = Column(String(64), nullable=False)
    config_hash = Column(String(64), nullable=False)
    source_scope = Column(Text, nullable=False)
    domain_scope = Column(Text, nullable=False)
    gap_scope = Column(Text, nullable=False)
    status = Column(String(32), nullable=False)
    successful_attempt_id = Column(Integer, nullable=True)
    latest_attempt_id = Column(Integer, nullable=True)
    created_by_reference = Column(String(512), nullable=True)
    approved_by_reference = Column(String(512), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    supersedes_run_id = Column(Integer, ForeignKey("weekly_knowledge_runs.id", ondelete="RESTRICT", name="fk_wkr_supersedes_run_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow, nullable=False)
    row_version = Column(Integer, nullable=False, default=1, server_default="1")


class WeeklyKnowledgeRunAttempt(Base):
    __tablename__ = "weekly_knowledge_run_attempts"
    __table_args__ = (
        UniqueConstraint("weekly_run_id", "attempt_number", name="uq_wkra_run_attempt"),
        UniqueConstraint("id", "weekly_run_id", name="uq_wkra_id_weekly_run_id"),
        CheckConstraint(_vocab_sql("status", WeeklyRunAttemptStatus), name="ck_wkra_status_vocab"),
        CheckConstraint("attempt_number > 0", name="ck_wkra_attempt_number_pos"),
        CheckConstraint("retry_of_attempt_id IS NULL OR retry_of_attempt_id <> id", name="ck_wkra_retry_not_self"),
        CheckConstraint("completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at", name="ck_wkra_completed_after_started"),
        CheckConstraint("failure_reason IS NULL OR char_length(failure_reason) <= 2000", name="ck_wkra_failure_reason_length"),
        CheckConstraint("block_reason IS NULL OR char_length(block_reason) <= 2000", name="ck_wkra_block_reason_length"),
        CheckConstraint("total_sources >= 0", name="ck_wkra_total_sources_nonnegative"),
        CheckConstraint("checked_sources >= 0", name="ck_wkra_checked_sources_nonnegative"),
        CheckConstraint("fetched_sources >= 0", name="ck_wkra_fetched_sources_nonnegative"),
        CheckConstraint("skipped_sources >= 0", name="ck_wkra_skipped_sources_nonnegative"),
        CheckConstraint("blocked_sources >= 0", name="ck_wkra_blocked_sources_nonnegative"),
        CheckConstraint("failed_sources >= 0", name="ck_wkra_failed_sources_nonnegative"),
        CheckConstraint("new_knowledge_count >= 0", name="ck_wkra_new_knowledge_count_nonnegative"),
        CheckConstraint("updated_knowledge_count >= 0", name="ck_wkra_updated_knowledge_count_nonnegative"),
        CheckConstraint("superseded_knowledge_count >= 0", name="ck_wkra_superseded_knowledge_count_nonnegative"),
        CheckConstraint("rejected_knowledge_count >= 0", name="ck_wkra_rejected_knowledge_count_nonnegative"),
        CheckConstraint("created_gap_count >= 0", name="ck_wkra_created_gap_count_nonnegative"),
        CheckConstraint("resolved_gap_count >= 0", name="ck_wkra_resolved_gap_count_nonnegative"),
        CheckConstraint("warning_count >= 0", name="ck_wkra_warning_count_nonnegative"),
        CheckConstraint("error_count >= 0", name="ck_wkra_error_count_nonnegative"),
        ForeignKeyConstraint(["retry_of_attempt_id", "weekly_run_id"], ["weekly_knowledge_run_attempts.id", "weekly_knowledge_run_attempts.weekly_run_id"], name="fk_wkra_retry_same_run", ondelete="RESTRICT"),
        Index("uq_wkra_one_successful_terminal", "weekly_run_id", unique=True, postgresql_where=text("status IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS')")),
        Index("ix_wkra_status_started_at", "status", "started_at"),
        Index("ix_wkra_retry_of_attempt_id", "retry_of_attempt_id"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    weekly_run_id = Column(Integer, ForeignKey("weekly_knowledge_runs.id", ondelete="RESTRICT", name="fk_wkra_weekly_run_id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    retry_of_attempt_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    worker_reference = Column(String(512), nullable=True)
    config_snapshot_reference = Column(String(2048), nullable=True)
    run_checksum = Column(String(64), nullable=True)
    canonicalization_version = Column(String(32), nullable=False, default="v1", server_default="v1")
    hash_algorithm = Column(String(32), nullable=False, default="SHA-256", server_default="SHA-256")
    total_sources = Column(Integer, nullable=False, default=0, server_default="0")
    checked_sources = Column(Integer, nullable=False, default=0, server_default="0")
    fetched_sources = Column(Integer, nullable=False, default=0, server_default="0")
    skipped_sources = Column(Integer, nullable=False, default=0, server_default="0")
    blocked_sources = Column(Integer, nullable=False, default=0, server_default="0")
    failed_sources = Column(Integer, nullable=False, default=0, server_default="0")
    new_knowledge_count = Column(Integer, nullable=False, default=0, server_default="0")
    updated_knowledge_count = Column(Integer, nullable=False, default=0, server_default="0")
    superseded_knowledge_count = Column(Integer, nullable=False, default=0, server_default="0")
    rejected_knowledge_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_gap_count = Column(Integer, nullable=False, default=0, server_default="0")
    resolved_gap_count = Column(Integer, nullable=False, default=0, server_default="0")
    warning_count = Column(Integer, nullable=False, default=0, server_default="0")
    error_count = Column(Integer, nullable=False, default=0, server_default="0")
    failure_code = Column(String(128), nullable=True)
    failure_reason = Column(Text, nullable=True)
    block_reason = Column(Text, nullable=True)
    evidence_reference = Column(String(2048), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow, nullable=False)
    row_version = Column(Integer, nullable=False, default=1, server_default="1")


class KnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"
    __table_args__ = (
        UniqueConstraint("canonical_gap_key", name="uq_knowledge_gaps_canonical_gap_key"),
        CheckConstraint(_vocab_sql("gap_type", KnowledgeGapType), name="ck_kg_gap_type_vocab"),
        CheckConstraint(_vocab_sql("priority", KnowledgeGapPriority), name="ck_kg_priority_vocab"),
        CheckConstraint(_vocab_sql("severity", KnowledgeGapSeverity), name="ck_kg_severity_vocab"),
        CheckConstraint(_vocab_sql("urgency", KnowledgeGapUrgency), name="ck_kg_urgency_vocab"),
        CheckConstraint(_vocab_sql("status", KnowledgeGapStatus), name="ck_kg_status_vocab"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_kg_confidence_range"),
        CheckConstraint("retry_count >= 0", name="ck_kg_retry_count_nonneg"),
        CheckConstraint("description IS NULL OR char_length(description) <= 8000", name="ck_kg_description_length"),
        CheckConstraint("current_knowledge_state IS NULL OR char_length(current_knowledge_state) <= 4000", name="ck_kg_current_knowledge_state_length"),
        CheckConstraint("required_knowledge_state IS NULL OR char_length(required_knowledge_state) <= 4000", name="ck_kg_required_knowledge_state_length"),
        CheckConstraint("next_action IS NULL OR char_length(next_action) <= 2000", name="ck_kg_next_action_length"),
        CheckConstraint("blocker IS NULL OR char_length(blocker) <= 2000", name="ck_kg_blocker_length"),
        Index("ix_kg_status_priority_severity", "status", "priority", "severity"),
        Index("ix_kg_next_review_at", "next_review_at"),
        Index("ix_kg_target_source_profile_id", "target_source_profile_id"),
        Index("ix_kg_discovered_attempt_id", "discovered_attempt_id"),
        Index("ix_kg_target_knowledge_unit_id", "target_knowledge_unit_id"),
        Index("ix_kg_capability_id", "capability_id"),
        Index("ix_kg_target_package_id", "target_package_id"),
        Index("ix_kg_domain_subdomain", "domain", "subdomain"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    canonical_gap_key = Column(String(64), nullable=False)
    canonicalization_version = Column(String(32), nullable=False, default="v1", server_default="v1")
    hash_algorithm = Column(String(32), nullable=False, default="SHA-256", server_default="SHA-256")
    domain = Column(String(128), nullable=False)
    subdomain = Column(String(128), nullable=True)
    capability_id = Column(String(64), nullable=True)
    gap_type = Column(String(64), nullable=False)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    evidence_of_gap = Column(Text, nullable=True)
    current_knowledge_state = Column(Text, nullable=True)
    required_knowledge_state = Column(Text, nullable=True)
    source_need = Column(Text, nullable=True)
    priority = Column(String(32), nullable=False, default="P2", server_default="P2")
    severity = Column(String(32), nullable=False, default="MEDIUM", server_default="MEDIUM")
    urgency = Column(String(32), nullable=False, default="NORMAL", server_default="NORMAL")
    confidence = Column(Float, nullable=True)
    status = Column(String(32), nullable=False, default="OPEN", server_default="OPEN")
    owner_reference = Column(String(512), nullable=True)
    reviewer_reference = Column(String(512), nullable=True)
    blocker = Column(Text, nullable=True)
    dependencies = Column(Text, nullable=True)
    target_package_id = Column(String(64), nullable=True)
    target_source_profile_id = Column(Integer, ForeignKey("governed_source_profiles.id", ondelete="RESTRICT", name="fk_knowledge_gaps_target_source_profile_id"), nullable=True)
    target_knowledge_unit_id = Column(Integer, ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_knowledge_gaps_target_knowledge_unit_id"), nullable=True)
    discovered_by = Column(String(512), nullable=True)
    discovered_attempt_id = Column(Integer, ForeignKey("weekly_knowledge_run_attempts.id", ondelete="RESTRICT", name="fk_knowledge_gaps_discovered_attempt_id"), nullable=True)
    next_action = Column(Text, nullable=True)
    next_review_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at = Column(DateTime, nullable=True)
    resolution_type = Column(String(64), nullable=True)
    resolution_evidence = Column(Text, nullable=True)
    resolved_by_reference = Column(String(512), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow, nullable=False)
    row_version = Column(Integer, nullable=False, default=1, server_default="1")


class WeeklyRunSourceResult(Base):
    __tablename__ = "weekly_run_source_results"
    __table_args__ = (
        UniqueConstraint("attempt_id", "source_profile_id", name="uq_wrsr_attempt_source_profile"),
        CheckConstraint(_vocab_sql("result_status", RunSourceResultStatus), name="ck_wrsr_result_status_vocab"),
        CheckConstraint("failure_reason IS NULL OR char_length(failure_reason) <= 2000", name="ck_wrsr_failure_reason_length"),
        CheckConstraint("knowledge_new_count >= 0", name="ck_wrsr_knowledge_new_count_nonnegative"),
        CheckConstraint("knowledge_updated_count >= 0", name="ck_wrsr_knowledge_updated_count_nonnegative"),
        CheckConstraint("knowledge_superseded_count >= 0", name="ck_wrsr_knowledge_superseded_count_nonnegative"),
        CheckConstraint("knowledge_rejected_count >= 0", name="ck_wrsr_knowledge_rejected_count_nonnegative"),
        CheckConstraint("gap_created_count >= 0", name="ck_wrsr_gap_created_count_nonnegative"),
        CheckConstraint("warning_count >= 0", name="ck_wrsr_warning_count_nonnegative"),
        CheckConstraint("error_count >= 0", name="ck_wrsr_error_count_nonnegative"),
        Index("ix_wrsr_source_profile_id", "source_profile_id"),
        Index("ix_wrsr_result_status", "result_status"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    attempt_id = Column(Integer, ForeignKey("weekly_knowledge_run_attempts.id", ondelete="RESTRICT", name="fk_wrsr_attempt_id"), nullable=False)
    source_profile_id = Column(Integer, ForeignKey("governed_source_profiles.id", ondelete="RESTRICT", name="fk_wrsr_source_profile_id"), nullable=False)
    source_version_id = Column(Integer, ForeignKey("governed_source_profile_versions.id", ondelete="RESTRICT", name="fk_wrsr_source_version_id"), nullable=True)
    result_status = Column(String(32), nullable=False)
    checked_at = Column(DateTime, nullable=True)
    fetch_outcome = Column(String(64), nullable=True)
    extraction_outcome = Column(String(64), nullable=True)
    publication_outcome = Column(String(64), nullable=True)
    knowledge_new_count = Column(Integer, nullable=False, default=0, server_default="0")
    knowledge_updated_count = Column(Integer, nullable=False, default=0, server_default="0")
    knowledge_superseded_count = Column(Integer, nullable=False, default=0, server_default="0")
    knowledge_rejected_count = Column(Integer, nullable=False, default=0, server_default="0")
    gap_created_count = Column(Integer, nullable=False, default=0, server_default="0")
    warning_count = Column(Integer, nullable=False, default=0, server_default="0")
    error_count = Column(Integer, nullable=False, default=0, server_default="0")
    failure_code = Column(String(128), nullable=True)
    failure_reason = Column(Text, nullable=True)
    evidence_reference = Column(String(2048), nullable=True)
    content_fingerprint = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)


class WeeklyRunGapResult(Base):
    __tablename__ = "weekly_run_gap_results"
    __table_args__ = (
        UniqueConstraint("attempt_id", "gap_id", name="uq_wrgr_attempt_gap"),
        CheckConstraint(_vocab_sql("result_type", RunGapResultType), name="ck_wrgr_result_type_vocab"),
        CheckConstraint("previous_status IS NULL OR (" + _vocab_sql("previous_status", KnowledgeGapStatus) + ")", name="ck_wrgr_previous_status_vocab"),
        CheckConstraint("new_status IS NULL OR (" + _vocab_sql("new_status", KnowledgeGapStatus) + ")", name="ck_wrgr_new_status_vocab"),
        Index("ix_wrgr_gap_id", "gap_id"),
        Index("ix_wrgr_result_type", "result_type"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    attempt_id = Column(Integer, ForeignKey("weekly_knowledge_run_attempts.id", ondelete="RESTRICT", name="fk_wrgr_attempt_id"), nullable=False)
    gap_id = Column(Integer, ForeignKey("knowledge_gaps.id", ondelete="RESTRICT", name="fk_wrgr_gap_id"), nullable=False)
    result_type = Column(String(32), nullable=False)
    previous_status = Column(String(32), nullable=True)
    new_status = Column(String(32), nullable=True)
    evidence_reference = Column(String(2048), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)


class I5GovernanceDecision(Base):
    __tablename__ = "i5_governance_decisions"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "decision_request_key", name="uq_i5gd_decision_request"),
        UniqueConstraint("id", "entity_type", "entity_id", "decision_family", name="uq_i5gd_id_entity_family"),
        CheckConstraint(_vocab_sql("entity_type", GovernanceEntityType), name="ck_i5gd_entity_type_vocab"),
        CheckConstraint(_vocab_sql("decision_family", GovernanceDecisionFamily), name="ck_i5gd_decision_family_vocab"),
        CheckConstraint(_vocab_sql("decision_type", GovernanceDecisionType), name="ck_i5gd_decision_type_vocab"),
        CheckConstraint(_vocab_sql("outcome", GovernanceDecisionOutcome), name="ck_i5gd_outcome_vocab"),
        CheckConstraint(_vocab_sql("actor_type", GovernanceActorType), name="ck_i5gd_actor_type_vocab"),
        CheckConstraint("entity_id > 0", name="ck_i5gd_entity_id_pos"),
        CheckConstraint("supersedes_decision_id IS NULL OR supersedes_decision_id <> id", name="ck_i5gd_supersedes_not_self"),
        CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_i5gd_canonical_hash_format"),
        CheckConstraint("decision_request_key ~ '^[A-Za-z0-9._:-]{1,128}$'", name="ck_i5gd_decision_request_key_format"),
        CheckConstraint("hash_algorithm = 'SHA-256'", name="ck_i5gd_hash_algorithm_constant"),
        CheckConstraint("canonicalization_version = 'v1'", name="ck_i5gd_canonicalization_version_constant"),
        CheckConstraint("reason IS NULL OR char_length(reason) <= 4000", name="ck_i5gd_reason_length"),
        CheckConstraint("(decision_type <> 'SUPERSESSION') OR (supersedes_decision_id IS NOT NULL)", name="ck_i5gd_supersession_requires_parent"),
        CheckConstraint(
            "(decision_type = 'SUPERSESSION') OR ("
            "(decision_type = 'RIGHTS_REVIEW' AND decision_family = 'RIGHTS') OR "
            "(decision_type = 'AUTOMATION_REVIEW' AND decision_family = 'AUTOMATION') OR "
            "(decision_type = 'QUALITY_REVIEW' AND decision_family = 'QUALITY') OR "
            "(decision_type = 'MEDICAL_SAFETY_REVIEW' AND decision_family = 'MEDICAL_SAFETY') OR "
            "(decision_type = 'SECURITY_REVIEW' AND decision_family = 'SECURITY') OR "
            "(decision_type = 'APPROVAL' AND decision_family = 'LIFECYCLE') OR "
            "(decision_type = 'REJECTION' AND decision_family = 'LIFECYCLE') OR "
            "(decision_type = 'ACTIVATION' AND decision_family = 'LIFECYCLE') OR "
            "(decision_type = 'SUSPENSION' AND decision_family = 'LIFECYCLE') OR "
            "(decision_type = 'REVOCATION' AND decision_family = 'LIFECYCLE') OR "
            "(decision_type = 'GAP_RESOLUTION' AND decision_family = 'GAP_LIFECYCLE') OR "
            "(decision_type = 'GAP_REOPEN' AND decision_family = 'GAP_LIFECYCLE') OR "
            "(decision_type = 'RUN_APPROVAL' AND decision_family = 'RUN_APPROVAL') OR "
            "(decision_type = 'RUN_TERMINALIZATION' AND decision_family = 'RUN_TERMINALIZATION')"
            ")",
            name="ck_i5gd_decision_type_family_matrix",
        ),
        CheckConstraint(
            "(entity_type IN ('SOURCE_PROFILE', 'SOURCE_PROFILE_VERSION') AND decision_family IN ('RIGHTS', 'AUTOMATION', 'QUALITY', 'MEDICAL_SAFETY', 'SECURITY', 'LIFECYCLE')) OR "
            "(entity_type = 'KNOWLEDGE_GAP' AND decision_family IN ('LIFECYCLE', 'GAP_LIFECYCLE')) OR "
            "(entity_type = 'WEEKLY_RUN' AND decision_family IN ('LIFECYCLE', 'RUN_APPROVAL')) OR "
            "(entity_type = 'WEEKLY_RUN_ATTEMPT' AND decision_family = 'RUN_TERMINALIZATION') OR "
            "(entity_type = 'RUN_SOURCE_RESULT' AND decision_family IN ('RIGHTS', 'AUTOMATION', 'QUALITY', 'MEDICAL_SAFETY', 'SECURITY', 'LIFECYCLE')) OR "
            "(entity_type = 'RUN_GAP_RESULT' AND decision_family IN ('QUALITY', 'LIFECYCLE'))",
            name="ck_i5gd_entity_family_matrix",
        ),
        CheckConstraint(
            "(entity_type = 'SOURCE_PROFILE' AND decision_type IN ('RIGHTS_REVIEW', 'AUTOMATION_REVIEW', 'QUALITY_REVIEW', 'MEDICAL_SAFETY_REVIEW', 'SECURITY_REVIEW', 'APPROVAL', 'REJECTION', 'ACTIVATION', 'SUSPENSION', 'REVOCATION', 'SUPERSESSION')) OR "
            "(entity_type = 'SOURCE_PROFILE_VERSION' AND decision_type IN ('RIGHTS_REVIEW', 'AUTOMATION_REVIEW', 'QUALITY_REVIEW', 'MEDICAL_SAFETY_REVIEW', 'SECURITY_REVIEW', 'APPROVAL', 'REJECTION', 'SUPERSESSION')) OR "
            "(entity_type = 'KNOWLEDGE_GAP' AND decision_type IN ('APPROVAL', 'REJECTION', 'GAP_RESOLUTION', 'GAP_REOPEN', 'SUPERSESSION')) OR "
            "(entity_type = 'WEEKLY_RUN' AND decision_type IN ('RUN_APPROVAL', 'APPROVAL', 'REJECTION', 'SUSPENSION', 'REVOCATION', 'SUPERSESSION')) OR "
            "(entity_type = 'WEEKLY_RUN_ATTEMPT' AND decision_type IN ('RUN_TERMINALIZATION', 'SUPERSESSION')) OR "
            "(entity_type = 'RUN_SOURCE_RESULT' AND decision_type IN ('RIGHTS_REVIEW', 'AUTOMATION_REVIEW', 'QUALITY_REVIEW', 'MEDICAL_SAFETY_REVIEW', 'SECURITY_REVIEW', 'APPROVAL', 'REJECTION', 'SUPERSESSION')) OR "
            "(entity_type = 'RUN_GAP_RESULT' AND decision_type IN ('QUALITY_REVIEW', 'APPROVAL', 'REJECTION', 'SUPERSESSION'))",
            name="ck_i5gd_entity_decision_matrix",
        ),
        ForeignKeyConstraint(["supersedes_decision_id", "entity_type", "entity_id", "decision_family"], ["i5_governance_decisions.id", "i5_governance_decisions.entity_type", "i5_governance_decisions.entity_id", "i5_governance_decisions.decision_family"], name="fk_i5gd_supersedes_same_entity_family", ondelete="RESTRICT"),
        Index("uq_i5gd_one_superseder", "supersedes_decision_id", unique=True, postgresql_where=text("supersedes_decision_id IS NOT NULL")),
        Index("uq_i5gd_one_root_per_family", "entity_type", "entity_id", "decision_family", unique=True, postgresql_where=text("supersedes_decision_id IS NULL")),
        Index("ix_i5gd_entity_history", "entity_type", "entity_id", "created_at", "id"),
        Index("ix_i5gd_family_history", "entity_type", "entity_id", "decision_family", "created_at", "id"),
        Index("ix_i5gd_content_hash", "hash_algorithm", "canonicalization_version", "canonical_hash"),
        Index("ix_i5gd_decision_type", "decision_type"),
        Index("ix_i5gd_outcome", "outcome"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(Integer, nullable=False)
    decision_family = Column(String(64), nullable=False)
    decision_type = Column(String(64), nullable=False)
    decision_request_key = Column(String(128), nullable=False)
    from_state = Column(String(64), nullable=True)
    to_state = Column(String(64), nullable=True)
    outcome = Column(String(32), nullable=False)
    reason_code = Column(String(128), nullable=True)
    reason = Column(Text, nullable=True)
    actor_type = Column(String(32), nullable=False)
    actor_reference = Column(String(512), nullable=True)
    evidence_reference = Column(String(2048), nullable=True)
    decision_metadata = Column(Text, nullable=True)
    canonical_hash = Column(String(64), nullable=False)
    canonicalization_version = Column(String(32), nullable=False, default="v1", server_default="v1")
    hash_algorithm = Column(String(32), nullable=False, default="SHA-256", server_default="SHA-256")
    supersedes_decision_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)



# ---------------------------------------------------------------------------
# I5-IMPL-W1-P02 — Raw Retention / Structured Knowledge Unit / Provenance
# Migration AUTHOR_ONLY deferred; runtime harness uses metadata.create_all.
# Zero relationship() declarations (W1-P01 convention).
# ---------------------------------------------------------------------------


class I5RawEvidence(Base):
    __tablename__ = "i5_raw_evidence"
    __table_args__ = (
        CheckConstraint(_vocab_sql("retention_mode", RawRetentionMode), name="ck_ire_retention_mode_vocab"),
        CheckConstraint(_vocab_sql("storage_mode", RawStorageMode), name="ck_ire_storage_mode_vocab"),
        CheckConstraint(_vocab_sql("rights_terms_state", RightsTermsState), name="ck_ire_rights_terms_state_vocab"),
        CheckConstraint(_vocab_sql("robots_access_state", RobotsAccessState), name="ck_ire_robots_access_state_vocab"),
        CheckConstraint(_vocab_sql("redaction_state", RedactionState), name="ck_ire_redaction_state_vocab"),
        CheckConstraint(_vocab_sql("prohibited_data_state", ProhibitedDataState), name="ck_ire_prohibited_data_state_vocab"),
        CheckConstraint(_vocab_sql("expiry_state", ExpiryState), name="ck_ire_expiry_state_vocab"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_ire_content_hash_format"),
        CheckConstraint("byte_hash IS NULL OR byte_hash ~ '^[0-9a-f]{64}$'", name="ck_ire_byte_hash_format"),
        CheckConstraint("normalized_hash IS NULL OR normalized_hash ~ '^[0-9a-f]{64}$'", name="ck_ire_normalized_hash_format"),
        CheckConstraint("hash_algorithm = 'SHA-256'", name="ck_ire_hash_algorithm_constant"),
        CheckConstraint("char_length(canonical_url) >= 1", name="ck_ire_canonical_url_nonempty"),
        CheckConstraint("supersedes_raw_evidence_id IS NULL OR supersedes_raw_evidence_id <> id", name="ck_ire_supersedes_not_self"),
        CheckConstraint(
            "(prohibited_data_state <> 'CONFIRMED_PROHIBITED') OR (retention_mode = 'RAW_EXCLUDED_PROTECTED_ELEMENTS')",
            name="ck_ire_prohibited_requires_excluded_mode",
        ),
        CheckConstraint(
            "recoverability_state IS NULL OR recoverability_state IN ('RECOVERABLE', 'ABSENCE_GOVERNED', 'UNKNOWN')",
            name="ck_ire_recoverability_state_vocab",
        ),
        UniqueConstraint("content_hash", "source_profile_id", "canonical_url", name="uq_ire_content_source_url"),
        Index("ix_ire_source_profile_id", "source_profile_id"),
        Index("ix_ire_retrieval_run_id", "retrieval_run_id"),
        Index("ix_ire_retention_mode", "retention_mode"),
        Index("ix_ire_content_hash", "content_hash"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    source_profile_id = Column(Integer, ForeignKey("governed_source_profiles.id", ondelete="RESTRICT", name="fk_ire_source_profile_id"), nullable=False)
    source_document_id = Column(String(128), nullable=True)
    source_version_id = Column(String(128), nullable=True)
    retrieval_run_id = Column(Integer, ForeignKey("weekly_knowledge_runs.id", ondelete="SET NULL", name="fk_ire_retrieval_run_id"), nullable=True)
    retrieval_timestamp = Column(DateTime, nullable=False)
    canonical_url = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    byte_hash = Column(String(64), nullable=True)
    normalized_hash = Column(String(64), nullable=True)
    hash_algorithm = Column(String(32), nullable=False, default="SHA-256", server_default="SHA-256")
    mime_type = Column(String(128), nullable=True)
    language = Column(String(32), nullable=True)
    jurisdiction = Column(String(64), nullable=True)
    storage_mode = Column(String(64), nullable=False, default="NONE", server_default="NONE")
    retention_mode = Column(String(64), nullable=False)
    rights_terms_state = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    robots_access_state = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    redaction_state = Column(String(32), nullable=False, default="NONE", server_default="NONE")
    prohibited_data_state = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    expiry_state = Column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    supersedes_raw_evidence_id = Column(Integer, ForeignKey("i5_raw_evidence.id", ondelete="RESTRICT", name="fk_ire_supersedes_raw_evidence_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    created_by_run_id = Column(Integer, ForeignKey("weekly_knowledge_runs.id", ondelete="SET NULL", name="fk_ire_created_by_run_id"), nullable=True)
    # DB-03 / §270.F durable locator / recoverability contract
    storage_locator = Column(Text, nullable=True)
    object_key = Column(Text, nullable=True)
    durable_path = Column(Text, nullable=True)
    byte_size = Column(BigInteger, nullable=True)
    integrity_state = Column(String(32), nullable=True)
    recoverability_state = Column(String(32), nullable=True)


class KnowledgeUnit(Base):
    __tablename__ = "knowledge_units"
    __table_args__ = (
        CheckConstraint(_vocab_sql("knowledge_type", KnowledgeType), name="ck_ku_knowledge_type_vocab"),
        CheckConstraint(_vocab_sql("evidence_strength", EvidenceStrength), name="ck_ku_evidence_strength_vocab"),
        CheckConstraint(_vocab_sql("medical_safety_state", MedicalSafetyState), name="ck_ku_medical_safety_state_vocab"),
        CheckConstraint(_vocab_sql("conflict_state", ConflictState), name="ck_ku_conflict_state_vocab"),
        CheckConstraint(_vocab_sql("freshness_state", FreshnessState), name="ck_ku_freshness_state_vocab"),
        CheckConstraint(_vocab_sql("review_state", ReviewState), name="ck_ku_review_state_vocab"),
        CheckConstraint(_vocab_sql("publication_state", PublicationState), name="ck_ku_publication_state_vocab"),
        CheckConstraint(_vocab_sql("runtime_eligibility", KnowledgeUnitRuntimeEligibility), name="ck_ku_runtime_eligibility_vocab"),
        CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_ku_canonical_hash_format"),
        CheckConstraint("deduplication_key ~ '^[0-9a-f]{64}$'", name="ck_ku_deduplication_key_format"),
        CheckConstraint("hash_algorithm = 'SHA-256'", name="ck_ku_hash_algorithm_constant"),
        CheckConstraint("canonicalization_version = 'v1'", name="ck_ku_canonicalization_version_constant"),
        CheckConstraint("char_length(normalized_statement) >= 1", name="ck_ku_normalized_statement_nonempty"),
        CheckConstraint("supersedes_unit_id IS NULL OR supersedes_unit_id <> id", name="ck_ku_supersedes_not_self"),
        CheckConstraint(
            "(runtime_eligibility <> 'ELIGIBLE') OR (provenance_complete = true)",
            name="ck_ku_eligible_requires_provenance",
        ),
        UniqueConstraint("canonical_unit_id", "immutable_version_id", name="uq_ku_canonical_version"),
        UniqueConstraint("deduplication_key", name="uq_ku_deduplication_key"),
        Index("ix_ku_domain", "domain"),
        Index("ix_ku_runtime_eligibility", "runtime_eligibility"),
        Index("ix_ku_canonical_hash", "canonical_hash"),
        Index("ix_ku_manifest_track_id", "manifest_track_id"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    canonical_unit_id = Column(String(64), nullable=False)
    immutable_version_id = Column(String(64), nullable=False)
    domain = Column(String(128), nullable=False)
    topic_taxonomy = Column(String(256), nullable=True)
    disease_or_health_condition = Column(String(256), nullable=True)
    manifest_entity_id = Column(String(16), nullable=True)
    manifest_track_id = Column(String(64), nullable=True)
    language = Column(String(32), nullable=False, default="en", server_default="en")
    knowledge_type = Column(String(32), nullable=False)
    normalized_statement = Column(Text, nullable=False)
    applicability = Column(Text, nullable=True)
    exclusions = Column(Text, nullable=True)
    population = Column(String(256), nullable=True)
    jurisdiction = Column(String(64), nullable=True)
    evidence_strength = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    medical_safety_state = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    conflict_state = Column(String(32), nullable=False, default="NONE", server_default="NONE")
    freshness_state = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    review_state = Column(String(32), nullable=False, default="NOT_REVIEWED", server_default="NOT_REVIEWED")
    publication_state = Column(String(32), nullable=False, default="DRAFT", server_default="DRAFT")
    runtime_eligibility = Column(String(32), nullable=False, default="NOT_ELIGIBLE", server_default="NOT_ELIGIBLE")
    provenance_complete = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    deduplication_key = Column(String(64), nullable=False)
    canonical_hash = Column(String(64), nullable=False)
    hash_algorithm = Column(String(32), nullable=False, default="SHA-256", server_default="SHA-256")
    canonicalization_version = Column(String(32), nullable=False, default="v1", server_default="v1")
    supersedes_unit_id = Column(Integer, ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_ku_supersedes_unit_id"), nullable=True)
    retraction_reason = Column(Text, nullable=True)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow, nullable=False)
    last_reviewed_at = Column(DateTime, nullable=True)


class KnowledgeProvenance(Base):
    __tablename__ = "knowledge_provenance"
    __table_args__ = (
        CheckConstraint("content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name="ck_kp_content_hash_format"),
        CheckConstraint("byte_hash IS NULL OR byte_hash ~ '^[0-9a-f]{64}$'", name="ck_kp_byte_hash_format"),
        CheckConstraint("normalized_hash IS NULL OR normalized_hash ~ '^[0-9a-f]{64}$'", name="ck_kp_normalized_hash_format"),
        CheckConstraint("char_length(retrieval_method) >= 1", name="ck_kp_retrieval_method_nonempty"),
        UniqueConstraint("knowledge_unit_id", name="uq_kp_knowledge_unit_id"),
        Index("ix_kp_source_profile_id", "source_profile_id"),
        Index("ix_kp_raw_evidence_id", "raw_evidence_id"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    knowledge_unit_id = Column(Integer, ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_kp_knowledge_unit_id"), nullable=False)
    source_profile_id = Column(Integer, ForeignKey("governed_source_profiles.id", ondelete="RESTRICT", name="fk_kp_source_profile_id"), nullable=False)
    source_document_id = Column(String(128), nullable=True)
    source_version_id = Column(String(128), nullable=True)
    raw_evidence_id = Column(Integer, ForeignKey("i5_raw_evidence.id", ondelete="RESTRICT", name="fk_kp_raw_evidence_id"), nullable=True)
    retrieval_method = Column(String(128), nullable=False)
    access_route = Column(String(128), nullable=True)
    content_hash = Column(String(64), nullable=True)
    byte_hash = Column(String(64), nullable=True)
    normalized_hash = Column(String(64), nullable=True)
    extraction_process = Column(String(256), nullable=True)
    normalization_process = Column(String(256), nullable=True)
    review_decision_id = Column(Integer, ForeignKey("i5_governance_decisions.id", ondelete="SET NULL", name="fk_kp_review_decision_id"), nullable=True)
    attribution_data = Column(Text, nullable=True)
    citation_rendering_data = Column(Text, nullable=True)
    conflict_hook = Column(String(256), nullable=True)
    supersession_hook = Column(String(256), nullable=True)
    retraction_hook = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# I5-IMPL-W2-P01 — Knowledge Memory / Versioning / Diff / Supersession
# ---------------------------------------------------------------------------


class KnowledgeMemoryItem(Base):
    __tablename__ = "knowledge_memory_items"
    __table_args__ = (
        CheckConstraint(_vocab_sql("evidence_strength", EvidenceStrength), name="ck_kmi_evidence_strength_vocab"),
        CheckConstraint(_vocab_sql("freshness_state", FreshnessState), name="ck_kmi_freshness_state_vocab"),
        CheckConstraint(_vocab_sql("conflict_state", ConflictState), name="ck_kmi_conflict_state_vocab"),
        CheckConstraint(_vocab_sql("medical_safety_state", MedicalSafetyState), name="ck_kmi_medical_safety_state_vocab"),
        CheckConstraint(
            _vocab_sql("runtime_eligibility", KnowledgeUnitRuntimeEligibility),
            name="ck_kmi_runtime_eligibility_vocab",
        ),
        CheckConstraint(_vocab_sql("supersession_state", SupersessionState), name="ck_kmi_supersession_state_vocab"),
        CheckConstraint(
            "(runtime_eligibility <> 'ELIGIBLE') OR (supersession_state = 'CURRENT')",
            name="ck_kmi_eligible_requires_current",
        ),
        UniqueConstraint("memory_item_id", name="uq_kmi_memory_item_id"),
        UniqueConstraint("knowledge_unit_id", name="uq_kmi_knowledge_unit_id"),
        Index("ix_kmi_domain", "domain"),
        Index("ix_kmi_runtime_eligibility", "runtime_eligibility"),
        Index("ix_kmi_supersession_state", "supersession_state"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    memory_item_id = Column(String(64), nullable=False)
    knowledge_unit_id = Column(
        Integer,
        ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_kmi_knowledge_unit_id"),
        nullable=False,
    )
    domain = Column(String(128), nullable=False)
    topic = Column(String(256), nullable=True)
    knowledge_version = Column(String(64), nullable=False)
    source_ids = Column(Text, nullable=True)
    source_versions = Column(Text, nullable=True)
    evidence_strength = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    freshness_state = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    conflict_state = Column(String(32), nullable=False, default="NONE", server_default="NONE")
    medical_safety_state = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    runtime_eligibility = Column(String(32), nullable=False, default="NOT_ELIGIBLE", server_default="NOT_ELIGIBLE")
    supersession_state = Column(String(32), nullable=False, default="CURRENT", server_default="CURRENT")
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )


class KnowledgeMemoryTransition(Base):
    __tablename__ = "knowledge_memory_transitions"
    __table_args__ = (
        CheckConstraint(
            _vocab_sql("transition_kind", MemoryTransitionKind),
            name="ck_kmt_transition_kind_vocab",
        ),
        CheckConstraint(_vocab_sql("change_kind", MemoryChangeKind), name="ck_kmt_change_kind_vocab"),
        CheckConstraint("idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_kmt_idempotency_key_format"),
        CheckConstraint(
            "diff_json IS NULL OR (char_length(diff_json) >= 2 AND left(diff_json, 1) = '{' AND right(diff_json, 1) = '}')",
            name="ck_kmt_diff_json_object",
        ),
        UniqueConstraint("idempotency_key", name="uq_kmt_idempotency_key"),
        Index("ix_kmt_memory_item_id", "memory_item_id"),
        Index("ix_kmt_created_at", "created_at"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    memory_row_id = Column(
        Integer,
        ForeignKey("knowledge_memory_items.id", ondelete="RESTRICT", name="fk_kmt_memory_item_row_id"),
        nullable=False,
    )
    memory_item_id = Column(String(64), nullable=False)
    from_knowledge_unit_id = Column(
        Integer,
        ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_kmt_from_knowledge_unit_id"),
        nullable=True,
    )
    to_knowledge_unit_id = Column(
        Integer,
        ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_kmt_to_knowledge_unit_id"),
        nullable=True,
    )
    transition_kind = Column(String(32), nullable=False)
    change_kind = Column(String(32), nullable=False)
    diff_json = Column(Text, nullable=True)
    idempotency_key = Column(String(64), nullable=False)
    reason = Column(Text, nullable=True)
    process_id = Column(
        String(128),
        nullable=False,
        default="W2P01_SUPERSESSION_SERVICE",
        server_default="W2P01_SUPERSESSION_SERVICE",
    )
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# I5-IMPL-W2-P02 — Conflict records / Medical-safety review queue
# ---------------------------------------------------------------------------


class KnowledgeConflict(Base):
    __tablename__ = "knowledge_conflicts"
    __table_args__ = (
        CheckConstraint(_vocab_sql("conflict_state", ConflictState), name="ck_kc_conflict_state_vocab"),
        CheckConstraint("idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_kc_idempotency_key_format"),
        CheckConstraint(
            "knowledge_unit_id_a < knowledge_unit_id_b",
            name="ck_kc_units_ordered",
        ),
        UniqueConstraint("idempotency_key", name="uq_kc_idempotency_key"),
        UniqueConstraint("conflict_key", name="uq_kc_conflict_key"),
        UniqueConstraint("knowledge_unit_id_a", "knowledge_unit_id_b", name="uq_kc_unit_pair"),
        Index("ix_kc_conflict_state", "conflict_state"),
        Index("ix_kc_ku_a", "knowledge_unit_id_a"),
        Index("ix_kc_ku_b", "knowledge_unit_id_b"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    conflict_key = Column(String(64), nullable=False)
    knowledge_unit_id_a = Column(
        Integer,
        ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_kc_ku_a"),
        nullable=False,
    )
    knowledge_unit_id_b = Column(
        Integer,
        ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_kc_ku_b"),
        nullable=False,
    )
    conflict_state = Column(
        String(32),
        nullable=False,
        default="SUSPECTED",
        server_default="SUSPECTED",
    )
    conflict_summary = Column(Text, nullable=True)
    resolution_note = Column(Text, nullable=True)
    idempotency_key = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )


class SafetyReviewQueueItem(Base):
    __tablename__ = "knowledge_safety_reviews"
    __table_args__ = (
        CheckConstraint(
            _vocab_sql("queue_status", SafetyReviewQueueStatus),
            name="ck_ksr_queue_status_vocab",
        ),
        CheckConstraint(
            _vocab_sql("medical_safety_state", MedicalSafetyState),
            name="ck_ksr_medical_safety_state_vocab",
        ),
        CheckConstraint("idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_ksr_idempotency_key_format"),
        UniqueConstraint("queue_item_id", name="uq_ksr_queue_item_id"),
        UniqueConstraint("idempotency_key", name="uq_ksr_idempotency_key"),
        Index("ix_ksr_queue_status", "queue_status"),
        Index("ix_ksr_knowledge_unit_id", "knowledge_unit_id"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    queue_item_id = Column(String(64), nullable=False)
    knowledge_unit_id = Column(
        Integer,
        ForeignKey("knowledge_units.id", ondelete="RESTRICT", name="fk_ksr_knowledge_unit_id"),
        nullable=False,
    )
    queue_status = Column(
        String(32),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
    )
    medical_safety_state = Column(String(32), nullable=False)
    high_risk_domain = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    reason = Column(Text, nullable=True)
    decision_id = Column(
        Integer,
        ForeignKey("i5_governance_decisions.id", ondelete="SET NULL", name="fk_ksr_decision_id"),
        nullable=True,
    )
    idempotency_key = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )


# -------------------- I5-IMPL-W5-P01 / P10 — Iran directory (NOT clinical KU) --------------------
# Permanent law: IR directory records are discovery metadata only.
# They MUST NOT FK to knowledge_units / become KnowledgeUnit clinical authority.


class IranDoctor(Base):
    """Global Iran doctor directory entry (not user-owned UserDoctor)."""

    __tablename__ = "iran_doctors"
    __table_args__ = (
        CheckConstraint("char_length(canonical_directory_key) >= 1", name="ck_iran_doctor_key_nonempty"),
        CheckConstraint("char_length(full_name) >= 1", name="ck_iran_doctor_name_nonempty"),
        CheckConstraint(
            "record_state IN ('ACTIVE', 'INACTIVE')",
            name="ck_iran_doctor_record_state",
        ),
        UniqueConstraint("canonical_directory_key", name="uq_iran_doctor_canonical_key"),
        Index("ix_iran_doctor_city", "city"),
        Index("ix_iran_doctor_province", "province"),
        Index("ix_iran_doctor_specialty", "specialty"),
        Index("ix_iran_doctor_record_state", "record_state"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    canonical_directory_key = Column(String(128), nullable=False)
    full_name = Column(String(256), nullable=False)
    specialty = Column(String(128), nullable=True)
    city = Column(String(128), nullable=True)
    province = Column(String(128), nullable=True)
    phone = Column(String(64), nullable=True)
    address = Column(String(512), nullable=True)
    record_state = Column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    # Future governed-source readiness only — no live IR source embedded.
    source_system_label = Column(String(128), nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    last_observed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )


class IranLaboratory(Base):
    """Global Iran laboratory directory entry."""

    __tablename__ = "iran_laboratories"
    __table_args__ = (
        CheckConstraint("char_length(canonical_directory_key) >= 1", name="ck_iran_lab_key_nonempty"),
        CheckConstraint("char_length(name) >= 1", name="ck_iran_lab_name_nonempty"),
        CheckConstraint(
            "record_state IN ('ACTIVE', 'INACTIVE')",
            name="ck_iran_lab_record_state",
        ),
        UniqueConstraint("canonical_directory_key", name="uq_iran_lab_canonical_key"),
        Index("ix_iran_lab_city", "city"),
        Index("ix_iran_lab_province", "province"),
        Index("ix_iran_lab_record_state", "record_state"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    canonical_directory_key = Column(String(128), nullable=False)
    name = Column(String(256), nullable=False)
    city = Column(String(128), nullable=True)
    province = Column(String(128), nullable=True)
    services_text = Column(String(512), nullable=True)
    phone = Column(String(64), nullable=True)
    address = Column(String(512), nullable=True)
    record_state = Column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    source_system_label = Column(String(128), nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    last_observed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )


class IranHospital(Base):
    """Global Iran hospital / medical-center directory entry."""

    __tablename__ = "iran_hospitals"
    __table_args__ = (
        CheckConstraint("char_length(canonical_directory_key) >= 1", name="ck_iran_hosp_key_nonempty"),
        CheckConstraint("char_length(name) >= 1", name="ck_iran_hosp_name_nonempty"),
        CheckConstraint(
            "facility_type IN ('HOSPITAL', 'MEDICAL_CENTER')",
            name="ck_iran_hosp_facility_type",
        ),
        CheckConstraint(
            "record_state IN ('ACTIVE', 'INACTIVE')",
            name="ck_iran_hosp_record_state",
        ),
        UniqueConstraint("canonical_directory_key", name="uq_iran_hosp_canonical_key"),
        Index("ix_iran_hosp_city", "city"),
        Index("ix_iran_hosp_province", "province"),
        Index("ix_iran_hosp_facility_type", "facility_type"),
        Index("ix_iran_hosp_record_state", "record_state"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    canonical_directory_key = Column(String(128), nullable=False)
    name = Column(String(256), nullable=False)
    facility_type = Column(String(32), nullable=False, default="HOSPITAL", server_default="HOSPITAL")
    city = Column(String(128), nullable=True)
    province = Column(String(128), nullable=True)
    phone = Column(String(64), nullable=True)
    address = Column(String(512), nullable=True)
    record_state = Column(String(32), nullable=False, default="ACTIVE", server_default="ACTIVE")
    source_system_label = Column(String(128), nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    last_observed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )
# ---------------------------------------------------------------------------
# DB-03 / §270 — Additive canonical authorities (Wave 1)
# Zero relationship() declarations (I5 / DB-03 convention for new tables).
# ---------------------------------------------------------------------------


class UserConsent(Base):
    """Durable consent authority. Caregiver relationship != medical notify authorization."""

    __tablename__ = "user_consents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'revoked', 'expired')",
            name="ck_user_consents_status_vocab",
        ),
        Index(
            "uq_user_consents_active_grant",
            "subject_user_id",
            "consent_type",
            "purpose",
            "grantee_type",
            "grantee_id",
            "effective_from",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_user_consents_subject_user_id", "subject_user_id"),
        Index("ix_user_consents_status", "status"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    subject_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_user_consents_subject_user_id"),
        nullable=False,
    )
    consent_type = Column(String(64), nullable=False)
    purpose = Column(String(128), nullable=False)
    scope_summary = Column(Text, nullable=True)
    grantee_type = Column(String(64), nullable=False)
    grantee_id = Column(String(128), nullable=False)
    relationship_id = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="pending", server_default="pending")
    policy_version = Column(String(32), nullable=True)
    granted_at = Column(DateTime(timezone=True), nullable=True)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_until = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(Text, nullable=True)
    source = Column(String(64), nullable=True)
    provenance = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )


class UserConsentScope(Base):
    __tablename__ = "user_consent_scopes"
    __table_args__ = (
        UniqueConstraint("consent_id", "permission_key", name="uq_user_consent_scopes_consent_permission"),
        Index("ix_user_consent_scopes_consent_id", "consent_id"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    consent_id = Column(
        Integer,
        ForeignKey("user_consents.id", ondelete="CASCADE", name="fk_user_consent_scopes_consent_id"),
        nullable=False,
    )
    permission_key = Column(String(128), nullable=False)
    allowed = Column(Boolean, nullable=False, default=False, server_default="false")
    metadata_json = Column("metadata", Text, nullable=True)


class UserPeriodSummary(Base):
    """I7 canonical period summary authority (DAILY/WEEKLY/MONTHLY/YEARLY)."""

    __tablename__ = "user_period_summaries"
    __table_args__ = (
        CheckConstraint(
            "summary_type IN ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')",
            name="ck_ups_summary_type_vocab",
        ),
        UniqueConstraint(
            "user_id",
            "summary_type",
            "period_start",
            "version",
            name="uq_ups_user_type_period_version",
        ),
        Index("ix_ups_user_id", "user_id"),
        Index("ix_ups_summary_type", "summary_type"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_ups_user_id"),
        nullable=False,
    )
    summary_type = Column(String(16), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    structured_summary_json = Column(Text, nullable=True)
    narrative_summary = Column(Text, nullable=True)
    evidence_range = Column(Text, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="active", server_default="active")
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)


class PhysiologicalMeasurement(Base):
    """Canonical scalar physiological measurement authority (HR). device_events = lifecycle only."""

    __tablename__ = "physiological_measurements"
    __table_args__ = (
        CheckConstraint(
            "measurement_type IN ('heart_rate')",
            name="ck_pm_measurement_type_vocab",
        ),
        UniqueConstraint("idempotency_key", name="uq_pm_idempotency_key"),
        # DESC ordering applied in Alembic DDL for (user_id, measured_at DESC).
        Index("ix_pm_user_measured_at", "user_id", "measured_at"),
        Index("ix_pm_device_measured_at", "device_id", "measured_at"),
        Index("ix_pm_idempotency_key", "idempotency_key"),
    )

    id = Column(BigInteger, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_pm_user_id"),
        nullable=False,
    )
    device_id = Column(
        Integer,
        ForeignKey("devices.id", ondelete="RESTRICT", name="fk_pm_device_id"),
        nullable=False,
    )
    sensor_id = Column(
        Integer,
        ForeignKey("device_sensors.id", ondelete="SET NULL", name="fk_pm_sensor_id"),
        nullable=True,
    )
    measurement_type = Column(String(32), nullable=False)
    numeric_value = Column(Float, nullable=False)
    unit = Column(String(32), nullable=False, default="bpm", server_default="bpm")
    measured_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    quality_state = Column(String(32), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    source_sequence = Column(String(128), nullable=True)
    ingestion_status = Column(String(32), nullable=False, default="accepted", server_default="accepted")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)


class PhysiologicalBaseline(Base):
    __tablename__ = "physiological_baselines"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "measurement_type",
            "baseline_version",
            "window_start",
            name="uq_pb_user_type_version_window",
        ),
        Index("ix_pb_user_id", "user_id"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_pb_user_id"),
        nullable=False,
    )
    measurement_type = Column(String(32), nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    coverage = Column(Float, nullable=True)
    quality = Column(String(32), nullable=True)
    baseline_version = Column(Integer, nullable=False, default=1, server_default="1")
    derived_at = Column(DateTime(timezone=True), nullable=False)
    source_range = Column(Text, nullable=True)
    baseline_value = Column(Float, nullable=True)


class DerivedHealthSignal(Base):
    """Nondiagnostic derived signal; not a diagnosis authority."""

    __tablename__ = "derived_health_signals"
    __table_args__ = (
        Index("ix_dhs_user_id", "user_id"),
        Index("ix_dhs_detected_at", "detected_at"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_dhs_user_id"),
        nullable=False,
    )
    signal_type = Column(String(64), nullable=False)
    severity_band = Column(String(32), nullable=True)
    evidence_measurement_ids = Column(Text, nullable=True)
    policy_ref = Column(String(128), nullable=True)
    detected_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="open", server_default="open")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)


class CareResponsePolicy(Base):
    """Versioned care response policy. Clinical windows MUST remain NULL until authorized."""

    __tablename__ = "care_response_policies"
    __table_args__ = (
        UniqueConstraint("policy_id", "policy_version", name="uq_crp_policy_id_version"),
        Index("ix_crp_status", "status"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    policy_id = Column(String(64), nullable=False)
    policy_version = Column(String(32), nullable=False)
    risk_category = Column(String(64), nullable=False)
    # CRITICAL: no server_default / no seed — clinical timing unapproved
    ack_window_seconds = Column(Integer, nullable=True)
    escalation_window_seconds = Column(Integer, nullable=True)
    expiry_behavior = Column(String(64), nullable=True)
    recipient_rules_json = Column(Text, nullable=True)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_until = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="draft", server_default="draft")
    approval_metadata = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)


class CareEpisode(Base):
    """Care continuity spine (trigger→notify→react→escalate→resolve). Not a diagnosis."""

    __tablename__ = "care_episodes"
    __table_args__ = (
        Index("ix_ce_user_id", "user_id"),
        Index("ix_ce_current_state", "current_state"),
        Index("ix_ce_opened_at", "opened_at"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_ce_user_id"),
        nullable=False,
    )
    origin_type = Column(String(64), nullable=False)
    origin_ref = Column(String(255), nullable=True)
    category = Column(String(64), nullable=True)
    policy_id = Column(String(64), nullable=True)
    policy_version = Column(String(32), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    current_state = Column(String(64), nullable=False, default="open", server_default="open")
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_reason = Column(Text, nullable=True)
    ack_due_at = Column(DateTime(timezone=True), nullable=True)
    escalation_due_at = Column(DateTime(timezone=True), nullable=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
        nullable=False,
    )


class CareEpisodeLink(Base):
    __tablename__ = "care_episode_links"
    __table_args__ = (
        UniqueConstraint("episode_id", "link_type", "link_id", name="uq_cel_episode_type_id"),
        Index("ix_cel_episode_id", "episode_id"),
    )

    id = Column(Integer, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    episode_id = Column(
        Integer,
        ForeignKey("care_episodes.id", ondelete="CASCADE", name="fk_cel_episode_id"),
        nullable=False,
    )
    link_type = Column(String(64), nullable=False)
    link_table = Column(String(128), nullable=False)
    link_id = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)


class PhysiologicalMeasurementRollup(Base):
    """Optional Wave-4 hourly/daily rollup (DESIGN:include). Partitioning still deferred."""

    __tablename__ = "physiological_measurement_rollups"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "measurement_type",
            "bucket_start",
            "bucket_kind",
            name="uq_pmr_user_type_bucket",
        ),
        Index("ix_pmr_user_bucket", "user_id", "bucket_start"),
    )

    id = Column(BigInteger, Identity(start=1), primary_key=True, autoincrement=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_pmr_user_id"),
        nullable=False,
    )
    measurement_type = Column(String(32), nullable=False)
    bucket_kind = Column(String(16), nullable=False)  # hourly | daily
    bucket_start = Column(DateTime(timezone=True), nullable=False)
    bucket_end = Column(DateTime(timezone=True), nullable=False)
    sample_count = Column(Integer, nullable=False, default=0, server_default="0")
    avg_value = Column(Float, nullable=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)


# -------------------- I5-KNOW-01 Trusted Source Registry / Rights / Books --------------------


class I5SourceRegistryExtension(Base):
    """Trusted Source Registry overlay (listing ≠ authorization)."""

    __tablename__ = "i5_source_registry_extensions"

    source_profile_id = Column(
        Integer,
        ForeignKey("governed_source_profiles.id", ondelete="CASCADE", name="fk_sre_source_profile"),
        primary_key=True,
    )
    source_universe = Column(String(32), nullable=False, index=True)
    publisher_family = Column(String(128), nullable=True)
    authority_class = Column(String(64), nullable=False, index=True)
    country = Column(String(64), nullable=True)
    jurisdiction = Column(String(64), nullable=True)
    languages = Column(String(128), nullable=True)
    knowledge_domains = Column(Text, nullable=True)
    specialty_domains = Column(Text, nullable=True)
    canonical_home = Column(Text, nullable=True)
    canonical_discovery_endpoint = Column(Text, nullable=True)
    api_endpoint = Column(Text, nullable=True)
    rss_endpoint = Column(Text, nullable=True)
    atom_endpoint = Column(Text, nullable=True)
    sitemap_endpoint = Column(Text, nullable=True)
    oai_endpoint = Column(Text, nullable=True)
    bulk_endpoint = Column(Text, nullable=True)
    supported_formats = Column(Text, nullable=True)
    access_right = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    automation_right = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN", index=True)
    tdm_right = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    transform_right = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    retain_raw_right = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    retain_derived_right = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    redistribution_right = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    attribution_requirement = Column(Text, nullable=True)
    robots_state = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    rate_limit_policy = Column(Text, nullable=True)
    freshness_policy = Column(Text, nullable=True)
    processing_permission_mode = Column(
        String(64), nullable=False, default="FULLTEXT_AUTOMATION_BLOCKED", server_default="FULLTEXT_AUTOMATION_BLOCKED"
    )
    review_stage = Column(String(32), nullable=False, default="NONE", server_default="NONE")
    credential_authority = Column(Boolean, nullable=False, default=False, server_default="false")
    current_rights_review = Column(Text, nullable=True)
    rights_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    last_authority_verification = Column(DateTime(timezone=True), nullable=True)
    last_successful_acquisition = Column(DateTime(timezone=True), nullable=True)
    last_observed_change = Column(DateTime(timezone=True), nullable=True)
    registry_status = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow, nullable=False)


class I5SourceRegistryRole(Base):
    __tablename__ = "i5_source_registry_roles"
    __table_args__ = (
        UniqueConstraint("source_profile_id", "role", name="uq_srr_profile_role"),
        Index("ix_srr_role", "role"),
    )

    id = Column(BigInteger, Identity(start=1), primary_key=True, autoincrement=True)
    source_profile_id = Column(
        Integer,
        ForeignKey("governed_source_profiles.id", ondelete="CASCADE", name="fk_srr_source_profile"),
        nullable=False,
    )
    role = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)


class I5SourceP0Tag(Base):
    __tablename__ = "i5_source_p0_tags"
    __table_args__ = (
        UniqueConstraint("source_profile_id", "disease", name="uq_sp0_profile_disease"),
        Index("ix_sp0_disease", "disease"),
    )

    id = Column(BigInteger, Identity(start=1), primary_key=True, autoincrement=True)
    source_profile_id = Column(
        Integer,
        ForeignKey("governed_source_profiles.id", ondelete="CASCADE", name="fk_sp0_source_profile"),
        nullable=False,
    )
    disease = Column(String(32), nullable=False)
    relevance = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)


class I5SourceCoverageGap(Base):
    __tablename__ = "i5_source_coverage_gaps"
    __table_args__ = (
        Index("ix_scg_disease_dim", "disease_or_domain", "knowledge_dimension"),
    )

    id = Column(BigInteger, Identity(start=1), primary_key=True, autoincrement=True)
    disease_or_domain = Column(String(128), nullable=False)
    knowledge_dimension = Column(String(128), nullable=False)
    evidence_class = Column(String(64), nullable=True)
    status = Column(String(64), nullable=False)
    detail = Column(Text, nullable=True)
    knowledge_gap_id = Column(
        Integer,
        ForeignKey("knowledge_gaps.id", ondelete="SET NULL", name="fk_scg_knowledge_gap"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow, nullable=False)


class I5ReferenceBook(Base):
    __tablename__ = "i5_reference_books"
    __table_args__ = (UniqueConstraint("book_key", name="uq_irb_book_key"),)

    id = Column(BigInteger, Identity(start=1), primary_key=True, autoincrement=True)
    book_key = Column(String(256), nullable=False)
    title = Column(String(512), nullable=False)
    publisher = Column(String(256), nullable=True)
    publisher_source_profile_id = Column(
        Integer,
        ForeignKey("governed_source_profiles.id", ondelete="SET NULL", name="fk_irb_publisher_gsp"),
        nullable=True,
    )
    authors_editors = Column(Text, nullable=True)
    isbn = Column(String(32), nullable=True)
    specialty = Column(String(128), nullable=True)
    disease_coverage = Column(Text, nullable=True)
    rights_class = Column(String(64), nullable=False, default="UNKNOWN_RIGHTS", server_default="UNKNOWN_RIGHTS")
    medical_authority_note = Column(Text, nullable=True)
    automation_tdm_permission = Column(String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    fulltext_automation_permission = Column(String(32), nullable=False, default="DENIED", server_default="DENIED")
    retention_policy = Column(Text, nullable=True)
    canonical_access_route = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), onupdate=datetime.utcnow, nullable=False)


class I5ReferenceBookEdition(Base):
    __tablename__ = "i5_reference_book_editions"
    __table_args__ = (UniqueConstraint("book_id", "edition_label", name="uq_irbe_book_edition"),)

    id = Column(BigInteger, Identity(start=1), primary_key=True, autoincrement=True)
    book_id = Column(
        BigInteger,
        ForeignKey("i5_reference_books.id", ondelete="CASCADE", name="fk_irbe_book"),
        nullable=False,
    )
    edition_label = Column(String(128), nullable=False)
    volume = Column(String(64), nullable=True)
    publication_year = Column(Integer, nullable=True)
    is_current = Column(Boolean, nullable=False, default=False, server_default="false")
    superseded_by_edition_id = Column(BigInteger, nullable=True)
    access_route = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=func.now(), nullable=False)
