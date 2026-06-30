"""Gate 2 optional backfill: goals_json -> user_goals, constraints_json -> user_restrictions

Revision ID: 026_gate2_legacy_backfill_optional
Revises: 025_user_care_plan_items
"""
import json
from typing import List, Optional, Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "026_gate2_legacy_backfill_optional"
down_revision: Union[str, None] = "025_user_care_plan_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _parse_json_list(raw: Optional[str]) -> List[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [str(raw).strip()] if str(raw).strip() else []
    if isinstance(data, list):
        return [str(x).strip() for x in data if x and str(x).strip()]
    if isinstance(data, str) and data.strip():
        return [data.strip()]
    return []


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            "SELECT user_id, goals_json, constraints_json FROM user_profile_knowledge "
            "WHERE goals_json IS NOT NULL OR constraints_json IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        user_id = row[0]
        for goal_title in _parse_json_list(row[1]):
            exists = conn.execute(
                text(
                    "SELECT 1 FROM user_goals WHERE user_id = :uid AND title = :title "
                    "AND (valid_to IS NULL) LIMIT 1"
                ),
                {"uid": user_id, "title": goal_title[:256]},
            ).first()
            if exists:
                continue
            conn.execute(
                text(
                    "INSERT INTO user_goals (user_id, category, title, status, source, created_at, updated_at) "
                    "VALUES (:uid, 'lifestyle', :title, 'active', 'system', now(), now())"
                ),
                {"uid": user_id, "title": goal_title[:256]},
            )
        for constraint_title in _parse_json_list(row[2]):
            exists = conn.execute(
                text(
                    "SELECT 1 FROM user_restrictions WHERE user_id = :uid AND title = :title "
                    "AND (valid_to IS NULL) LIMIT 1"
                ),
                {"uid": user_id, "title": constraint_title[:256]},
            ).first()
            if exists:
                continue
            conn.execute(
                text(
                    "INSERT INTO user_restrictions (user_id, restriction_type, title, status, source, created_at, updated_at) "
                    "VALUES (:uid, 'other', :title, 'active', 'system', now(), now())"
                ),
                {"uid": user_id, "title": constraint_title[:256]},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM user_goals WHERE source = 'system'"))
    conn.execute(text("DELETE FROM user_restrictions WHERE source = 'system' AND restriction_type = 'other'"))
