"""Device category/label + setup-code authority columns.

Revision ID: 084_device_category_setup_code_authority
Revises: 083_otp_purpose_phone_change
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "084_device_category_setup_code_authority"
down_revision: Union[str, None] = "083_otp_purpose_phone_change"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("device_category", sa.String(length=16), nullable=True))
    op.add_column("devices", sa.Column("user_label", sa.String(length=80), nullable=True))
    op.add_column("devices", sa.Column("setup_code_verifier", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("setup_code_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("setup_code_version", sa.SmallInteger(), nullable=True))
    op.add_column(
        "devices",
        sa.Column(
            "setup_code_failed_attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "devices",
        sa.Column("setup_code_failure_window_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("setup_code_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_devices_device_category",
        "devices",
        "device_category IS NULL OR device_category IN ('SELF', 'OTHER')",
    )
    op.create_check_constraint(
        "ck_devices_setup_code_failed_attempts_nonneg",
        "devices",
        "setup_code_failed_attempts >= 0",
    )
    op.create_index(
        "uq_devices_setup_code_fingerprint",
        "devices",
        ["setup_code_fingerprint"],
        unique=True,
        postgresql_where=sa.text("setup_code_fingerprint IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_devices_setup_code_fingerprint",
        table_name="devices",
        postgresql_where=sa.text("setup_code_fingerprint IS NOT NULL"),
    )
    op.drop_constraint("ck_devices_setup_code_failed_attempts_nonneg", "devices", type_="check")
    op.drop_constraint("ck_devices_device_category", "devices", type_="check")
    op.drop_column("devices", "setup_code_locked_until")
    op.drop_column("devices", "setup_code_failure_window_started_at")
    op.drop_column("devices", "setup_code_failed_attempts")
    op.drop_column("devices", "setup_code_version")
    op.drop_column("devices", "setup_code_fingerprint")
    op.drop_column("devices", "setup_code_verifier")
    op.drop_column("devices", "user_label")
    op.drop_column("devices", "device_category")
