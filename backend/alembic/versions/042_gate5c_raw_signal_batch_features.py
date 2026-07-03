"""Gate 5-C — Raw signal batch technical feature extraction (non-diagnostic)

Revision ID: 042_gate5c_raw_signal_batch_features
Revises: 041_gate5b_raw_signal_batches

Adds raw_signal_batch_features for internal technical preprocessing results.
No clinical interpretation; one row per batch per processing_version.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "042_gate5c_raw_signal_batch_features"
down_revision: Union[str, None] = "041_gate5b_raw_signal_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB(astext_type=sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON()

    op.create_table(
        "raw_signal_batch_features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw_signal_batch_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hub_device_id", sa.Integer(), nullable=False),
        sa.Column("sensor_id", sa.Integer(), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("processing_version", sa.String(length=32), nullable=False),
        sa.Column("processing_status", sa.String(length=16), nullable=False),
        sa.Column("features_json", json_type, nullable=True),
        sa.Column("quality_json", json_type, nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["raw_signal_batch_id"],
            ["raw_signal_batches.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hub_device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sensor_id"], ["device_sensors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "raw_signal_batch_id",
            "processing_version",
            name="uq_raw_signal_batch_features_batch_version",
        ),
    )
    op.create_index(
        "ix_raw_signal_batch_features_status_created",
        "raw_signal_batch_features",
        ["processing_status", "created_at"],
    )
    op.create_index(
        "ix_raw_signal_batch_features_user_processed",
        "raw_signal_batch_features",
        ["user_id", "processed_at"],
    )
    op.create_index(
        "ix_raw_signal_batch_features_batch_version",
        "raw_signal_batch_features",
        ["raw_signal_batch_id", "processing_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_raw_signal_batch_features_batch_version", table_name="raw_signal_batch_features")
    op.drop_index("ix_raw_signal_batch_features_user_processed", table_name="raw_signal_batch_features")
    op.drop_index("ix_raw_signal_batch_features_status_created", table_name="raw_signal_batch_features")
    op.drop_table("raw_signal_batch_features")
