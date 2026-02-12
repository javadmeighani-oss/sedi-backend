"""baseline_v1_schema

Revision ID: 001_baseline_v1
Revises:
Create Date: 2025-02-12

Baseline v1: all tables from current SQLAlchemy models. No real data assumed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_baseline_v1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users (no FK)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("secret_key", sa.String(), nullable=False),
        sa.Column("preferred_language", sa.String(), server_default=sa.text("'en'"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    # Medical conditions (no FK)
    op.create_table(
        "medical_conditions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("embedding_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_medical_conditions_id"), "medical_conditions", ["id"], unique=False)

    # Memory
    op.create_table(
        "memory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_message", sa.String(), nullable=False),
        sa.Column("sedi_response", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_memory_id"), "memory", ["id"], unique=False)

    # Health data
    op.create_table(
        "health_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("heart_rate", sa.String(), nullable=True),
        sa.Column("temperature", sa.String(), nullable=True),
        sa.Column("spo2", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_health_data_id"), "health_data", ["id"], unique=False)

    # Notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("actions_json", sa.Text(), nullable=True),
        sa.Column("deeplink_url", sa.String(length=512), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("ttl_seconds", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notifications_id"), "notifications", ["id"], unique=False)
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)

    # Push devices
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("fcm_token", sa.String(length=512), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_push_devices_id"), "push_devices", ["id"], unique=False)
    op.create_index(op.f("ix_push_devices_user_id"), "push_devices", ["user_id"], unique=False)
    op.create_index(op.f("ix_push_devices_fcm_token"), "push_devices", ["fcm_token"], unique=True)

    # Medications
    op.create_table(
        "medications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("generic_name", sa.String(), nullable=True),
        sa.Column("dosage_form", sa.String(), nullable=True),
        sa.Column("default_dosage", sa.String(), nullable=True),
        sa.Column("condition_id", sa.Integer(), nullable=True),
        sa.Column("embedding_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["condition_id"], ["medical_conditions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_medications_id"), "medications", ["id"], unique=False)

    # User conditions
    op.create_table(
        "user_conditions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("condition_id", sa.Integer(), nullable=False),
        sa.Column("diagnosed_date", sa.DateTime(), nullable=True),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("embedding_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["condition_id"], ["medical_conditions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_conditions_id"), "user_conditions", ["id"], unique=False)
    op.create_index(op.f("ix_user_conditions_user_id"), "user_conditions", ["user_id"], unique=False)

    # User medications
    op.create_table(
        "user_medications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("medication_id", sa.Integer(), nullable=False),
        sa.Column("interval_hours", sa.Integer(), server_default=sa.text("8"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_medications_id"), "user_medications", ["id"], unique=False)
    op.create_index(op.f("ix_user_medications_user_id"), "user_medications", ["user_id"], unique=False)

    # Daily memory summaries
    op.create_table(
        "daily_memory_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("mood", sa.String(), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("last_interaction", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_daily_memory_summaries_id"), "daily_memory_summaries", ["id"], unique=False)
    op.create_index(op.f("ix_daily_memory_summaries_user_id"), "daily_memory_summaries", ["user_id"], unique=False)

    # User memory facts
    op.create_table(
        "user_memory_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("embedding_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_memory_facts_id"), "user_memory_facts", ["id"], unique=False)
    op.create_index(op.f("ix_user_memory_facts_user_id"), "user_memory_facts", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_memory_facts_domain"), "user_memory_facts", ["domain"], unique=False)
    op.create_index(op.f("ix_user_memory_facts_key"), "user_memory_facts", ["key"], unique=False)

    # Device events
    op.create_table(
        "device_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("embedding_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_device_events_id"), "device_events", ["id"], unique=False)
    op.create_index(op.f("ix_device_events_user_id"), "device_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_device_events_device_id"), "device_events", ["device_id"], unique=False)
    op.create_index(op.f("ix_device_events_event_type"), "device_events", ["event_type"], unique=False)

    # Devices
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=False),
        sa.Column("device_type", sa.String(length=50), server_default=sa.text("'heart_rate'"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_devices_id"), "devices", ["id"], unique=False)
    op.create_index(op.f("ix_devices_user_id"), "devices", ["user_id"], unique=False)
    op.create_index(op.f("ix_devices_device_id"), "devices", ["device_id"], unique=True)

    # User profile knowledge
    op.create_table(
        "user_profile_knowledge",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("baseline_summary", sa.Text(), nullable=True),
        sa.Column("goals_json", sa.Text(), nullable=True),
        sa.Column("constraints_json", sa.Text(), nullable=True),
        sa.Column("preferences_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_profile_knowledge_id"), "user_profile_knowledge", ["id"], unique=False)
    op.create_index(op.f("ix_user_profile_knowledge_user_id"), "user_profile_knowledge", ["user_id"], unique=True)

    # User fact candidates
    op.create_table(
        "user_fact_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("source_memory_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_explicit", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_memory_id"], ["memory.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_fact_candidates_id"), "user_fact_candidates", ["id"], unique=False)
    op.create_index(op.f("ix_user_fact_candidates_user_id"), "user_fact_candidates", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_fact_candidates_domain"), "user_fact_candidates", ["domain"], unique=False)

    # User facts
    op.create_table(
        "user_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("confidence", sa.Float(), server_default=sa.text("0.7"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_facts_id"), "user_facts", ["id"], unique=False)
    op.create_index(op.f("ix_user_facts_user_id"), "user_facts", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_facts_key"), "user_facts", ["key"], unique=False)
    op.create_unique_constraint("uq_user_facts_user_id_key", "user_facts", ["user_id", "key"])

    # Notification feedback (depends on notifications, users)
    op.create_table(
        "notification_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notification_feedback_id"), "notification_feedback", ["id"], unique=False)
    op.create_index(op.f("ix_notification_feedback_notification_id"), "notification_feedback", ["notification_id"], unique=False)
    op.create_index(op.f("ix_notification_feedback_user_id"), "notification_feedback", ["user_id"], unique=False)


def downgrade() -> None:
    # Drop in reverse dependency order (dependents first).
    op.drop_table("notification_feedback")
    op.drop_table("user_facts")
    op.drop_table("user_fact_candidates")
    op.drop_table("user_profile_knowledge")
    op.drop_table("devices")
    op.drop_table("device_events")
    op.drop_table("user_memory_facts")
    op.drop_table("daily_memory_summaries")
    op.drop_table("user_medications")
    op.drop_table("user_conditions")
    op.drop_table("medications")
    op.drop_table("push_devices")
    op.drop_table("notifications")
    op.drop_table("health_data")
    op.drop_table("memory")
    op.drop_table("medical_conditions")
    op.drop_table("users")
