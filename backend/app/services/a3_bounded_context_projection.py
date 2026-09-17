"""Bounded I8/I9 projections for A3 Heart chat context — no plan/clinical authority.

Fail-open on errors. I6-honoring reads only via existing ownership/consent seams.
Never dump raw telemetry, MAD, or numeric HR interpretation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i9.device_reported_vital_status import (
    SOURCE_CLASS as DEVICE_REPORTED_SOURCE,
    get_effective_device_reported_vital_status,
)


def project_bounded_i8_actions(
    db: Session,
    user_id: int,
    *,
    today_local_date: Optional[str] = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Active/pending same-day governed I8 actions only — short semantic projection."""
    out: list[dict[str, Any]] = []
    try:
        if not today_local_date:
            return out
        from datetime import date as date_cls

        local_d = date_cls.fromisoformat(str(today_local_date))
        repo = I8OperationalRepository()
        plan = repo.get_active_plan(db, user_id=int(user_id), user_local_date=local_d)
        if plan is None:
            return out
        actions = repo.list_actions_for_plan(db, user_id=int(user_id), plan_id=int(plan.id))
        for act in actions:
            status = str(getattr(act, "status", "") or "")
            if status not in ("ACTIVE",):
                continue
            if str(getattr(act, "safety_state", "") or "") == "BLOCKED":
                continue
            summary = str(getattr(act, "summary_text", "") or "").strip()
            if not summary:
                continue
            out.append(
                {
                    "domain": str(getattr(act, "action_domain", "") or ""),
                    "status": status,
                    "local_date": str(plan.user_local_date),
                    "summary": summary[:160],
                }
            )
            if len(out) >= max(1, int(limit)):
                break
    except Exception:
        return []
    return out


def project_bounded_i9_facts(
    db: Session,
    user_id: int,
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Bounded DEVICE_REPORTED status + latest raw BPM observation only."""
    out: list[dict[str, Any]] = []
    try:
        from backend.app.services.i10.self_producer_adapter import (
            resolve_or_ensure_self_health_subject_id,
        )

        subject_id = resolve_or_ensure_self_health_subject_id(db, int(user_id))
        if subject_id is None:
            return out

        device_eff = get_effective_device_reported_vital_status(
            db, health_subject_id=int(subject_id)
        )
        if device_eff is not None and device_eff.status in ("STABLE", "UNSTABLE"):
            ts = device_eff.detected_at
            if ts is not None and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            out.append(
                {
                    "kind": "device_reported_vital_status",
                    "status": str(device_eff.status),
                    "source": DEVICE_REPORTED_SOURCE,
                    "observed_at": ts.isoformat() if ts else None,
                }
            )

        latest = (
            db.query(models.PhysiologicalMeasurement)
            .filter(
                models.PhysiologicalMeasurement.user_id == int(user_id),
                models.PhysiologicalMeasurement.measurement_type == "heart_rate",
                models.PhysiologicalMeasurement.ingestion_status == "accepted",
            )
            .order_by(models.PhysiologicalMeasurement.measured_at.desc())
            .first()
        )
        if latest is not None and latest.value is not None:
            measured = latest.measured_at
            if measured is not None and measured.tzinfo is None:
                measured = measured.replace(tzinfo=timezone.utc)
            out.append(
                {
                    "kind": "heart_rate_bpm",
                    "bpm": float(latest.value),
                    "observed_at": measured.isoformat() if measured else None,
                    "note": "raw_observed_only",
                }
            )
        return out[: max(1, int(limit))]
    except Exception:
        return []


def format_i8_context_block(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = ["[I8_BOUNDED_ACTIONS]"]
    for it in items:
        lines.append(
            f"- {it.get('domain','')}/{it.get('status','')} "
            f"({it.get('local_date','')}): {it.get('summary','')}"
        )
    lines.append("Chat is not plan authority; do not invent or complete plans here.")
    return "\n".join(lines)


def format_i9_context_block(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = ["[I9_BOUNDED_FACTS]"]
    for it in items:
        kind = it.get("kind")
        if kind == "device_reported_vital_status":
            lines.append(
                f"- DEVICE_REPORTED status={it.get('status')} "
                f"observed_at={it.get('observed_at')}"
            )
        elif kind == "heart_rate_bpm":
            lines.append(
                f"- heart_rate_bpm={it.get('bpm')} observed_at={it.get('observed_at')} (raw)"
            )
    lines.append(
        "No clinical interpretation. Do not derive thresholds, diagnosis, or risk."
    )
    return "\n".join(lines)
