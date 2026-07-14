"""Gate 4C / Section 15-B8 — interaction_events notification chat idempotency

Revision ID: 050_gate4_event_idem
Revises: 049_section10_kb_embeddings_memory_governance

Invariant (product):
  For authenticated owner + event_type='chat_message' + non-null
  source_notification_id, at most ONE interaction_events row may exist.

conversation_id is intentionally NOT part of the unique key:
  - PostgreSQL UNIQUE treats NULL as distinct, so NULL vs non-NULL
    conversation_id pairs could otherwise reopen consumption.
  - A changed conversation_id must not create a second consumption.
  - Frontend clears pending launch after the first successful turn and
    later legal turns omit source_notification_id.

Duplicate cleanup is NOT automatic/destructive. If duplicates already
exist, upgrade fails closed and requires explicit production approval
plus a separate cleanup package before retrying.

Partial unique index is created on PostgreSQL only (matches repo pattern
in 040_gate5a_hub_sensor_status). Non-Postgres environments rely on
service-layer select-before-insert + savepoint recovery.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "050_gate4_event_idem"
down_revision: Union[str, None] = "049_section10_kb_embeddings_memory_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_interaction_events_notif_chat_once"


def _raise_if_duplicates(bind) -> None:
    """Fail closed when duplicate candidate keys already exist (no silent deletes)."""
    rows = bind.execute(
        sa.text(
            """
            SELECT user_id,
                   source_notification_id,
                   COUNT(*) AS duplicate_count,
                   MIN(id) AS earliest_event_id,
                   MAX(id) AS latest_event_id
            FROM interaction_events
            WHERE event_type = 'chat_message'
              AND source_notification_id IS NOT NULL
            GROUP BY user_id, source_notification_id
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC, user_id ASC, source_notification_id ASC
            """
        )
    ).fetchall()
    if not rows:
        return
    sample = ", ".join(
        f"(user_id={r[0]}, source_notification_id={r[1]}, count={r[2]}, "
        f"earliest_id={r[3]}, latest_id={r[4]})"
        for r in rows[:10]
    )
    raise RuntimeError(
        "Refusing to create "
        f"{INDEX_NAME}: found {len(rows)} duplicate "
        "notification chat_message consumption key(s). "
        "No audit rows were deleted. Obtain explicit production cleanup "
        "approval, then re-run. Sample: "
        f"{sample}"
    )


def upgrade() -> None:
    bind = op.get_bind()
    _raise_if_duplicates(bind)

    if bind.dialect.name != "postgresql":
        # Match existing migration style: partial unique indexes are PostgreSQL.
        return

    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
            ON interaction_events (user_id, source_notification_id)
            WHERE event_type = 'chat_message'
              AND source_notification_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP INDEX IF EXISTS {INDEX_NAME}"))
