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
        "I'm here to listen, remember what matters to you, and help you stay on track. "
        "How are you feeling today?"
    ),
    "fa": (
        "سلام{name_part}. من صدی هستم، همراه سلامت شما. "
        "اینجا هستم تا بشنوم، آنچه برای شما مهم است را به خاطر بسپارم و کمکتان کنم. "
        "امروز حالتان چطور است؟"
    ),
    "ar": (
        "مرحبًا{name_part}. أنا صدي، مرافقتك الصحية. "
        "أنا هنا لأستمع وأحتفظ بما يهمك وأساعدك على المتابعة. "
        "كيف تشعر اليوم؟"
    ),
}

_OPENERS: Dict[str, list[str]] = {
    "en": [
        "Welcome back{name_part}. Anything on your mind today?",
        "Good to see you again{name_part}. How can I support you today?",
    ],
    "fa": [
        "خوش آمدید{name_part}. امروز چیزی در ذهن دارید؟",
        "از دیدنتان خوشحالم{name_part}. امروز چطور می‌توانم کمکتان کنم؟",
    ],
    "ar": [
        "مرحبًا بعودتك{name_part}. هل هناك شيء في بالك اليوم؟",
        "سعدت برؤيتك مجددًا{name_part}. كيف يمكنني دعمك اليوم؟",
    ],
}


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


def maybe_proactive_opener(db: Session, user: models.User) -> Optional[str]:
    """Bounded opener: cooldown + not spam; no clinical inference."""
    if user.sedi_intro_completed_at is None:
        return None
    lang = _lang(user)
    last = _last_user_message_at(db, user.id)
    now = datetime.now(timezone.utc)
    if last is not None:
        last_aware = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if now - last_aware < _OPENER_COOLDOWN:
            return None
    options = _OPENERS.get(lang, _OPENERS["en"])
    # Deterministic pick by user id (stable, not random spam).
    pick = options[user.id % len(options)]
    return pick.format(name_part=_name_part(user, lang))


def open_a3_session(db: Session, user: models.User) -> Dict[str, Any]:
    """Return first-intro or proactive opener; mark intro durable when first.

    NEW_DAY is lifecycle context for chat — not a forced session/open greeting.
    Engagement cooldown may still supply a bounded returning opener.
    """
    from backend.app.services.a3_interaction_lifecycle import resolve_interaction_lifecycle
    from backend.app.services.user_context import UserContextService

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
    else:
        # Cooldown engagement only — calendar NEW_DAY does not force greeting.
        proactive = maybe_proactive_opener(db, user)
        if proactive:
            message = proactive

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
