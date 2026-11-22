"""R-108 / R-074 step 2 - the ONE typed read contract for «what is going on in this user's care right now» (the care view of Sedi's brain).

The brain is three stores read through different owners: I6 facts (complaints, episodes), I10 (follow-up chains, the done / not-done
ledger) and the user's events (appointments) + medicines. Before this module every consumer re-counted and re-interpreted them
(``journey._journey_open``, ``guide.open_care_follow_ups``, the status report ...), so chat, notifications and reports could disagree
(chat says «nothing is wrong» while an acute follow-up is open).

``CareState`` is the deterministic, frozen, read-only view they share (the sibling of ``UserState`` for «who is this user»):
  * built ONLY through the owners that hold the data (``i6.memory_writes`` consent-gated reader, ``i10.commitment_followup`` public
    reads, ``UserEvent``, ``user_medication_service``) - no new store, no schema, no write path;
  * memory-read consent gates everything (no consent -> an empty state, nothing read);
  * fail-open per section; ``get_care_state`` returns None only when nothing at all could be read.
A guard test lists the consumers; new code that needs the care picture uses ``get_care_state`` / ``summary_line``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from backend.app import sedi_copy

logger = logging.getLogger(__name__)

MAX_EVENTS = 3
RESOLVED_WINDOW = timedelta(days=7)
_STATUS_NOTE_KEYS = {"better": "journey.status_note.better", "worse": "journey.status_note.worse"}
_LANGS = ("fa", "ar", "en")


@dataclass(frozen=True)
class CareIssue:
    text: str
    status: str = "open"  # open | better | worse (from the user's own later «it got better / worse»)


@dataclass(frozen=True)
class CareFollowUp:
    kind: str  # journey | commitment
    tier: Optional[str] = None  # acute | soon | routine (journey only)
    next_due: Optional[datetime] = None  # naive UTC
    attempt: int = 1


@dataclass(frozen=True)
class CareEvent:
    title: str
    starts_at: datetime


@dataclass(frozen=True)
class CareState:
    user_id: int
    consent: bool = True
    issues: tuple[CareIssue, ...] = ()
    follow_ups: tuple[CareFollowUp, ...] = ()
    events: tuple[CareEvent, ...] = ()
    medications: int = 0
    resolved_recent: int = 0

    @property
    def has_open_journey(self) -> bool:
        return any(f.kind == "journey" for f in self.follow_ups)

    @property
    def is_acute(self) -> bool:
        return any(f.kind == "journey" and f.tier == "acute" for f in self.follow_ups)

    @property
    def is_empty(self) -> bool:
        return not (self.issues or self.follow_ups or self.events or self.medications or self.resolved_recent)


def _clip(text: Any, limit: int = 90) -> str:
    return " ".join(str(text or "").split())[:limit].strip()


def _status_of(note: str) -> Optional[str]:
    """«better» / «worse» when ``note`` is one of the catalog status notes the care journey writes (any language)."""
    flat = _clip(note, 200)
    for status, key in _STATUS_NOTE_KEYS.items():
        for lang in _LANGS:
            base = _clip(sedi_copy.t(key, lang), 200)
            if flat == base or flat.startswith(base + " ·"):  # the journey writes «note · YYYY-MM-DD»
                return status
    return None


def _items(value: Any) -> list[str]:
    raw = list(value) if isinstance(value, (list, tuple)) else ([value] if isinstance(value, str) and value.strip() else [])
    return [t for t in (_clip(i) for i in raw) if t]


def _issues(db: Any, user_id: int) -> tuple[CareIssue, ...]:
    """The user's primary open complaint: the stated concern (else the newest episode) and where it stands now."""
    try:
        from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty

        concerns: list[str] = []
        episodes: list[str] = []
        for row in list_facts_readonly_or_empty(db, user_id) or []:
            if (row.domain, row.key) not in (("medical", "health_concerns"), ("medical", "symptom_episodes")):
                continue
            try:
                value = json.loads(row.value_json)
            except Exception:  # noqa: BLE001
                continue
            (concerns if row.key == "health_concerns" else episodes).extend(_items(value))
        status = "open"
        story: list[str] = []
        for note in episodes:  # chronological: a status note describes the story BEFORE it; a later story line starts «open» again
            marked = _status_of(note)
            if marked:
                if story or concerns:  # the stated concern is the story the note is about
                    status = marked
            else:
                story.append(note)
                status = "open"  # a new statement is not yet reported better/worse (Codex P2, PR 202)
        text = concerns[0] if concerns else (story[-1] if story else "")
        return (CareIssue(text=text, status=status),) if text else ()
    except Exception:  # noqa: BLE001
        logger.exception("[R-108] care issues not read")
        return ()


def _follow_ups(db: Any, user_id: int) -> tuple[CareFollowUp, ...]:
    try:
        from backend.app.services.i10 import commitment_followup as cf

        rows = cf.open_follow_ups(db, user_id)
        return tuple(
            CareFollowUp(kind=r["kind"], tier=r.get("tier"), next_due=r.get("due_at"), attempt=int(r.get("attempt") or 1)) for r in rows
        )
    except Exception:  # noqa: BLE001
        return ()


def _events(db: Any, user_id: int, now: datetime) -> tuple[CareEvent, ...]:
    try:
        from backend.app import models

        rows = (
            db.query(models.UserEvent)
            .filter(models.UserEvent.user_id == user_id, models.UserEvent.status == "scheduled", models.UserEvent.starts_at >= now)
            .order_by(models.UserEvent.starts_at.asc())
            .limit(MAX_EVENTS)
            .all()
        )
        return tuple(CareEvent(title=_clip(r.title, 80), starts_at=r.starts_at) for r in rows if _clip(r.title, 80))
    except Exception:  # noqa: BLE001
        return ()


def _medications(db: Any, user_id: int) -> int:
    try:
        from backend.app.services.user_medication_service import list_user_medications

        return len(list_user_medications(db, user_id))
    except Exception:  # noqa: BLE001
        return 0


def _resolved(db: Any, user_id: int, now: datetime) -> int:
    try:
        from backend.app.services.i10 import commitment_followup as cf

        return int(cf.resolved_journeys_since(db, user_id, now - RESOLVED_WINDOW))
    except Exception:  # noqa: BLE001
        return 0


def _has_read_consent(db: Any, user_id: int) -> bool:
    try:
        from backend.app.services.i6.consent_service import PERM_READ, has_permission_readonly

        return bool(has_permission_readonly(db, user_id, PERM_READ))
    except Exception:  # noqa: BLE001
        return False


def get_care_state(db: Any, user_id: int, *, now: Optional[datetime] = None) -> Optional[CareState]:
    """The user's care state through its owners; an empty state without memory-read consent; None when ``db`` is missing or on error."""
    if db is None:
        return None
    try:
        moment = now or datetime.utcnow()
        if not _has_read_consent(db, user_id):
            return CareState(user_id=user_id, consent=False)
        return CareState(
            user_id=user_id,
            consent=True,
            issues=_issues(db, user_id),
            follow_ups=_follow_ups(db, user_id),
            events=_events(db, user_id, moment),
            medications=_medications(db, user_id),
            resolved_recent=_resolved(db, user_id, moment),
        )
    except Exception:  # noqa: BLE001 - every consumer already degrades without it
        logger.exception("[R-108] care state not built")
        return None


def summary_line(state: Optional[CareState], language: Optional[str] = None) -> str:
    """One deterministic line (catalog text, no model) for chat / notification / report consumers; «» when there is nothing to say."""
    if state is None or not state.consent:
        return ""
    raw = str(language or "").strip().lower()
    lang = next((c for c in _LANGS if raw.startswith(c)), "fa")
    parts: list[str] = []
    for issue in state.issues[:1]:
        parts.append(sedi_copy.t(f"care_state.issue.{issue.status}", lang, text=issue.text))
    if state.follow_ups:
        parts.append(sedi_copy.t("care_state.followup", lang))
    for event in state.events[:1]:
        parts.append(sedi_copy.t("care_state.event", lang, title=event.title))
    if state.resolved_recent:
        parts.append(sedi_copy.t("care_state.resolved", lang, n=state.resolved_recent))
    return " · ".join(parts)
