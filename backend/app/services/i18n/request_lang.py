from __future__ import annotations

from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i18n.locale import DEFAULT_LANG, normalize_lang, parse_accept_language


def resolve_request_lang(
    request: Request,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
) -> str:
    """
    Resolve request language for V1:
      1) If Accept-Language header is present -> use it (en|fa|ar)
      2) Else if user_id + db are provided -> use user.preferred_language (normalized)
      3) Else -> DEFAULT_LANG (en)

    Note: parse_accept_language() always falls back to en for unknown values.
    We only call it when the header is actually present (non-empty),
    to allow fallback to user preference when header is missing.
    """
    raw = request.headers.get("Accept-Language")
    if raw and raw.strip():
        return parse_accept_language(raw)

    if db is not None and user_id is not None:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user and getattr(user, "preferred_language", None):
            return normalize_lang(user.preferred_language)

    return DEFAULT_LANG

