"""Gate 5-A — Gadget Hub status fields + device_sensors registry

Revision ID: 040_gate5a_hub_sensor_status
Revises: 039_gate4b_notification_context_fields

Extends devices for Gadget Hub metadata. Adds device_sensors for hub-reported sensors.

One active gadget_hub per user: partial unique index on PostgreSQL when safe;
service layer also enforces (see gadget_hub_status.find_active_gadget_hub_for_user).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "040_gate5a_hub_sensor_status"
down_revision: Union[str, None] = "039_gate4b_notification_context_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("battery_level", sa.Float(), nullable=True))
    op.add_column("devices", sa.Column("firmware_version", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("hardware_version", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("hub_status", sa.String(length=32), nullable=True))
    op.add_column("devices", sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True))
    op.add_column("devices", sa.Column("last_sync_at", sa.DateTime(), nullable=True))

    op.create_table(
        "device_sensors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hub_device_id", sa.Integer(), nullable=False),
        sa.Column("sensor_key", sa.String(length=255), nullable=False),
        sa.Column("sensor_type", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("connection_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("capabilities_json", sa.Text(), nullable=True),
        sa.Column("battery_level", sa.Float(), nullable=True),
        sa.Column("firmware_version", sa.String(length=64), nullable=True),
        sa.Column("hardware_version", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_signal_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["hub_device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hub_device_id", "sensor_key", name="uq_device_sensors_hub_sensor_key"),
    )
    op.create_index("ix_device_sensors_hub_device_id", "device_sensors", ["hub_device_id"])
    op.create_index("ix_device_sensors_sensor_key", "device_sensors", ["sensor_key"])

    # Partial unique: one active gadget_hub per user (PostgreSQL).
    # TODO: SQLite/test DBs without partial indexes rely on service-layer enforcement.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_one_active_gadget_hub_per_user
            ON devices (user_id)
            WHERE device_type = 'gadget_hub' AND status = 'active' AND revoked_at IS NULL
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_devices_one_active_gadget_hub_per_user")

    op.drop_index("ix_device_sensors_sensor_key", table_name="device_sensors")
    op.drop_index("ix_device_sensors_hub_device_id", table_name="device_sensors")
    op.drop_table("device_sensors")

    op.drop_column("devices", "last_sync_at")
    op.drop_column("devices", "last_heartbeat_at")
    op.drop_column("devices", "hub_status")
    op.drop_column("devices", "hardware_version")
    op.drop_column("devices", "firmware_version")
    op.drop_column("devices", "battery_level")
