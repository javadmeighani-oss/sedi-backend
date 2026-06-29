"""device subject_user_id (Gate 1 gadget prep)

Revision ID: 018_device_subject_user
Revises: 017_user_care_relationships
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "018_device_subject_user"
down_revision: Union[str, None] = "017_user_care_relationships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("subject_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_devices_subject_user_id_users",
        "devices",
        "users",
        ["subject_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_devices_subject_user_id", "devices", ["subject_user_id"])
    # Backfill: subject is the registering owner
    op.execute("UPDATE devices SET subject_user_id = user_id WHERE subject_user_id IS NULL")


def downgrade() -> None:
    op.drop_index("ix_devices_subject_user_id", table_name="devices")
    op.drop_constraint("fk_devices_subject_user_id_users", "devices", type_="foreignkey")
    op.drop_column("devices", "subject_user_id")
