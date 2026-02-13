"""phone_otp_auth (Stage 25)

Revision ID: 002_phone_otp
Revises: 001_baseline_v1
Create Date: 2025-02-13

Stage 25 Step 1: Phone OTP auth – users.phone, otp_codes, refresh_tokens.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_phone_otp"
down_revision: Union[str, None] = "001_baseline_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add users.phone (unique, nullable for legacy)
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_users_phone"), "users", ["phone"], unique=True)

    # otp_codes
    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sent_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_otp_codes_id"), "otp_codes", ["id"], unique=False)
    op.create_index(op.f("ix_otp_codes_phone"), "otp_codes", ["phone"], unique=False)

    # refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("device_info", sa.String(length=512), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_refresh_tokens_id"), "refresh_tokens", ["id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_otp_codes_phone"), table_name="otp_codes")
    op.drop_index(op.f("ix_otp_codes_id"), table_name="otp_codes")
    op.drop_table("otp_codes")
    op.drop_index(op.f("ix_users_phone"), table_name="users")
    op.drop_column("users", "phone")
