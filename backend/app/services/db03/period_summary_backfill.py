"""daily_memory_summaries → user_period_summaries DAILY version=1 (§270.R).

Uses explicit SQL for the 058-era column set so Wave-2 ORM columns do not break
mid-chain Alembic backfill (059) before migration 068 exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import models


@dataclass
class PeriodBackfillCounts:
    source_rows_expected: int = 0
    mapped_rows: int = 0
    conflict_rows: int = 0
    unmapped_rows: int = 0

    @property
    def unexplained_data_loss(self) -> int:
        accounted = self.mapped_rows + self.conflict_rows + self.unmapped_rows
        return max(0, self.source_rows_expected - accounted)


_INSERT_UPS_058 = text(
    """
    INSERT INTO user_period_summaries (
        user_id, summary_type, period_start, period_end, version,
        structured_summary_json, narrative_summary, evidence_range,
        generated_at, status
    ) VALUES (
        :user_id, 'DAILY', :period_start, :period_end, 1,
        :structured_summary_json, :narrative_summary, :evidence_range,
        :generated_at, 'active'
    )
    """
)

_EXISTS_UPS = text(
    """
    SELECT id FROM user_period_summaries
    WHERE user_id = :user_id
      AND summary_type = 'DAILY'
      AND period_start = :period_start
      AND version = 1
    LIMIT 1
    """
)


def _period_start_utc(created: datetime) -> datetime:
    if created.tzinfo is None:
        base = created.replace(tzinfo=timezone.utc)
    else:
        base = created.astimezone(timezone.utc)
    return base.replace(hour=0, minute=0, second=0, microsecond=0)


def backfill_daily_memory_summaries(db: Session) -> PeriodBackfillCounts:
    counts = PeriodBackfillCounts()
    rows = db.query(models.DailyMemorySummary).order_by(models.DailyMemorySummary.id).all()
    counts.source_rows_expected = len(rows)

    for row in rows:
        try:
            # SAVEPOINT so a single-row failure cannot abort Alembic's outer txn.
            with db.begin_nested():
                created = row.created_at or datetime.now(timezone.utc)
                period_start = _period_start_utc(created)
                period_end = period_start.replace(hour=23, minute=59, second=59)

                existing = db.execute(
                    _EXISTS_UPS,
                    {"user_id": row.user_id, "period_start": period_start},
                ).first()
                if existing:
                    counts.conflict_rows += 1
                    continue

                structured = {
                    "legacy_daily_memory_summary_id": row.id,
                    "mood": row.mood,
                    "context": row.context,
                    "last_interaction": (
                        row.last_interaction.isoformat() if row.last_interaction else None
                    ),
                }
                generated_at = (
                    created if created.tzinfo else created.replace(tzinfo=timezone.utc)
                )
                db.execute(
                    _INSERT_UPS_058,
                    {
                        "user_id": row.user_id,
                        "period_start": period_start,
                        "period_end": period_end,
                        "structured_summary_json": json.dumps(structured),
                        "narrative_summary": row.summary,
                        "evidence_range": json.dumps(
                            {"source": "daily_memory_summaries", "id": row.id}
                        ),
                        "generated_at": generated_at,
                    },
                )
                counts.mapped_rows += 1
        except IntegrityError:
            counts.conflict_rows += 1
        except Exception:  # noqa: BLE001
            counts.unmapped_rows += 1

    db.flush()
    return counts
