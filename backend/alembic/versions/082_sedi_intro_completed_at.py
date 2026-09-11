"""Add durable Sedi first-contact intro flag on users.

Revision ID: 082_sedi_intro_completed_at
Revises: 081_self_health_subject_1to1_hardening
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "082_sedi_intro_completed_at"
down_revision: Union[str, None] = "081_self_health_subject_1to1_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("sedi_intro_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "sedi_intro_completed_at")
