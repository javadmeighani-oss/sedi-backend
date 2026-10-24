"""A3 session open: durable first-contact intro + bounded in-app proactive opener.

Server authority only. No Flutter local storage as intro authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app import models

_OPENER_COOLDOWN = timedelta(hours=12)

_INTRO: Dict[str, str] = {
    "en": (
        "Hello{name_part}. I'm Sedi, your personal health companion. "
        "I listen and remember what matters under your privacy settings, "
        "and I'm here to help you stay on track. "
        "What feels most important or helpful to focus on right now?"
    ),
    "fa": (
        "سلام{name_part}، من صدی‌ام؛ همراه سلامتت. "
        "با رعایت حریم خصوصی‌ات گوش می‌دم، چیزهای مهم رو یادم می‌مونه "
        "و کنارتم تا کمکت کنم. "
        "الان چی برات مهم‌تره که روش تمرکز کنیم؟"
    ),
    "ar": (
        "مرحبًا{name_part}. أنا صدی، مرافقتك الصحية. "
        "أستمع وأحتفظ بما يهمك وفق إعدادات خصوصيتك، "
        "وأنا هنا لأساعدك على المتابعة. "
        "ما الأمر الأهم أو الأكثر فائدة للتركيز عليه الآن؟"
    ),
}

_OPENERS: Dict[str, list[str]] = {
    "en": [
        "{hello} How is your day going? Whatever is on your mind, I'm listening.",
        "{hello} I wanted to check in on you. What's new today?",
    ],
    "fa": [
        "{hello} امروز حالت چطوره؟ هر چی تو ذهنته بگو، من گوش می‌دم.",
        "{hello} دلم می‌خواست احوالت رو بپرسم؛ امروز چه خبر؟",
    ],
    "ar": [
        "{hello} كيف حالك اليوم؟ مهما كان في بالك، أنا أُصغي إليك.",
        "{hello} أحببت أن أطمئن عليك. ما الجديد اليوم؟",
    ],
}


def _hello(lang: str, name_part: str) -> str:
    """Friendly greeting without the stiff «خوش برگشتی»; «جان» only when there is a name."""
    if lang == "fa":
        return f"سلام{name_part} جان!" if name_part else "سلام!"
    if lang == "ar":
        return f"أهلاً{name_part}!"
    return f"Hi{name_part}!"


def _lang(user: models.User) -> str:
    raw = (user.preferred_language or "en").strip().lower()
    return raw if raw in ("en", "fa", "ar") else "en"


def _name_part_from(name: Optional[str], lang: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return ""
    if lang == "fa":
        return f" {cleaned}"
    if lang == "ar":
        return f" {cleaned}"
    return f", {cleaned}"


def _name_part(user: models.User, lang: str) -> str:
    return _name_part_from(getattr(user, "name", None), lang)


def build_first_intro_message(
    user: models.User, *, preferred_name: Optional[str] = None
) -> str:
    lang = _lang(user)
    template = _INTRO.get(lang, _INTRO["en"])
    name = preferred_name if preferred_name is not None else getattr(user, "name", None)
    return template.format(name_part=_name_part_from(name, lang))


def _last_user_message_at(db: Session, user_id: int) -> Optional[datetime]:
    row = (
        db.query(models.Memory.created_at)
        .filter(models.Memory.user_id == user_id)
        .order_by(models.Memory.created_at.desc())
        .first()
    )
    return row[0] if row else None


_REQUEST_MARKERS = (
    "؟", "?", "بده", "بگو", "توضیح", "چیه", "چطور", "چگونه", "چرا", "می‌خوام", "میخوام",
    "explain", "tell me", "how ", "what ", "why ", "please", "can you",
)


def _safe_continuity_snippet(text: Optional[str], *, max_len: int = 80) -> Optional[str]:
    """The user's own short statement as a topic, or None when it is a request/question (never quote those back)."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if any(m in lowered for m in _REQUEST_MARKERS):
        return None
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def authorized_last_eligible_turn(db: Session, user_id: int) -> Optional[models.Memory]:
    """I6/I7 read boundary: user-owned, retention-eligible raw only when memory.read is active."""
    try:
        from backend.app.services.i6.consent_service import PERM_READ, has_permission
        from backend.app.services.i7.retention import query_eligible_raw

        if not has_permission(db, user_id, PERM_READ):
            return None
        rows = query_eligible_raw(db, user_id, limit=1)
        if not rows:
            return None
        row = rows[0]
        if int(getattr(row, "user_id", 0) or 0) != int(user_id):
            return None
        return row
    except Exception:
        return None


def _continuity_opener(lang: str, topic: str, name_part: str) -> str:
    """One sentence recap of the last topic + an invitation to continue or to start something else (R-011)."""
    templates = {
        "en": "{hello} Last time we talked about {topic}. Want to pick that up again, or is something else on your mind today?",
        "fa": "{hello} آخرین بار درباره‌ی {topic} حرف می‌زدیم. می‌خوای همون رو ادامه بدیم، یا امروز یه موضوع دیگه تو ذهنته؟",
        "ar": "{hello} آخر مرة تحدثنا عن {topic}. هل تحب أن نكمل، أم عندك موضوع آخر اليوم؟",
    }
    template = templates.get(lang, templates["en"])
    return template.format(hello=_hello(lang, name_part), topic=topic)


def maybe_proactive_opener(db: Session, user: models.User) -> Optional[str]:
    """Bounded opener: cooldown first, then authorized continuity or generic."""
    if user.sedi_intro_completed_at is None:
        return None
    last = _last_user_message_at(db, user.id)
    now = datetime.now(timezone.utc)
    if last is not None:
        last_aware = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if now - last_aware < _OPENER_COOLDOWN:
            return None
    lang = _lang(user)
    name_part = _name_part(user, lang)
    topic = None
    try:
        from backend.app.services.i7.conversation_recap import recap_topic

        topic = recap_topic(db, user.id, lang, privacy="in_app")
    except Exception:
        topic = None
    if not topic:
        # Raw turns expired/ineligible: the authorized I7 derived continuity may still name the topic.
        try:
            from backend.app.services.i7.derived_continuity import (
                get_bounded_continuity_topic,
                should_project_derived_continuity,
            )

            if should_project_derived_continuity(db, user.id):
                topic = _safe_continuity_snippet(get_bounded_continuity_topic(db, user.id))
        except Exception:
            topic = None
    if not topic:
        try:
            from backend.app.services.i7.privacy_safe_recent_topic import (
                display_phrase_for_topic_label,
                get_privacy_safe_recent_topic_label,
            )

            label = get_privacy_safe_recent_topic_label(db, user.id)
            if label and label != "general":
                topic = display_phrase_for_topic_label(label, lang)
        except Exception:
            topic = None
    if topic:
        return _continuity_opener(lang, topic, name_part)
    options = _OPENERS.get(lang, _OPENERS["en"])
    # Deterministic pick by user id (stable, not random spam).
    pick = options[user.id % len(options)]
    return pick.format(hello=_hello(lang, name_part), name_part=name_part)


def _notification_name_prefix(name: Optional[str], lang: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return ""
    if lang in ("fa", "ar"):
        return f"{cleaned}، "
    return f"{cleaned}, "


def _presence_continuation_opener(
    *,
    lang: str,
    name: Optional[str],
    topic_phrase: Optional[str],
) -> str:
    prefix = _notification_name_prefix(name, lang)
    if topic_phrase:
        templates = {
            "en": (
                "{prefix}last time we talked about {topic}. "
                "Want to pick that up again, or is something else on your mind?"
            ),
            "fa": (
                "{prefix}آخرین بار درباره‌ی {topic} حرف می‌زدیم. "
                "می‌خوای همون رو ادامه بدیم، یا یه موضوع دیگه تو ذهنته؟"
            ),
            "ar": (
                "{prefix}آخر مرة تحدثنا عن {topic}. "
                "هل تحب أن نكمل، أم عندك موضوع آخر؟"
            ),
        }
        body = templates.get(lang, templates["en"]).format(prefix=prefix, topic=topic_phrase)
        return body[:1].upper() + body[1:] if lang == "en" and not prefix else body
    generics = {
        "en": f"{prefix}how are you? We can pick up where we left off, or talk about something new.".strip(),
        "fa": f"{prefix}حالت چطوره؟ می‌تونیم از همون‌جا که موندیم ادامه بدیم یا درباره‌ی یه چیز تازه حرف بزنیم.".strip(),
        "ar": f"{prefix}كيف حالك؟ يمكننا أن نتابع من حيث توقفنا أو نتحدث عن شيء جديد.".strip(),
    }
    body = generics.get(lang, generics["en"])
    return body[:1].upper() + body[1:] if lang == "en" and not prefix else body


def _daily_digest_opener(*, lang: str, name: Optional[str]) -> str:
    """Calm family-specific opener for DAILY_WELLNESS_DIGEST (no raw body)."""
    prefix = _notification_name_prefix(name, lang)
    templates = {
        "en": f"{prefix}Ready for your daily Sedi check-in?".strip(),
        "fa": f"{prefix}برای پیگیری روزانه صدی آماده‌ای؟".strip(),
        "ar": f"{prefix}هل أنت مستعد للمتابعة اليومية مع صدی؟".strip(),
    }
    return templates.get(lang, templates["en"])


def _generic_notification_origin_opener(*, lang: str, name: Optional[str]) -> str:
    prefix = _notification_name_prefix(name, lang)
    templates = {
        "en": f"{prefix}You opened this from a Sedi notification. How would you like to continue?".strip(),
        "fa": f"{prefix}از اعلان صدی آمدی. می‌خواهی از همین‌جا ادامه بدهیم؟".strip(),
        "ar": f"{prefix}فتحت هذا من إشعار صدی. كيف تريد المتابعة؟".strip(),
    }
    return templates.get(lang, templates["en"])


def _care_checkin_opener(*, lang: str, name: Optional[str]) -> str:
    """R-019: the user tapped Sedi's caring check-in. Warm, no event named (chat context carries it privately)."""
    cleaned = (name or "").strip()
    if lang == "fa":
        who = f"{cleaned} جان، " if cleaned else ""
        return f"{who}خوشحالم که اومدی. دلم می‌خواست بدونم این روزها چطوری؛ هرچی تو دلته بگو، من گوش می‌دم."
    if lang == "ar":
        who = f"{cleaned}، " if cleaned else ""
        return f"{who}سعيدة أنك جئت. أردت أن أعرف كيف حالك هذه الأيام؛ قل ما في قلبك، أنا أُصغي."
    who = f"{cleaned}, " if cleaned else ""
    return f"{who}I'm glad you came. I wanted to know how you've been these days; tell me whatever is on your heart, I'm listening."


def build_notification_origin_opener(
    db: Session,
    user: models.User,
    notification: models.Notification,
    *,
    language: str,
    preferred_name: Optional[str] = None,
) -> str:
    """Bounded localized opener from verified notification origin.

    Uses privacy-safe I7 coarse topic for PRESENCE_REENGAGEMENT when available.
    DAILY_WELLNESS_DIGEST gets a calm family-specific opener.
    Never injects raw notification body/context_json.
    """
    from backend.app.services.i10.policy_types import I10SemanticFamily

    lang = language if language in ("en", "fa", "ar") else "en"
    name = preferred_name if preferred_name is not None else getattr(user, "name", None)
    family = (notification.semantic_family or "").strip()

    if family == I10SemanticFamily.DAILY_WELLNESS_DIGEST.value:
        return _daily_digest_opener(lang=lang, name=name)

    if (getattr(notification, "template_key", None) or "") == "care_checkin":
        return _care_checkin_opener(lang=lang, name=name)

    if family == I10SemanticFamily.PRESENCE_REENGAGEMENT.value:
        topic_phrase = None
        try:
            from backend.app.services.i7.privacy_safe_recent_topic import (
                display_phrase_for_topic_label,
                get_privacy_safe_recent_topic_label,
            )

            label = get_privacy_safe_recent_topic_label(db, int(user.id))
            topic_phrase = display_phrase_for_topic_label(label, lang)
        except Exception:
            topic_phrase = None
        if not topic_phrase or label == "general":
            try:
                from backend.app.services.i7.conversation_recap import recap_topic

                # Inside the app (the user already opened it): the recap may be specific.
                topic_phrase = recap_topic(db, int(user.id), lang, privacy="in_app") or None
            except Exception:
                topic_phrase = None
        return _presence_continuation_opener(
            lang=lang, name=name, topic_phrase=topic_phrase
        )

    # Other families: short localized acknowledgment only (no clinical reinterpretation).
    return _generic_notification_origin_opener(lang=lang, name=name)


def open_a3_session(
    db: Session,
    user: models.User,
    *,
    source_notification_id: Optional[int] = None,
    device_timezone: Optional[str] = None,
) -> Dict[str, Any]:
    """Return first-intro or proactive opener; mark intro durable when first.

    Optional ``source_notification_id`` (JWT-owned) yields a notification-origin
    continuation opener after intro priority. Does not write Memory / fake user turns.
    """
    from backend.app.services.a3_interaction_lifecycle import resolve_interaction_lifecycle
    from backend.app.services.i6.consent_service import ensure_default_memory_enabled
    from backend.app.services.user_context import UserContextService

    ensure_default_memory_enabled(db, int(user.id), commit=True)
    try:
        from backend.app.services.chat_commands import adopt_device_timezone

        adopt_device_timezone(db, int(user.id), device_timezone)
    except Exception:
        db.rollback()

    verified_notification: Optional[models.Notification] = None
    if source_notification_id is not None:
        from backend.app.services.gate4.interaction_event_service import (
            verify_notification_belongs_to_user,
        )
        from backend.app.services.gate4.notification_chat_context import (
            build_safe_chat_context,
        )

        verified_notification = verify_notification_belongs_to_user(
            db,
            user_id=int(user.id),
            notification_id=int(source_notification_id),
        )
        # Build safe context for authority/leakage guarantees (never returned raw).
        build_safe_chat_context(
            verified_notification,
            db=db,
            viewer_user_id=int(user.id),
        )

    lang = _lang(user)
    first_intro = user.sedi_intro_completed_at is None
    message = ""
    proactive: Optional[str] = None
    pack = None
    preferred_name: Optional[str] = None
    try:
        pack = UserContextService(db).get_user_context(int(user.id))
        if pack and getattr(pack, "preferred_name", None) and str(pack.preferred_name).strip():
            preferred_name = str(pack.preferred_name).strip()
        if pack and getattr(pack, "language", None) and str(pack.language).strip():
            pl = str(pack.language).strip().lower()
            if pl.startswith("fa"):
                lang = "fa"
            elif pl.startswith("ar"):
                lang = "ar"
            elif pl.startswith("en"):
                lang = "en"
    except Exception:
        pack = None

    lifecycle = resolve_interaction_lifecycle(db, user, user_context_pack=pack)

    if first_intro:
        message = build_first_intro_message(user, preferred_name=preferred_name)
        user.sedi_intro_completed_at = datetime.now(timezone.utc)
        db.add(user)
        db.commit()
        db.refresh(user)
        # Re-resolve after stamp so response reflects completed intro.
        lifecycle = resolve_interaction_lifecycle(db, user, user_context_pack=pack)
    elif verified_notification is not None:
        # Explicit notification-origin open bypasses ordinary 12h proactive cooldown.
        message = build_notification_origin_opener(
            db,
            user,
            verified_notification,
            language=lang,
            preferred_name=preferred_name,
        )
        proactive = message
    else:
        # Cooldown engagement only — calendar NEW_DAY does not force greeting.
        proactive = maybe_proactive_opener(db, user)
        if proactive:
            message = proactive

    try:
        from backend.app.services.auth_session_policy import record_session_open_presence

        record_session_open_presence(db, user.id)
        db.commit()
    except Exception:
        pass

    continued = verified_notification is not None
    return {
        "message": message,
        "language": lang,
        "user_id": user.id,
        "first_intro": first_intro,
        "intro_completed": user.sedi_intro_completed_at is not None,
        "proactive_opener": proactive if not first_intro else None,
        "interaction_lifecycle": lifecycle.as_dict(),
        "known_profile_keys": list(lifecycle.known_profile_keys),
        "timezone_authority_gap": lifecycle.timezone_authority_gap,
        "continued_from_notification": continued,
        "source_notification_id": (
            int(verified_notification.id) if verified_notification is not None else None
        ),
    }


def user_facing_known_facts(db: Session, user_id: int) -> list[dict]:
    """Safe I7/profile facts for A3 card — no raw memory/embeddings."""
    from backend.app.services.user_profile_fact_service import list_profile_facts

    items = list_profile_facts(db, user_id)
    out: list[dict] = []
    for item in items:
        fact_type = str(item.get("fact_type") or "").strip()
        value = item.get("value")
        if not fact_type or value is None:
            continue
        text = value if isinstance(value, str) else str(value)
        text = text.strip()
        if not text:
            continue
        out.append(
            {
                "category": fact_type,
                "text": text,
            }
        )
    return out
