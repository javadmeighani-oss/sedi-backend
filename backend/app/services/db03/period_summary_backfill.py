"""daily_memory_summaries → user_period_summaries DAILY version=1 (§270.R)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

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


def backfill_daily_memory_summaries(db: Session) -> PeriodBackfillCounts:
    counts = PeriodBackfillCounts()
    rows = db.query(models.DailyMemorySummary).order_by(models.DailyMemorySummary.id).all()
    counts.source_rows_expected = len(rows)

    for row in rows:
        try:
            created = row.created_at or datetime.now(timezone.utc)
            if created.tzinfo is None:
                period_start = created.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                period_start = created.astimezone(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            period_end = period_start.replace(hour=23, minute=59, second=59)

            existing = (
                db.query(models.UserPeriodSummary)
                .filter(
                    models.UserPeriodSummary.user_id == row.user_id,
                    models.UserPeriodSummary.summary_type == "DAILY",
                    models.UserPeriodSummary.period_start == period_start,
                    models.UserPeriodSummary.version == 1,
                )
                .first()
            )
            if existing:
                counts.conflict_rows += 1
                continue

            structured = {
                "legacy_daily_memory_summary_id": row.id,
                "mood": row.mood,
                "context": row.context,
                "last_interaction": row.last_interaction.isoformat() if row.last_interaction else None,
            }
            db.add(
                models.UserPeriodSummary(
                    user_id=row.user_id,
                    summary_type="DAILY",
                    period_start=period_start,
                    period_end=period_end,
                    version=1,
                    structured_summary_json=json.dumps(structured),
                    narrative_summary=row.summary,
                    evidence_range=json.dumps({"source": "daily_memory_summaries", "id": row.id}),
                    generated_at=created if created.tzinfo else created.replace(tzinfo=timezone.utc),
                    status="active",
                )
            )
            counts.mapped_rows += 1
        except Exception:  # noqa: BLE001
            counts.unmapped_rows += 1

    db.flush()
    return counts
