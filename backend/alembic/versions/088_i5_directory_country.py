"""I5 directory: additive country column (default IR) for multi-country readiness.

Revision ID: 088_i5_directory_country
Revises: 087_a4_notification_inbox_visibility

SCHEMA ONLY. Adds country (ISO 3166-1 alpha-2) to iran_doctors / iran_laboratories /
iran_hospitals; every existing row becomes 'IR'. No seed, no network, no data change.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "088_i5_directory_country"
down_revision: Union[str, None] = "087_a4_notification_inbox_visibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    ("iran_doctors", "ix_iran_doctor_country"),
    ("iran_laboratories", "ix_iran_lab_country"),
    ("iran_hospitals", "ix_iran_hosp_country"),
)


def upgrade() -> None:
    for table, index in _TABLES:
        op.add_column(
            table,
            sa.Column("country", sa.String(length=2), nullable=False, server_default="IR"),
        )
        op.create_index(index, table, ["country"])


def downgrade() -> None:
    for table, index in reversed(_TABLES):
        op.drop_index(index, table_name=table)
        op.drop_column(table, "country")
