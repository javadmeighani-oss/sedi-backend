"""Gate 5-E — ML model registry and shadow inference foundation (non-diagnostic)

Revision ID: 043_gate5e_ml_shadow_foundation
Revises: 042_gate5c_raw_signal_batch_features

Adds ml_model_registry and ml_inference_records for internal/shadow ML outputs.
No clinical interpretation; user_visible defaults false; no automatic notifications.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "043_gate5e_ml_shadow_foundation"
down_revision: Union[str, None] = "042_gate5c_raw_signal_batch_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB(astext_type=sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON()

    op.create_table(
        "ml_model_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("signal_family", sa.String(length=64), nullable=False),
        sa.Column("input_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="research"),
        sa.Column("training_dataset", sa.String(length=255), nullable=True),
        sa.Column("metrics_json", json_type, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_name", "model_version", name="uq_ml_model_registry_name_version"),
    )
    op.create_index("ix_ml_model_registry_status", "ml_model_registry", ["status"])
    op.create_index("ix_ml_model_registry_signal_family", "ml_model_registry", ["signal_family"])

    op.create_table(
        "ml_inference_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("sensor_id", sa.Integer(), nullable=True),
        sa.Column("raw_signal_batch_id", sa.Integer(), nullable=True),
        sa.Column("raw_signal_batch_feature_id", sa.Integer(), nullable=True),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("output_type", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("features_summary_json", json_type, nullable=True),
        sa.Column("raw_output_json", json_type, nullable=True),
        sa.Column("safety_status", sa.String(length=32), nullable=False, server_default="shadow_only"),
        sa.Column("user_visible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sensor_id"], ["device_sensors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["raw_signal_batch_id"], ["raw_signal_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["raw_signal_batch_feature_id"],
            ["raw_signal_batch_features.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["model_id"], ["ml_model_registry.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ml_inference_records_user_created", "ml_inference_records", ["user_id", "created_at"])
    op.create_index("ix_ml_inference_records_model_id", "ml_inference_records", ["model_id"])
    op.create_index("ix_ml_inference_records_output_type", "ml_inference_records", ["output_type"])
    op.create_index(
        "ix_ml_inference_records_feature_id",
        "ml_inference_records",
        ["raw_signal_batch_feature_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ml_inference_records_feature_id", table_name="ml_inference_records")
    op.drop_index("ix_ml_inference_records_output_type", table_name="ml_inference_records")
    op.drop_index("ix_ml_inference_records_model_id", table_name="ml_inference_records")
    op.drop_index("ix_ml_inference_records_user_created", table_name="ml_inference_records")
    op.drop_table("ml_inference_records")
    op.drop_index("ix_ml_model_registry_signal_family", table_name="ml_model_registry")
    op.drop_index("ix_ml_model_registry_status", table_name="ml_model_registry")
    op.drop_table("ml_model_registry")
