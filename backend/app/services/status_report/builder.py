"""R-110 amendment 1 (Javad 2026-11-20): ONE «status report» that Sedi prepares on request - general health status, a doctor-visit
summary, a diet/nutrition plan, lifestyle, an exercise-plan output.

One contract, built ONLY from the owners that already hold the data (R-005: no new store, no schema, no write path):
  * I6 facts (consent-gated read): complaints, episodes, history, allergies, preferences, work, goals;
  * UserMedication (the user's own medicines), I8 weekly plan projection + weekly user report (what the user marked), I10 journey state;
  * UserState for the name and age.
The report is a list of titled sections of short lines with stable ids so the app can let the user review and remove any line
BEFORE it makes the file; the file itself (PDF) is made on the user's device and shared by the user (no automatic sending).
It states only what the user said or recorded - never a diagnosis, never a drug suggestion. Fail-open per section.
Kill switch: SEDI_STATUS_REPORT_DISABLED.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from backend.app import sedi_copy

logger = logging.getLogger(__name__)

DISABLED_ENV = "SEDI_STATUS_REPORT_DISABLED"
KINDS = ("health_status", "doctor_visit", "nutrition", "lifestyle", "exercise_plan")
MAX_ITEMS = 8
MAX_ITEM_CHARS = 140
MAX_PLAN_LINES = 28
_QUESTIONS = 3

# kind -> ordered section keys
SECTIONS: dict[str, tuple[str, ...]] = {
    "health_status": ("about", "concerns", "timeline", "history", "allergies", "meds", "sleep", "work", "goals", "follow_up", "week"),
    "doctor_visit": ("about", "reason", "timeline", "history", "allergies", "meds", "follow_up", "questions"),
    "nutrition": ("about", "allergies", "food", "goals", "plan_nutrition", "week"),
    "lifestyle": ("about", "goals", "sleep", "work", "household", "interests", "food", "exercise", "week"),
    "exercise_plan": ("about", "goals", "exercise", "plan_exercise", "week"),
}


def enabled() -> bool:
    return os.getenv(DISABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def _lang(language: Optional[str]) -> str:
    raw = str(language or "").strip().lower()
    for code in ("fa", "ar", "en"):
        if raw.startswith(code):
            return code
    return "fa"


def kinds(language: Optional[str] = None) -> list[dict[str, str]]:
    lang = _lang(language)
    return [{"kind": k, "title": sedi_copy.t(f"report.kind.{k}", lang)} for k in KINDS]


# ----------------------------------------------------------------------------------------------------------------- readers
def _clip(text: Any, limit: int = MAX_ITEM_CHARS) -> str:
    return " ".join(str(text or "").split())[:limit].strip()


def _items(value: Any, *, newest: bool = False) -> list[str]:
    """Clean short lines from a stored fact (a list, a string or a number - e.g. sleep hours are stored as an integer). ``newest``: a
    chronological list keeps its LAST items when it is longer than the cap (new statements are appended)."""
    if isinstance(value, (list, tuple)):
        raw = list(value)
    elif isinstance(value, bool):
        raw = []
    elif isinstance(value, (int, float)):
        raw = [value]
    elif isinstance(value, str) and value.strip():
        raw = [value]
    else:
        raw = []
    out: list[str] = []
    for item in raw:
        text = _clip(item)
        if text and text not in out:
            out.append(text)
    return out[-MAX_ITEMS:] if newest else out[:MAX_ITEMS]


def _facts(db: Any, user_id: int) -> dict[tuple[str, str], Any]:
    """Every readable I6 fact as {(domain, key): value}; {} without read consent (the I6 reader is consent-gated)."""
    from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty

    out: dict[tuple[str, str], Any] = {}
    for row in list_facts_readonly_or_empty(db, user_id) or []:
        try:
            out[(str(row.domain), str(row.key))] = json.loads(row.value_json)
        except Exception:  # noqa: BLE001 - one unreadable fact never breaks the report
            continue
    return out


def _fact_lines(facts: dict, *pairs: tuple[str, str], newest: bool = False) -> list[str]:
    lines: list[str] = []
    for pair in pairs:
        for item in _items(facts.get(pair), newest=newest):
            if item not in lines:
                lines.append(item)
    return lines[-MAX_ITEMS:] if newest else lines[:MAX_ITEMS]


def _about(db: Any, user_id: int, lang: str) -> list[str]:
    try:
        from backend.app.services.user_context.user_state import get_user_state

        state = get_user_state(db, user_id)
        if state is None:
            return []
        lines: list[str] = []
        if state.preferred_name:
            lines.append(sedi_copy.t("report.about.name", lang, name=_clip(state.preferred_name, 60)))
        if state.age:
            lines.append(sedi_copy.t("report.about.age", lang, age=state.age))
        return lines
    except Exception:  # noqa: BLE001
        return []


def _meds(db: Any, user_id: int, lang: str) -> list[str]:
    try:
        from backend.app.services.user_medication_service import list_user_medications

        lines: list[str] = []
        for med in list_user_medications(db, user_id)[:MAX_ITEMS]:
            parts = [_clip(med.get("name"), 60)]
            if med.get("user_dosage"):
                parts.append(_clip(med["user_dosage"], 40))
            line = " - ".join(p for p in parts if p)
            times = [str(t) for t in (med.get("reminder_times") or [])]
            if times:
                line += " (" + sedi_copy.t("report.meds.times", lang, times=", ".join(times)) + ")"
            if line:
                lines.append(line)
        return lines
    except Exception:  # noqa: BLE001
        return []


def _plan_lines(db: Any, user_id: int, domain: str, lang: str) -> list[str]:
    try:
        from backend.app.services.lifestyle.a3_weekly_plan_projection import build_lifestyle_weekly_plan_projection

        projection = build_lifestyle_weekly_plan_projection(db, user_id)
        if projection.get("state") in ("review_due", "empty", "unavailable"):
            return []  # an ended cycle is history, not «this week's plan» (Codex P2, PR 200)
        lines: list[str] = []
        for day in projection.get("days") or []:
            for item in day.get(domain) or []:
                title = _clip(item.get("activity_title") or item.get("title"), 90)
                if not title:
                    continue
                key = "report.plan.line_timed" if item.get("local_time") else "report.plan.line"
                lines.append(sedi_copy.t(key, lang, day=day.get("day_index"), time=item.get("local_time") or "", title=title))
                if len(lines) >= MAX_PLAN_LINES:
                    return lines
        return lines
    except Exception:  # noqa: BLE001
        return []


def _week_lines(db: Any, user_id: int, lang: str) -> list[str]:
    """What the user marked this week (only when something was marked - never an invented number)."""
    try:
        from backend.app.services.i8.weekly_user_report import build_weekly_user_report

        report = build_weekly_user_report(db, user_id, language=lang)
        totals = report.get("totals") or {}
        if report.get("state") != "ready":
            return []
        return [sedi_copy.t("report.week.line", lang, done=int(totals.get("done", 0)), not_done=int(totals.get("not_done", 0)))]
    except Exception:  # noqa: BLE001
        return []


def _follow_up_lines(db: Any, user_id: int, lang: str) -> list[str]:
    try:
        from backend.app.services.i10 import commitment_followup as cf

        return [sedi_copy.t("report.followup.open", lang)] if cf.open_journey_count(db, user_id) > 0 else []
    except Exception:  # noqa: BLE001
        return []


def _section_lines(key: str, db: Any, user_id: int, facts: dict, lang: str) -> list[str]:
    if key == "about":
        return _about(db, user_id, lang)
    if key == "reason":  # the reason for the visit: what the user told Sedi is the problem, else the newest episode note
        concerns = _fact_lines(facts, ("medical", "health_concerns"))
        return concerns or _fact_lines(facts, ("medical", "symptom_episodes"), newest=True)[-1:]
    if key == "concerns":
        return _fact_lines(facts, ("medical", "health_concerns"))
    if key == "timeline":
        return _fact_lines(facts, ("medical", "symptom_episodes"), newest=True)  # the latest updates, never the oldest eight
    if key == "history":
        return _fact_lines(facts, ("medical", "family_history"))
    if key == "allergies":
        return _fact_lines(facts, ("intake", "allergies"))
    if key == "meds":
        return _meds(db, user_id, lang)
    if key == "sleep":
        return [sedi_copy.t("report.sleep.line", lang, hours=h) for h in _fact_lines(facts, ("lifestyle", "sleep_duration_hours"))[:1]]
    if key == "work":
        return _fact_lines(facts, ("work", "occupation"), ("work", "work_schedule"), ("work", "work_stressors"))
    if key == "goals":
        return _fact_lines(facts, ("intake", "goal"))
    if key == "household":
        return _fact_lines(facts, ("social", "household_context"))
    if key == "interests":
        return _fact_lines(facts, ("preferences", "interests"))
    if key == "food":
        return _fact_lines(facts, ("intake", "food_preferences"))
    if key == "exercise":
        return _fact_lines(facts, ("intake", "exercise_preferences"))
    if key == "plan_nutrition":
        return _plan_lines(db, user_id, "nutrition", lang)
    if key == "plan_exercise":
        return _plan_lines(db, user_id, "exercise", lang)
    if key == "week":
        return _week_lines(db, user_id, lang)
    if key == "follow_up":
        return _follow_up_lines(db, user_id, lang)
    if key == "questions":  # questions for the doctor (not answers): fixed, catalog text
        return [sedi_copy.t(f"report.question.{i}", lang) for i in range(1, _QUESTIONS + 1)]
    return []


def _has_read_consent(db: Any, user_id: int) -> bool:
    try:
        from backend.app.services.i6.consent_service import PERM_READ, has_permission_readonly

        return bool(has_permission_readonly(db, user_id, PERM_READ))
    except Exception:  # noqa: BLE001
        return False


# ----------------------------------------------------------------------------------------------------------------- the report
def build_status_report(db: Any, user_id: int, kind: str, language: Optional[str] = None, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """The report as plain data: ``{kind, title, language, generated_on, state, sections:[{key,title,lines:[{id,text}]}], note}``.

    ``state``: 'ready' (something beyond the identity lines), 'empty' (Sedi knows nothing to report yet), 'no_consent' (memory read
    consent is missing - nothing is read). An unknown kind raises ``ValueError`` (the router answers 422)."""
    if kind not in KINDS:
        raise ValueError(f"unknown status report kind: {kind!r}")
    lang = _lang(language)
    report: dict[str, Any] = {
        "kind": kind,
        "title": sedi_copy.t(f"report.kind.{kind}", lang),
        "language": lang,
        "generated_on": (now or datetime.utcnow()).date().isoformat(),
        "state": "no_consent",
        "sections": [],
        "note": sedi_copy.t("report.note", lang),
    }
    if not _has_read_consent(db, user_id):
        return report
    facts = _facts(db, user_id)
    content = False
    for key in SECTIONS[kind]:
        try:
            lines = _section_lines(key, db, user_id, facts, lang)
        except Exception:  # noqa: BLE001 - one section never breaks the report
            logger.exception("[R-110] status report section skipped: %s", key)
            lines = []
        if not lines:
            continue
        if key not in ("about", "questions"):
            content = True
        report["sections"].append(
            {
                "key": key,
                "title": sedi_copy.t(f"report.section.{key}", lang),
                "lines": [{"id": f"{key}-{i}", "text": text} for i, text in enumerate(lines)],
            }
        )
    report["state"] = "ready" if content else "empty"
    if not content:  # an «about + questions» skeleton is not a report: keep only the honest empty state
        report["sections"] = []
    return report
