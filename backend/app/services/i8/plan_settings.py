"""Plan settings (pilot V1 screen 6, Javad 2026-10-29): which weekdays the meal reminders count for, how long BEFORE the
meal Sedi reminds, and on which weekday and time the weekly review comes.

Stored as ONE I6 fact ``preferences.plan_settings`` (JSON per domain: ``{"nutrition": {...}, "exercise": {...}}``) -
consent-gated, vocabulary-only (no migration). The same values are copied onto the plan's ACTIVE composer actions as
``presentation_json.remind`` so the reminder worker needs no extra query.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

DOMAINS = ("nutrition", "exercise")
FACT_DOMAIN = "preferences"
FACT_KEY = "plan_settings"
# None = no reminders; 0 = on time; otherwise minutes BEFORE the item.
VALID_LEADS = (None, 0, 15, 30)
REVIEW_TIME_DEFAULT = "20:00"


class PlanSettingsError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def default_review_weekday(language: Optional[str]) -> int:
    """ISO weekday of the weekly review: Friday for Persian, Sunday for English and Arabic (Javad 2026-10-29)."""
    lang = (language or "fa").split("-")[0].lower()
    return 5 if lang == "fa" else 7


def default_settings(language: Optional[str]) -> dict:
    return {
        "days": [1, 2, 3, 4, 5, 6, 7],
        "lead": 0,
        "review_weekday": default_review_weekday(language),
        "review_time": REVIEW_TIME_DEFAULT,
    }


def _valid_hhmm(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if len(text) != 5 or text[2] != ":" or not (text[:2] + text[3:]).isdigit():
        return None
    hour, minute = int(text[:2]), int(text[3:])
    return text if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def normalize(patch: dict, base: dict) -> dict:
    """Merge a partial patch over ``base`` and validate. Raises PlanSettingsError(code)."""
    out = dict(base)
    if "days" in patch and patch["days"] is not None:
        days = patch["days"]
        if not isinstance(days, (list, tuple)):
            raise PlanSettingsError("DAYS_INVALID")
        try:
            clean = sorted({int(d) for d in days})
        except (TypeError, ValueError) as exc:
            raise PlanSettingsError("DAYS_INVALID") from exc
        if not clean or any(d < 1 or d > 7 for d in clean):
            raise PlanSettingsError("DAYS_INVALID")
        out["days"] = clean
    if "lead" in patch:
        lead = patch["lead"]
        if lead not in VALID_LEADS:
            raise PlanSettingsError("LEAD_INVALID")
        out["lead"] = lead
    if "review_weekday" in patch and patch["review_weekday"] is not None:
        try:
            weekday = int(patch["review_weekday"])
        except (TypeError, ValueError) as exc:
            raise PlanSettingsError("REVIEW_WEEKDAY_INVALID") from exc
        if weekday < 1 or weekday > 7:
            raise PlanSettingsError("REVIEW_WEEKDAY_INVALID")
        out["review_weekday"] = weekday
    if "review_time" in patch and patch["review_time"] is not None:
        hhmm = _valid_hhmm(patch["review_time"])
        if hhmm is None:
            raise PlanSettingsError("REVIEW_TIME_INVALID")
        out["review_time"] = hhmm
    return out


def _user_language(db: Session, user_id: int) -> str:
    row = db.query(models.User.preferred_language).filter(models.User.id == int(user_id)).first()
    lang = ((row[0] if row and row[0] else "fa") or "fa").strip().lower().split("-")[0]
    return lang if lang in ("fa", "ar", "en") else "en"


def _stored(db: Session, user_id: int) -> dict:
    from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty

    for row in list_facts_readonly_or_empty(db, user_id, domain=FACT_DOMAIN):
        if row.key == FACT_KEY:
            try:
                data = json.loads(row.value_json or "{}")
            except (TypeError, ValueError):
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def has_saved_settings(db: Session, user_id: int, domain: str) -> bool:
    return isinstance(_stored(db, user_id).get(domain), dict)


def get_plan_settings(db: Session, user_id: int, domain: str, language: Optional[str] = None) -> dict:
    """The user's settings for ``domain`` (defaults filled in; never raises for unknown stored values)."""
    lang = language or _user_language(db, user_id)
    base = default_settings(lang)
    saved = _stored(db, user_id).get(domain)
    if isinstance(saved, dict):
        try:
            return normalize(saved, base)
        except PlanSettingsError:
            return base
    return base


def save_plan_settings(db: Session, user_id: int, domain: str, patch: dict, language: Optional[str] = None) -> dict:
    """Validate, store (consent-gated I6 write) and apply to the plan's reminder items. Returns the new settings."""
    from backend.app.services.i6.memory_writes import write_fact

    if domain not in DOMAINS:
        raise PlanSettingsError("DOMAIN_INVALID")
    current = get_plan_settings(db, user_id, domain, language)
    new = normalize(patch, current)
    blob = _stored(db, user_id)
    blob[domain] = new
    write_fact(db, user_id, FACT_DOMAIN, FACT_KEY, blob, commit=True)
    apply_settings_to_actions(db, user_id, domain, new)
    return new


def apply_settings_to_actions(db: Session, user_id: int, domain: str, settings: dict) -> int:
    """Copy the reminder settings onto the ACTIVE composer actions of ``domain``. Returns how many were updated."""
    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.user_id == int(user_id),
            models.I8OperationalPlanAction.action_domain == domain,
            models.I8OperationalPlanAction.status == "ACTIVE",
        )
        .all()
    )
    days = set(settings.get("days") or [])
    lead = settings.get("lead")
    changed = 0
    from datetime import date as _date

    for row in rows:
        try:
            pres = json.loads(row.presentation_json or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(pres, dict) or pres.get("source") != "sedi_plan_catalog_v1":
            continue
        weekday = None
        try:
            weekday = _date.fromisoformat(str(pres.get("local_date") or "")).isoweekday()
        except ValueError:
            weekday = None
        on = lead is not None and (weekday is None or weekday in days)
        remind = {"on": bool(on), "lead": int(lead or 0)}
        if pres.get("remind") == remind:
            continue
        pres["remind"] = remind
        row.presentation_json = json.dumps(pres, ensure_ascii=False)
        changed += 1
    if changed:
        db.commit()
    return changed
