"""Safe scheduled KB fetch runner (Gate 3I-A).

This is disabled by default and must be explicitly enabled by environment variable:
  SEDI_KB_SCHEDULED_FETCH_ENABLED=true

V1 safety goals:
- Only fetch explicitly allowlisted sources (domain + non-empty URL patterns).
- Only fetch approved/active/trusted sources (no arbitrary URLs).
- No recursive crawling (single URL only; redirects validated).
- Always stage runs as pending_review; NEVER auto-approve/publish from scheduler.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate3.knowledge_update_service import KnowledgeUpdateService


def scheduled_fetch_enabled() -> bool:
    return os.environ.get("SEDI_KB_SCHEDULED_FETCH_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


V1_ALLOWED_CATEGORIES = frozenset({
    "sleep",
    "nutrition",
    "exercise",
    "lifestyle",
    "stress_management",
    "daily_routine",
    "self_care",
})

# Conservative mapping for legacy/internal category names (do NOT broaden silently).
_CATEGORY_ALIASES = {
    "daily_planning": "daily_routine",
}

V1_BLOCKED_CATEGORIES = frozenset({
    "medication_education",
    "medical_condition",
    "clinical_guideline",
    "emergency_education",
    "mental_wellbeing",
    "mental_health_sensitive",
    "provider_directory",
    "lab_directory",
    "local_services",
    "health_care",
    "insurance",
    "appointment",
})

V1_ALLOWED_TRUST_LEVELS = frozenset({
    "official",
    # "clinical_guideline" is intentionally not enabled for scheduled V1 batches by default.
    # "vetted_partner" deferred until explicitly reviewed.
})


def _norm_category(cat: str | None) -> str:
    c = (cat or "").strip()
    if not c:
        return "other"
    return _CATEGORY_ALIASES.get(c, c)


def _patterns_non_empty(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        val = json.loads(raw)
    except Exception:
        return False
    return isinstance(val, list) and any(isinstance(x, str) and x.strip() for x in val)


def _is_due(src: models.KnowledgeSource, now: datetime) -> bool:
    # If never fetched, it is due (first scheduled run).
    if src.last_fetched_at is None:
        return True
    last = src.last_fetched_at
    interval_hours: Optional[int] = None
    if src.fetch_interval_hours:
        interval_hours = int(src.fetch_interval_hours)
    elif src.freshness_policy_days:
        interval_hours = int(src.freshness_policy_days) * 24
    if not interval_hours or interval_hours <= 0:
        return False
    return (now - last) >= timedelta(hours=interval_hours)


def select_due_sources(db: Session, *, now: Optional[datetime] = None, limit: int = 1) -> list[models.KnowledgeSource]:
    """Return due sources eligible for scheduled fetch (V1 strict)."""
    now = now or datetime.utcnow()

    rows: Sequence[models.KnowledgeSource] = (
        db.query(models.KnowledgeSource)
        .filter(models.KnowledgeSource.source_fetch_enabled.is_(True))
        .filter(models.KnowledgeSource.ingestion_status == "active")
        .order_by(models.KnowledgeSource.id.asc())
        .all()
    )

    out: list[models.KnowledgeSource] = []
    for src in rows:
        # Trust gate
        if (src.trust_level or "").strip() not in V1_ALLOWED_TRUST_LEVELS:
            continue

        # Category gate (conservative mapping)
        cat = _norm_category(src.category)
        if cat in V1_BLOCKED_CATEGORIES:
            continue
        if cat not in V1_ALLOWED_CATEGORIES:
            continue

        # V1 policy: always human review, never auto-approve
        if not src.review_required:
            continue
        if src.auto_approve_low_risk:
            continue

        # URL allowlist policy: domain + non-empty patterns required
        if not (src.allowed_domain or "").strip():
            continue
        if not _patterns_non_empty(src.allowed_url_patterns_json):
            continue

        # Fetch method must be URL fetch
        if (src.fetch_method or "").strip() != "url_fetch":
            continue

        # Avoid overlapping runs: skip if there is a running run for this source
        running = (
            db.query(models.KnowledgeIngestionRun)
            .filter(models.KnowledgeIngestionRun.source_id == src.id)
            .filter(models.KnowledgeIngestionRun.status == "running")
            .first()
        )
        if running:
            continue

        # Due gate
        if not _is_due(src, now):
            continue

        out.append(src)
        if len(out) >= max(0, int(limit)):
            break
    return out


def run_scheduled_kb_fetch(db: Session) -> Optional[dict]:
    """
    Run a single scheduled KB tick.
    - Does nothing unless SEDI_KB_SCHEDULED_FETCH_ENABLED is set.
    - Creates ingestion runs (pending_review) but never publishes.
    """
    if not scheduled_fetch_enabled():
        return None

    now = datetime.utcnow()
    max_per_tick = _int_env("SEDI_KB_SCHEDULED_FETCH_MAX_PER_TICK", 1)
    max_per_tick = max(0, min(20, max_per_tick))

    due = select_due_sources(db, now=now, limit=max_per_tick)
    if not due:
        return {"status": "ok", "attempted": 0, "fetched": 0, "skipped": 0}

    service = KnowledgeUpdateService()
    attempted = 0
    fetched = 0
    skipped = 0
    created_run_ids: list[int] = []

    for src in due:
        attempted += 1
        try:
            out = service.fetch_source(
                db,
                src.id,
                run_by="scheduler",
                fetch_url=None,
                run_type="scheduled_fetch",
            )
            fetched += 1
            created_run_ids.append(int(out["id"]))
        except Exception:
            # Fail safe: skip erroring sources; do not raise to scheduler loop.
            skipped += 1
            continue

    return {
        "status": "ok",
        "attempted": attempted,
        "fetched": fetched,
        "skipped": skipped,
        "run_ids": created_run_ids,
    }
