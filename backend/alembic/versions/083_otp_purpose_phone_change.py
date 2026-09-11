"""Add OTP purpose + optional account binding for phone-change.

Revision ID: 083_otp_purpose_phone_change
Revises: 082_sedi_intro_completed_at
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "083_otp_purpose_phone_change"
down_revision: Union[str, None] = "082_sedi_intro_completed_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "otp_codes",
        sa.Column(
            "purpose",
            sa.String(length=32),
            nullable=False,
            server_default="LOGIN",
        ),
    )
    op.add_column(
        "otp_codes",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_otp_codes_user_id_users",
        "otp_codes",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_otp_codes_purpose", "otp_codes", ["purpose"], unique=False)
    op.create_index("ix_otp_codes_user_id", "otp_codes", ["user_id"], unique=False)
    op.create_index(
        "ix_otp_codes_phone_purpose_user",
        "otp_codes",
        ["phone", "purpose", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_otp_codes_phone_purpose_user", table_name="otp_codes")
    op.drop_index("ix_otp_codes_user_id", table_name="otp_codes")
    op.drop_index("ix_otp_codes_purpose", table_name="otp_codes")
    op.drop_constraint("fk_otp_codes_user_id_users", "otp_codes", type_="foreignkey")
    op.drop_column("otp_codes", "user_id")
    op.drop_column("otp_codes", "purpose")
