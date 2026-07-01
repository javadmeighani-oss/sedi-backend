"""Gate 3G — knowledge source fetch policy and ingestion review fields

Revision ID: 036_gate3g_kb_fetch_review
Revises: 035_health_symptom_reports
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "036_gate3g_kb_fetch_review"
down_revision: Union[str, None] = "035_health_symptom_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("source_fetch_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("knowledge_sources", sa.Column("allowed_domain", sa.String(length=256), nullable=True))
    op.add_column("knowledge_sources", sa.Column("allowed_url_patterns_json", sa.Text(), nullable=True))
    op.add_column(
        "knowledge_sources",
        sa.Column("fetch_method", sa.String(length=32), nullable=False, server_default="manual_upload"),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("auto_approve_low_risk", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("knowledge_sources", sa.Column("last_fetched_at", sa.DateTime(), nullable=True))
    op.add_column("knowledge_sources", sa.Column("last_changed_at", sa.DateTime(), nullable=True))
    op.add_column("knowledge_sources", sa.Column("last_approved_at", sa.DateTime(), nullable=True))
    op.add_column("knowledge_sources", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("knowledge_sources", sa.Column("crawl_policy_json", sa.Text(), nullable=True))
    op.add_column(
        "knowledge_sources",
        sa.Column("max_fetch_bytes", sa.Integer(), nullable=True, server_default="2097152"),
    )
    op.add_column("knowledge_sources", sa.Column("fetch_interval_hours", sa.Integer(), nullable=True))
    op.add_column("knowledge_sources", sa.Column("robots_checked_at", sa.DateTime(), nullable=True))
    op.add_column("knowledge_sources", sa.Column("robots_allowed", sa.Boolean(), nullable=True))

    op.add_column(
        "knowledge_ingestion_runs",
        sa.Column("run_type", sa.String(length=32), nullable=False, server_default="manual_upload"),
    )
    op.add_column("knowledge_ingestion_runs", sa.Column("fetch_url", sa.String(length=512), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("fetched_content_hash", sa.String(length=64), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("previous_content_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "knowledge_ingestion_runs",
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending_review"),
    )
    op.add_column("knowledge_ingestion_runs", sa.Column("fetched_at", sa.DateTime(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("approved_by", sa.String(length=64), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("rejected_reason", sa.Text(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("parser_type", sa.String(length=32), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("source_snapshot_json", sa.Text(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("extracted_text_preview", sa.Text(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("ai_review_status", sa.String(length=32), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("review_findings_json", sa.Text(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("source_quality_score", sa.Float(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("parse_quality_score", sa.Float(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("evidence_quality_score", sa.Float(), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("medical_risk_level", sa.String(length=16), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("psychological_risk_level", sa.String(length=16), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("advertising_risk_level", sa.String(length=16), nullable=True))
    op.add_column("knowledge_ingestion_runs", sa.Column("recommended_action", sa.String(length=32), nullable=True))
    op.add_column(
        "knowledge_ingestion_runs",
        sa.Column("requires_human_review", sa.Boolean(), nullable=True, server_default=sa.text("false")),
    )
    op.add_column(
        "knowledge_ingestion_runs",
        sa.Column("auto_approve_allowed", sa.Boolean(), nullable=True, server_default=sa.text("false")),
    )

    op.create_index(
        "ix_knowledge_ingestion_runs_review_status",
        "knowledge_ingestion_runs",
        ["review_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_ingestion_runs_review_status", table_name="knowledge_ingestion_runs")
    for col in (
        "auto_approve_allowed", "requires_human_review",
        "recommended_action", "advertising_risk_level", "psychological_risk_level", "medical_risk_level",
        "evidence_quality_score", "parse_quality_score", "source_quality_score", "review_findings_json",
        "ai_review_status", "extracted_text_preview", "source_snapshot_json", "parser_type", "rejected_reason",
        "approved_by", "approved_at", "fetched_at", "review_status", "previous_content_hash",
        "fetched_content_hash", "fetch_url", "run_type",
    ):
        op.drop_column("knowledge_ingestion_runs", col)
    for col in (
        "robots_allowed", "robots_checked_at", "fetch_interval_hours", "max_fetch_bytes", "crawl_policy_json",
        "content_hash", "last_approved_at", "last_changed_at", "last_fetched_at", "auto_approve_low_risk",
        "review_required", "fetch_method", "allowed_url_patterns_json", "allowed_domain", "source_fetch_enabled",
    ):
        op.drop_column("knowledge_sources", col)
