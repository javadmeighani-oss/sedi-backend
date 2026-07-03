"""Gate 5-B — Raw heart/ECG signal batch store (append-only)

Revision ID: 041_gate5b_raw_signal_batches
Revises: 040_gate5a_hub_sensor_status

Adds raw_signal_batches for store-only Gadget Hub raw signal ingestion.
No clinical interpretation; append-only (no updated_at).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "041_gate5b_raw_signal_batches"
down_revision: Union[str, None] = "040_gate5a_hub_sensor_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB(astext_type=sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON()

    op.create_table(
        "raw_signal_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hub_device_id", sa.Integer(), nullable=False),
        sa.Column("hub_device_id_str", sa.String(length=255), nullable=False),
        sa.Column("sensor_id", sa.Integer(), nullable=False),
        sa.Column("sensor_key", sa.String(length=255), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("sample_rate_hz", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("samples_json", json_type, nullable=False),
        sa.Column("metadata_json", json_type, nullable=True),
        sa.Column("quality_metadata_json", json_type, nullable=True),
        sa.Column("client_batch_id", sa.String(length=128), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("storage_backend", sa.String(length=16), nullable=False, server_default="postgres_json"),
        sa.Column("object_storage_key", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hub_device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sensor_id"], ["device_sensors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_raw_signal_batches_dedupe_key"),
    )
    op.create_index("ix_raw_signal_batches_user_received", "raw_signal_batches", ["user_id", "received_at"])
    op.create_index(
        "ix_raw_signal_batches_hub_sensor_started",
        "raw_signal_batches",
        ["hub_device_id", "sensor_key", "started_at"],
    )
    op.create_index(
        "ix_raw_signal_batches_client_batch_hub",
        "raw_signal_batches",
        ["client_batch_id", "hub_device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_raw_signal_batches_client_batch_hub", table_name="raw_signal_batches")
    op.drop_index("ix_raw_signal_batches_hub_sensor_started", table_name="raw_signal_batches")
    op.drop_index("ix_raw_signal_batches_user_received", table_name="raw_signal_batches")
    op.drop_table("raw_signal_batches")
