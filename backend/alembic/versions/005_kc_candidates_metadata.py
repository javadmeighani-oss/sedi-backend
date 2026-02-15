"""kc_candidates_metadata (Conversation Extraction V1)

Revision ID: 005_kc_candidates_metadata
Revises: 004_knowledge_capture_v1
Create Date: 2025-02-15

Add metadata_json to kc_fact_candidates for needs_confirmation, source_message_id, etc.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_kc_candidates_metadata"
down_revision: Union[str, None] = "004_knowledge_capture_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kc_fact_candidates", sa.Column("metadata_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("kc_fact_candidates", "metadata_json")
