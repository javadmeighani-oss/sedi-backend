"""SELF HealthSubject 1:1 hardening — active SELF uniqueness.

Revision ID: 081_self_health_subject_1to1_hardening
Revises: 080_i9_device_reported_vital_status

Partial unique indexes only for EFFECTIVE ACTIVE SELF.
Does not constrain MANAGED (linked_user_id NULL) or inactive SELF.
Fail-closed: upgrade aborts if duplicate effective SELF rows exist.
No auto-delete / auto-merge / substitution.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "081_self_health_subject_1to1_hardening"
down_revision: Union[str, None] = "080_i9_device_reported_vital_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IDX_HS = "uq_health_subjects_active_self_linked_user"
IDX_AHSA = "uq_ahsa_active_self_account"


def _fail_on_duplicate_active_self_subjects() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            """
            SELECT linked_user_id, COUNT(*) AS n
            FROM health_subjects
            WHERE subject_kind = 'self'
              AND status = 'active'
              AND linked_user_id IS NOT NULL
            GROUP BY linked_user_id
            HAVING COUNT(*) > 1
            ORDER BY linked_user_id
            LIMIT 20
            """
        )
    ).fetchall()
    if rows:
        masked = ", ".join(f"linked_user_id={r[0]} count={r[1]}" for r in rows)
        raise RuntimeError(
            "SELF_1TO1_HARDENING_BLOCKED: duplicate active SELF HealthSubject rows "
            f"(no auto-delete/merge). samples=[{masked}]"
        )


def _fail_on_duplicate_active_self_ahsa() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            """
            SELECT account_user_id, COUNT(*) AS n
            FROM account_health_subject_access
            WHERE access_role = 'SELF'
              AND is_active IS TRUE
              AND revoked_at IS NULL
            GROUP BY account_user_id
            HAVING COUNT(*) > 1
            ORDER BY account_user_id
            LIMIT 20
            """
        )
    ).fetchall()
    if rows:
        masked = ", ".join(f"account_user_id={r[0]} count={r[1]}" for r in rows)
        raise RuntimeError(
            "SELF_1TO1_HARDENING_BLOCKED: duplicate effective active SELF AHSA rows "
            f"(no auto-delete/merge). samples=[{masked}]"
        )


def upgrade() -> None:
    _fail_on_duplicate_active_self_subjects()
    _fail_on_duplicate_active_self_ahsa()

    op.execute(
        f"""
CREATE UNIQUE INDEX {IDX_HS}
ON health_subjects (linked_user_id)
WHERE subject_kind = 'self'
  AND status = 'active'
  AND linked_user_id IS NOT NULL;
"""
    )
    op.execute(
        f"""
CREATE UNIQUE INDEX {IDX_AHSA}
ON account_health_subject_access (account_user_id)
WHERE access_role = 'SELF'
  AND is_active IS TRUE
  AND revoked_at IS NULL;
"""
    )
    op.execute(
        f"""
COMMENT ON INDEX {IDX_HS} IS
'G1: one effective active SELF HealthSubject per Account (linked_user_id)';
"""
    )
    op.execute(
        f"""
COMMENT ON INDEX {IDX_AHSA} IS
'G1: one effective active SELF AHSA per Account';
"""
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {IDX_AHSA};")
    op.execute(f"DROP INDEX IF EXISTS {IDX_HS};")
