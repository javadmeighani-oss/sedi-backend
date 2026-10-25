"""I7 active memory: user_attachments (documents/images/audio given from the chat box).

Revision ID: 090_i7_user_attachments
Revises: 089_i5_directory_doctor_feedback

ADDITIVE ONLY: one new table + indexes. No existing table or column is touched; downgrade drops only this table.
Files are stored in PostgreSQL (bytea) behind an AttachmentStore interface (size-capped in code); the upload feature
itself stays OFF until SEDI_ATTACHMENTS_ENABLED is set.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "090_i7_user_attachments"
down_revision: Union[str, None] = "089_i5_directory_doctor_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("mime", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="stored"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("extracted_json", sa.Text(), nullable=True),
        sa.Column("confirmed_event_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "sha256", name="uq_user_attachments_user_sha"),
    )
    op.create_index("ix_user_attachments_id", "user_attachments", ["id"])
    op.create_index("ix_user_attachments_user_created", "user_attachments", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_attachments_user_created", table_name="user_attachments")
    op.drop_index("ix_user_attachments_id", table_name="user_attachments")
    op.drop_table("user_attachments")
