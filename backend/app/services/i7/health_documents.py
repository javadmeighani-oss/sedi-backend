"""R-074 step 4 - the user's lab results and prescriptions become part of the OVERALL HEALTH PICTURE (existing owners, no new table).

Flow (the pipeline in `attachments.py` stays the entry): upload -> vision reading -> THIS module adds a deterministic, plain-words
analysis (what the document itself marks out of range, how a value moved against the user's earlier confirmed documents) ->
the user confirms -> the facts are written to I6 (`medical.lab_results`, `medical.prescribed_medications`, read back into chat
context through HealthContextAdapter) and the life-event timeline (I7) as before.

Boundaries: no model call here, no diagnosis, no advice, no drug change; «out of range» is only what the document printed; a
trend is only arithmetic on the user's own documents. Everything is consent-gated (I6 write), bounded and fail-open.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models, sedi_copy

MAX_LAB_FACT_ITEMS = 20
MAX_MEDS = 15
MAX_TREND_LINES = 6
MAX_FLAG_LINES = 8
_PREV_DOCS = 12
_SAME_BAND = 0.03  # within 3 % = "about the same"

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_TO_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")
_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _lang(language: Optional[str]) -> str:
    return language if language in ("fa", "ar", "en") else "en"


def _show(text: Any, lang: str) -> str:
    s = str(text)
    return s.translate(_FA_DIGITS) if lang in ("fa", "ar") else s


def _num(value: Any) -> Optional[float]:
    m = _NUM.search(str(value or "").translate(_TO_ASCII))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def _norm(name: Any) -> str:
    return re.sub(r"[\s‌\-_/().,:;]+", " ", str(name or "").lower()).strip()


def _unit_key(unit: Any) -> str:
    return re.sub(r"[\s.‌]+", "", str(unit or "").lower())


def _by_date_desc(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest REPORT date first (Codex P2): a backdated report confirmed later never overwrites a newer result."""
    return sorted(docs, key=lambda d: str(d.get("date") or ""), reverse=True)


def _previous_docs(db: Session, user_id: int, exclude_id: Optional[int]) -> list[dict[str, Any]]:
    """Earlier CONFIRMED documents of the user, newest first: [{date, type, findings, medications}]."""
    q = (
        db.query(models.UserAttachment)
        .filter(models.UserAttachment.user_id == user_id, models.UserAttachment.status == "confirmed")
        .order_by(models.UserAttachment.id.desc())
        .limit(_PREV_DOCS + 1)
    )
    out: list[dict[str, Any]] = []
    for row in q.all():
        if exclude_id is not None and int(row.id) == int(exclude_id):
            continue
        try:
            data = json.loads(row.extracted_json) if row.extracted_json else {}
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        out.append(
            {
                "date": data.get("date") or (row.processed_at.date().isoformat() if row.processed_at else ""),
                "type": data.get("document_type"),
                "findings": [f for f in (data.get("findings") or []) if isinstance(f, dict)],
                "medications": [str(m) for m in (data.get("medications") or []) if str(m).strip()],
            }
        )
    return _by_date_desc(out)[:_PREV_DOCS]


def _trends(current: list[dict[str, Any]], previous: list[dict[str, Any]], current_date: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in current:
        cur = _num(f.get("value"))
        name = _norm(f.get("name"))
        if cur is None or not name:
            continue
        for doc in previous:
            if current_date and doc.get("date") and str(doc["date"]) > current_date:
                continue  # only EARLIER documents are a 'before'
            # Codex P2: values are compared only when the unit matches (mg/dL vs mmol/L are different scales)
            hit = next(
                (
                    p
                    for p in doc["findings"]
                    if _norm(p.get("name")) == name
                    and _num(p.get("value")) is not None
                    and _unit_key(p.get("unit")) == _unit_key(f.get("unit"))
                ),
                None,
            )
            if hit is None:
                continue
            prev = _num(hit.get("value"))
            direction = "same"
            if prev and abs(cur - prev) / abs(prev) >= _SAME_BAND:
                direction = "up" if cur > prev else "down"
            elif prev == 0 and cur != 0:
                direction = "up" if cur > 0 else "down"
            out.append(
                {
                    "name": str(f.get("name")),
                    "unit": str(f.get("unit") or ""),
                    "prev": str(hit.get("value")),
                    "cur": str(f.get("value")),
                    "date": str(doc["date"] or ""),
                    "direction": direction,
                }
            )
            break
        if len(out) >= MAX_TREND_LINES:
            break
    return out


def analyse(db: Session, user_id: int, parsed: dict[str, Any], *, attachment_id: Optional[int], language: str, confirmed: bool) -> dict[str, Any]:
    """Deterministic plain-words analysis of one read document (never raises past the caller's guard)."""
    lang = _lang(language)
    doc_type = str(parsed.get("document_type") or "other")
    findings = [f for f in (parsed.get("findings") or []) if isinstance(f, dict)]
    meds = [str(m) for m in (parsed.get("medications") or []) if str(m).strip()]
    lines: list[str] = []
    flagged: list[dict[str, str]] = []
    trends: list[dict[str, Any]] = []
    t = sedi_copy.t

    if doc_type == "lab_result" and findings:
        flagged = [f for f in findings if f.get("flag") in ("low", "high")][:MAX_FLAG_LINES]
        n = len(findings)
        if flagged:
            lines.append(t("doc.analysis.lab.head", lang, n=_show(n, lang), k=_show(len(flagged), lang)))
            for f in flagged:
                lines.append(
                    t(
                        "doc.analysis.lab.flag_line",
                        lang,
                        name=str(f.get("name")),
                        value=_show(f.get("value"), lang),
                        unit=str(f.get("unit") or ""),
                        dir=t(f"doc.analysis.dir.{f.get('flag')}", lang),
                    ).replace("  ", " ")
                )
        else:
            lines.append(t("doc.analysis.lab.none_flagged", lang, n=_show(n, lang)))
        trends = _trends(findings, _previous_docs(db, user_id, attachment_id), str(parsed.get("date") or ""))
        for tr in trends:
            lines.append(
                t(
                    "doc.analysis.lab.trend_line",
                    lang,
                    name=tr["name"],
                    prev=_show(tr["prev"], lang),
                    cur=_show(tr["cur"], lang),
                    unit=tr["unit"],
                    dir=t(f"doc.analysis.trend.{tr['direction']}", lang),
                    date=_show(tr["date"], lang),
                ).replace("  ", " ")
            )
        lines.append(t("doc.analysis.lab.saved" if confirmed else "doc.analysis.lab.saved_pending", lang))
    elif meds:
        names = "، ".join(meds[:MAX_MEDS]) if lang in ("fa", "ar") else ", ".join(meds[:MAX_MEDS])
        lines.append(t("doc.analysis.rx", lang, n=_show(len(meds), lang), names=names))
        lines.append(t("doc.analysis.rx.saved" if confirmed else "doc.analysis.rx.pending", lang))
    else:
        lines.append(t("doc.analysis.other.saved" if confirmed else "doc.analysis.other", lang))

    suggestions: list[dict[str, Any]] = []
    visit = _future_date(parsed.get("next_visit_date"))
    if visit is not None:
        key = "doc.analysis.next_visit.ask" if confirmed else "doc.analysis.next_visit"
        lines.append(t(key, lang, date=_show(visit.isoformat(), lang)))
        suggestions.append({"kind": "next_visit", "date": visit.isoformat()})
    instr = [str(i) for i in (parsed.get("instructions") or []) if str(i).strip()][:5]
    if instr:
        lines.append(t("doc.analysis.instructions", lang, items=("؛ " if lang in ("fa", "ar") else "; ").join(instr)))
    if meds:
        suggestions.append({"kind": "medication_times", "names": meds[:MAX_MEDS]})

    return {
        "suggestions": suggestions,
        "document_type": doc_type,
        "flagged": [{"name": str(f.get("name")), "value": str(f.get("value")), "unit": str(f.get("unit") or ""), "flag": f.get("flag")} for f in flagged],
        "trends": trends,
        "text": "\n".join(lines),
    }


def _fact_line(f: dict[str, Any], date: str) -> str:
    flag = {"high": " (high)", "low": " (low)"}.get(f.get("flag"), "")
    unit = f" {f.get('unit')}" if f.get("unit") else ""
    when = f" [{date}]" if date else ""
    return f"{f.get('name')} {f.get('value')}{unit}{flag}{when}".strip()


def _sync_picture(db: Session, user_id: int, docs: list[dict[str, Any]]) -> dict[str, bool]:
    """Write (or, when nothing remains, forget) the two I6 facts from the user's confirmed documents, newest first."""
    from backend.app.services.i6.memory_writes import delete_fact, write_fact

    done = {"lab_results": False, "prescribed_medications": False}
    docs = _by_date_desc(docs)
    latest: dict[str, str] = {}
    for doc in docs:  # the first sighting of a test is its latest value
        if doc.get("type") != "lab_result":
            continue
        for f in doc["findings"]:
            key = _norm(f.get("name"))
            if key and key not in latest and len(latest) < MAX_LAB_FACT_ITEMS:
                latest[key] = _fact_line(f, str(doc.get("date") or ""))
    meds: list[str] = []
    seen: set[str] = set()
    for doc in docs:
        for m in doc["medications"]:
            k = _norm(m)
            if k and k not in seen and len(meds) < MAX_MEDS:
                seen.add(k)
                meds.append(m.strip())
    for key, items, limit in (("lab_results", list(latest.values()), 900), ("prescribed_medications", meds, 600)):
        try:
            if items:
                write_fact(db, user_id, "medical", key, "؛ ".join(items)[:limit], source="document", sensitivity_class="high")
                done[key] = True
            else:
                delete_fact(db, user_id, "medical", key, reason="document_forgotten")
        except Exception:
            db.rollback()
    return done


def record_into_picture(db: Session, user_id: int, parsed: dict[str, Any], *, attachment_id: int) -> dict[str, bool]:
    """After the user's confirmation: latest value per test + prescribed medicines go to I6 (read back into chat context)."""
    current = {
        "date": parsed.get("date") or "",
        "type": parsed.get("document_type"),
        "findings": [f for f in (parsed.get("findings") or []) if isinstance(f, dict)],
        "medications": [str(m) for m in (parsed.get("medications") or [])],
    }
    return _sync_picture(db, user_id, [current] + _previous_docs(db, user_id, attachment_id))


def forget_from_picture(db: Session, user_id: int) -> dict[str, bool]:
    """After a document is deleted: the picture is rebuilt from the documents that remain (or forgotten when none do)."""
    return _sync_picture(db, user_id, _previous_docs(db, user_id, None))


def _future_date(value: Any) -> Optional[date]:
    try:
        d = datetime.strptime(str(value or ""), "%Y-%m-%d").date()
    except ValueError:
        return None
    return d if d >= (datetime.utcnow().date() - timedelta(days=1)) else None


def create_next_visit_event(db: Session, user_id: int, parsed: dict[str, Any], *, language: str) -> Optional[dict[str, Any]]:
    """The next appointment printed on a confirmed document becomes a doctor-visit event with a reminder (event owner: gate2)."""
    visit = _future_date(parsed.get("next_visit_date"))
    if visit is None:
        return None
    lang = _lang(language)
    day_start = datetime(visit.year, visit.month, visit.day)
    dup = (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.user_id == user_id,
            models.UserEvent.event_type == "doctor_visit",
            models.UserEvent.status == "scheduled",
            models.UserEvent.starts_at >= day_start,
            models.UserEvent.starts_at < day_start + timedelta(days=1),
        )
        .first()
    )
    if dup is not None:
        return {"created": False, "duplicate": True, "event_id": int(dup.id), "date": visit.isoformat()}
    from backend.app.schemas.gate2 import EventCreateIn
    from backend.app.services.gate2_data_service import create_event
    from backend.app.services.gate4.policy_prefs_bridge import resolve_validated_user_timezone

    try:
        tz = resolve_validated_user_timezone(db, user_id)
    except Exception:
        tz = None
    body = EventCreateIn(
        title=sedi_copy.t("doc.next_visit.title", lang),
        event_domain="medical",
        event_type="doctor_visit",
        starts_at=day_start.replace(hour=9),
        timezone=tz,
        status="scheduled",
        importance="high",
        reminder_enabled=True,
        reminder_offsets=[60],
        source="system",
    )
    ev = create_event(db, user_id, body)
    return {"created": True, "duplicate": False, "event_id": ev.get("id"), "date": visit.isoformat()}


def previsit_checklist(db: Session, user_id: int, language: str) -> dict[str, Any]:
    """Deterministic «before the visit» list built ONLY from what the user's own picture holds (no invented values, no advice)."""
    from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty

    lang = _lang(language)
    t = sedi_copy.t
    facts = {f.key: str(f.value_json) for f in list_facts_readonly_or_empty(db, user_id, domain="medical")}
    bring = [t("previsit.bring.generic", lang)]
    if facts.get("lab_results"):
        bring.insert(0, t("previsit.bring.labs", lang))
    meds = facts.get("prescribed_medications")
    if meds:
        bring.insert(0, t("previsit.bring.meds", lang, names=meds[:200]))
    ask = [t("previsit.ask.change", lang)]
    if meds:
        ask.append(t("previsit.ask.meds", lang))
    ask.append(t("previsit.ask.questions", lang))
    text = "\n".join([t("previsit.head", lang)] + ["• " + b for b in bring] + [t("previsit.say", lang)] + ["• " + a for a in ask])
    return {"bring": bring, "say": ask, "text": text}
