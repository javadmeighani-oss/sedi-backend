"""I5 directory: nullable public feedback aggregates on iran_doctors.

Revision ID: 089_i5_directory_doctor_feedback
Revises: 088_i5_directory_country

SCHEMA ONLY. rating_avg (0-5), rating_count, satisfaction_percent — exactly as published by the
source platform; never computed or inferred. Existing rows stay NULL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "089_i5_directory_doctor_feedback"
down_revision: Union[str, None] = "088_i5_directory_country"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("iran_doctors", sa.Column("rating_avg", sa.Float(), nullable=True))
    op.add_column("iran_doctors", sa.Column("rating_count", sa.Integer(), nullable=True))
    op.add_column("iran_doctors", sa.Column("satisfaction_percent", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("iran_doctors", "satisfaction_percent")
    op.drop_column("iran_doctors", "rating_count")
    op.drop_column("iran_doctors", "rating_avg")
