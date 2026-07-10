"""Provider-neutral voice-call request foundation — no real telephony."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags

VOICE_MESSAGE_TEMPLATES = {
    "caregiver_no_response_check": {
        "fa": (
            "سلام، این پیام از طرف سدی است. "
            "کاربر پاسخی به تماس‌های مکرر ما نداده است. "
            "لطفاً وضعیت ایشان را بررسی کنید. "
            "این پیام به معنای تأیید اورژانس پزشکی نیست."
        ),
        "en": (
            "Hello, this is Sedi. "
            "The user has not responded to repeated contact attempts. "
            "Please check on them when you can. "
            "This is not a confirmed medical emergency."
        ),
        "ar": (
            "مرحباً، هذه رسالة من سيدي. "
            "لم يستجب المستخدم لمحاولات الاتصال المتكررة. "
            "يرجى التحقق من حالته عندما تتمكن. "
            "هذه ليست حالة طوارئ طبية مؤكدة."
        ),
    },
}


def get_voice_message_template(template_key: str, language: str) -> str:
    templates = VOICE_MESSAGE_TEMPLATES.get(template_key, {})
    lang = language if language in templates else "en"
    return templates.get(lang) or templates.get("en", "")


def create_voice_call_request(
    db: Session,
    *,
    owner_user_id: int,
    caregiver_id: int,
    template_key: str,
    language: str = "fa",
    escalation_id: Optional[int] = None,
) -> models.VoiceCallRequest:
    status = "suppressed"
    if feature_flags.voice_call_requests_enabled() and feature_flags.voice_call_provider_enabled():
        status = "pending"

    row = models.VoiceCallRequest(
        owner_user_id=owner_user_id,
        caregiver_id=caregiver_id,
        escalation_id=escalation_id,
        template_key=template_key,
        language=language,
        status=status,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
