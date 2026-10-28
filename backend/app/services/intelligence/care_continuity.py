# backend.app.services.intelligence.care_continuity
"""R-018: continuity of care for the chat voice — read-only, no new storage.

1. Life event: the user once told Sedi about a significant event (loss, job loss, separation, surgery, accident). A
   CareFollowUpTask(kind care_checkin) exists (I10-B12); when the user comes back to chat, Sedi may ask gently how they are
   holding up. Only the KIND is stored (never details).
2. Earlier suggestions: concrete things Sedi suggested more than 8 turns ago (outside the history window) but within a week,
   so she can ask "how did it go?" like a real caretaker. Taken from retention/consent-gated raw turns (I6 memory.read, I7).
Both are returned as ONE bounded system hint, '' when there is nothing (callers append it to the relationship guidance).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

_HISTORY_WINDOW_TURNS = 8
_SCAN_TURNS = 40
_MAX_SUGGESTIONS = 2
_SNIPPET_CHARS = 140
_EVENT_LOOKBACK_DAYS = 10

_SUGGESTION_MARKERS = (
    "پیشنهاد می‌کنم", "پیشنهاد میکنم", "پیشنهادم", "امتحان کن", "سعی کن", "تمرین", "هر شب", "هر روز", "قبل از خواب",
    "i suggest", "try ", "practice", "before bed", "every day", "every night",
    "أقترح", "جرّب", "جرب", "كل يوم",
)
_ERROR_MARKERS = ("مشکل فنی از سمت خودم", "خطایی رخ داد", "technical problem on my side", "حدث خطأ")

_EVENT_LABEL = {
    "loss": {"fa": "از دست دادن یکی از عزیزانش", "en": "losing someone dear to them", "ar": "فقدان عزيز"},
    "job_loss": {"fa": "از دست دادن کارش", "en": "losing their job", "ar": "فقدان العمل"},
    "separation": {"fa": "جدایی/طلاق", "en": "a separation or divorce", "ar": "انفصال أو طلاق"},
    "surgery": {"fa": "یک عمل جراحی", "en": "surgery", "ar": "عملية جراحية"},
    "accident": {"fa": "یک تصادف", "en": "an accident", "ar": "حادث"},
}


def _lang(language: Optional[str]) -> str:
    raw = (language or "fa").strip().lower().split("-")[0]
    return raw if raw in ("fa", "en", "ar") else "en"


def recent_life_event(db, user_id: int, *, now: Optional[datetime] = None) -> Optional[tuple[str, int]]:
    """(kind, days_ago) of the newest care_checkin task in the lookback window, or None."""
    from backend.app import models
    from backend.app.services.candidate_promotion_service import CARE_CHECKIN_TITLE_PREFIX

    when = now or datetime.utcnow()
    row = (
        db.query(models.CareFollowUpTask)
        .filter(
            models.CareFollowUpTask.user_id == user_id,
            models.CareFollowUpTask.title.like(f"{CARE_CHECKIN_TITLE_PREFIX}%"),
            models.CareFollowUpTask.created_at >= when - timedelta(days=_EVENT_LOOKBACK_DAYS),
        )
        .order_by(models.CareFollowUpTask.created_at.desc())
        .first()
    )
    if row is None:
        return None
    kind = str(row.title)[len(CARE_CHECKIN_TITLE_PREFIX):].strip().lower()
    if kind not in _EVENT_LABEL:
        return None
    return kind, max(0, (when - row.created_at).days)


def earlier_suggestions(db, user_id: int, *, now: Optional[datetime] = None) -> list[str]:
    """Short snippets of Sedi's own concrete suggestions older than the history window (within 7 days)."""
    from backend.app.services.i6.consent_service import PERM_READ, has_permission
    from backend.app.services.i7.retention import query_eligible_raw

    if not has_permission(db, user_id, PERM_READ):
        return []
    when = now or datetime.utcnow()
    out: list[str] = []
    for row in list(query_eligible_raw(db, user_id, limit=_SCAN_TURNS) or [])[_HISTORY_WINDOW_TURNS:]:
        created = getattr(row, "created_at", None)
        if created is not None and created.replace(tzinfo=None) < when - timedelta(days=7):
            continue
        reply = str(getattr(row, "sedi_response", "") or "")
        if not reply or any(m in reply for m in _ERROR_MARKERS):
            continue
        low = reply.lower()
        marker = next((m for m in _SUGGESTION_MARKERS if m in low), None)
        if marker is None:
            continue
        sentence = next((s.strip() for s in reply.replace("\n", ". ").split(".") if marker in s.lower()), "")
        sentence = " ".join(sentence.split())[:_SNIPPET_CHARS]
        if sentence and sentence not in out:
            out.append(sentence)
        if len(out) >= _MAX_SUGGESTIONS:
            break
    return out


def build_continuity_hint(db, user_id: int, language: Optional[str], *, now: Optional[datetime] = None) -> str:
    """Fail-open: '' on any problem."""
    lang = _lang(language)
    lines: list[str] = []
    try:
        from backend.app.services.i7.same_day_recap import today_so_far_hint

        _today = today_so_far_hint(db, user_id, language, now=now)
        if _today:
            lines.append(_today)
    except Exception:
        pass
    try:
        ev = recent_life_event(db, user_id, now=now)
    except Exception:
        ev = None
    if ev:
        kind, days = ev
        label = _EVENT_LABEL[kind][lang]
        if lang == "fa":
            lines.append(f"[رویداد_مهم_اخیر] کاربر {days} روز پیش درباره‌ی «{label}» با تو حرف زده بود و ممکن است هنوز دلش سنگین باشد. اگر خودش مطرح نکرد و طبیعی بود، یک‌بار ملایم بپرس چطور دوام می‌آورد؛ موضوع را هر بار پیش نکش و جزئیات را از خودت اضافه نکن.")
        elif lang == "ar":
            lines.append(f"[حدث_مهم_حديث] تحدث المستخدم قبل {days} يوماً عن «{label}» وقد يكون ما زال متأثراً. إن لم يذكره وكان الأمر طبيعياً فاسأليه مرة واحدة بلطف كيف يتحمل؛ ولا تعيدي الموضوع كل مرة ولا تضيفي تفاصيل من عندك.")
        else:
            lines.append(f"[RECENT_LIFE_EVENT] {days} day(s) ago the user told you about {label}; they may still be hurting. If they have not brought it up and it feels natural, ask gently ONCE how they are holding up; do not raise it every time and never add details of your own.")
    try:
        sugg = earlier_suggestions(db, user_id, now=now)
    except Exception:
        sugg = []
    if sugg:
        joined = " | ".join(sugg)
        if lang == "fa":
            lines.append(f"[پیشنهادهای_قبلی_صدی] (از گفت‌وگوهای چند روز اخیر) {joined} — اگر مناسب بود، به‌جای پیشنهاد تازه اول بپرس همان‌ها چطور پیش رفت.")
        elif lang == "ar":
            lines.append(f"[اقتراحات_سابقة] (من محادثات الأيام الماضية) {joined} — إن ناسب، اسألي كيف سارت قبل اقتراح جديد.")
        else:
            lines.append(f"[EARLIER_SUGGESTIONS] (from conversations in the past days) {joined} — if it fits, ask how those went before suggesting something new.")
    try:
        from datetime import datetime as _dt, timezone as _tz

        import pytz

        from backend.app.services.gate4.policy_prefs_bridge import resolve_validated_user_timezone
        from backend.app.services.i7.user_done import done_today_hint

        _zone = pytz.timezone(resolve_validated_user_timezone(db, user_id))
        _today = (now or _dt.now(_tz.utc)).astimezone(_zone).date()
        _done = done_today_hint(db, user_id, language, _today)
        if _done:
            lines.append(_done)
    except Exception:
        pass
    try:
        from backend.app.services.i8.action_edit import plan_changes_hint

        _plan = plan_changes_hint(db, user_id, language, now=now)
        if _plan:
            lines.append(_plan)
    except Exception:
        pass
    return "\n".join(lines)
