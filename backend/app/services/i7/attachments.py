# backend.app.services.i7.attachments
"""R-021 / M4: documents, images and voice the user gives Sedi from the chat box (I7 memory sources).

Principles
- Owner-scoped, consent-gated (memory.write to store, memory.forget to delete), size/type/magic-byte checked, SHA-256 deduped.
- ``AttachmentStore`` is the only place that touches bytes (PostgreSQL bytea today; object storage later, no reader change).
- Documents/images are READ by a vision model into a bounded, validated structure (summary + printed findings); nothing
  becomes a fact automatically. The user CONFIRMS it and only then it lands on the I7 timeline (kind medical_document).
- Audio is TRANSCRIBED; the transcript goes back to the chat as the user's message and the audio bytes are dropped.
- The whole feature is off unless SEDI_ATTACHMENTS_ENABLED is set (router level).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app import models

MAX_BYTES = {"image": 5 * 1024 * 1024, "audio": 5 * 1024 * 1024, "document": 8 * 1024 * 1024}
MAX_UPLOADS_PER_DAY = 40
MAX_TOTAL_BYTES_PER_USER = 120 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 4000
MAX_SUMMARY_CHARS = 600
MAX_FINDINGS = 40
MAX_FIELD_CHARS = 60

_MIME_KIND = {
    "image/jpeg": "image", "image/png": "image", "image/webp": "image",
    "application/pdf": "document",
    "audio/mpeg": "audio", "audio/mp4": "audio", "audio/m4a": "audio", "audio/x-m4a": "audio", "audio/aac": "audio",
    "audio/wav": "audio", "audio/x-wav": "audio", "audio/webm": "audio", "audio/ogg": "audio",
}


class AttachmentError(Exception):
    def __init__(self, code: str, http: int = 400):
        super().__init__(code)
        self.code = code
        self.http = http


def attachments_enabled() -> bool:
    return os.environ.get("SEDI_ATTACHMENTS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _has(db: Session, user_id: int, perm: str) -> bool:
    from backend.app.services.i6.consent_service import has_permission

    try:
        return bool(has_permission(db, user_id, perm))
    except Exception:
        return False


def sniff_kind(data: bytes) -> Optional[str]:
    """Kind from the file's own magic bytes (never trust the declared MIME alone)."""
    h = data[:16]
    if h[:3] == b"\xff\xd8\xff" or h[:8] == b"\x89PNG\r\n\x1a\n" or (h[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        return "image"
    if h[:5] == b"%PDF-":
        return "document"
    if (
        h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf1", b"\xff\xf9") or data[4:8] == b"ftyp"
        or h[:4] == b"OggS" or h[:4] == b"\x1a\x45\xdf\xa3" or (h[:4] == b"RIFF" and data[8:12] == b"WAVE")
    ):
        return "audio"
    return None


def _safe_name(name: Optional[str]) -> Optional[str]:
    n = os.path.basename((name or "").replace("\\", "/")).strip()
    n = "".join(c for c in n if c.isalnum() or c in " ._-()")[:128]
    return n or None


def _meta(row: models.UserAttachment, *, with_findings: bool = False) -> dict[str, Any]:
    out = {
        "id": int(row.id),
        "kind": row.kind,
        "mime": row.mime,
        "filename": row.filename,
        "size_bytes": int(row.size_bytes),
        "status": row.status,
        "summary": row.summary,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
        "confirmed": row.status == "confirmed",
    }
    if with_findings:
        try:
            out["findings"] = json.loads(row.extracted_json) if row.extracted_json else None
        except ValueError:
            out["findings"] = None
    return out


class AttachmentStore:
    """Byte storage seam. Replace the two methods to move files to object storage; nothing else changes."""

    @staticmethod
    def put(row: models.UserAttachment, data: bytes) -> None:
        row.content = data

    @staticmethod
    def get(row: models.UserAttachment) -> Optional[bytes]:
        return bytes(row.content) if row.content is not None else None

    @staticmethod
    def drop(row: models.UserAttachment) -> None:
        row.content = None


def store_attachment(
    db: Session, user_id: int, data: bytes, filename: Optional[str], declared_mime: str
) -> dict[str, Any]:
    from backend.app.services.i6.consent_service import PERM_WRITE

    if not _has(db, user_id, PERM_WRITE):
        raise AttachmentError("MEMORY_WRITE_NOT_GRANTED", 403)
    mime = (declared_mime or "").split(";")[0].strip().lower()
    kind = _MIME_KIND.get(mime)
    if kind is None:
        raise AttachmentError("UNSUPPORTED_TYPE", 415)
    if not data:
        raise AttachmentError("EMPTY_FILE", 400)
    if len(data) > MAX_BYTES[kind]:
        raise AttachmentError("FILE_TOO_LARGE", 413)
    if sniff_kind(data) != kind:
        raise AttachmentError("CONTENT_DOES_NOT_MATCH_TYPE", 415)
    since = _utcnow() - timedelta(days=1)
    today = db.query(func.count(models.UserAttachment.id)).filter(
        models.UserAttachment.user_id == user_id, models.UserAttachment.created_at >= since
    ).scalar() or 0
    if today >= MAX_UPLOADS_PER_DAY:
        raise AttachmentError("DAILY_LIMIT", 429)
    total = db.query(func.coalesce(func.sum(models.UserAttachment.size_bytes), 0)).filter(
        models.UserAttachment.user_id == user_id
    ).scalar() or 0
    if int(total) + len(data) > MAX_TOTAL_BYTES_PER_USER:
        raise AttachmentError("STORAGE_LIMIT", 413)
    digest = hashlib.sha256(data).hexdigest()
    existing = (
        db.query(models.UserAttachment)
        .filter(models.UserAttachment.user_id == user_id, models.UserAttachment.sha256 == digest)
        .first()
    )
    if existing is not None:
        return _meta(existing, with_findings=True)
    now = _utcnow()
    row = models.UserAttachment(
        user_id=user_id, kind=kind, mime=mime, filename=_safe_name(filename), size_bytes=len(data),
        sha256=digest, status="stored", created_at=now, updated_at=now,
    )
    AttachmentStore.put(row, data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _meta(row)


def _owned(db: Session, user_id: int, attachment_id: int) -> models.UserAttachment:
    row = (
        db.query(models.UserAttachment)
        .filter(models.UserAttachment.id == attachment_id, models.UserAttachment.user_id == user_id)
        .first()
    )
    if row is None:
        raise AttachmentError("NOT_FOUND", 404)
    return row


def list_attachments(db: Session, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    from backend.app.services.i6.consent_service import PERM_READ

    if not _has(db, user_id, PERM_READ):
        return []
    rows = (
        db.query(models.UserAttachment)
        .filter(models.UserAttachment.user_id == user_id)
        .order_by(models.UserAttachment.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [_meta(r) for r in rows]


def get_attachment(db: Session, user_id: int, attachment_id: int) -> dict[str, Any]:
    from backend.app.services.i6.consent_service import PERM_READ

    if not _has(db, user_id, PERM_READ):
        raise AttachmentError("MEMORY_READ_NOT_GRANTED", 403)
    return _meta(_owned(db, user_id, attachment_id), with_findings=True)


# ---------------------------------------------------------------------------------------------- model calls (injected in tests)
_ANALYZE_PROMPT = """You read ONE medical/health document or photo a user gave their health companion. Output JSON only:
{"document_type":"lab_result|prescription|report|imaging|other","summary":"<=500 chars, neutral, in the user's language",
 "date":"YYYY-MM-DD or empty","findings":[{"name":"","value":"","unit":"","flag":"low|high|normal|"}],"medications":["names as printed"]}
Rules: copy only what is PRINTED or clearly visible; never interpret, diagnose or advise; unknown fields stay empty;
at most 40 findings; if the image is not a health document, set document_type "other" and describe it in one neutral sentence."""


def _analyze_with_openai(data: bytes, mime: str, language: str) -> str:
    from backend.app.core.conversation import prompts

    b64 = base64.b64encode(data).decode("ascii")
    part: dict[str, Any]
    if mime == "application/pdf":
        part = {"type": "input_file", "filename": "document.pdf", "file_data": f"data:application/pdf;base64,{b64}"}
    else:
        part = {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}
    model = (os.environ.get("SEDI_ATTACHMENT_VISION_MODEL") or "").strip() or prompts.resolve_openai_chat_model()
    resp = prompts.client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": _ANALYZE_PROMPT},
            {"role": "user", "content": [{"type": "input_text", "text": f"Language: {language}"}, part]},
        ],
        reasoning={"effort": "low"},
    )
    return (resp.output_text or "").strip()


def _transcribe_with_openai(data: bytes, filename: str, mime: str, language: str) -> str:
    from backend.app.core.conversation import prompts

    model = (os.environ.get("SEDI_TRANSCRIBE_MODEL") or "").strip() or "gpt-4o-mini-transcribe"
    kwargs: dict[str, Any] = {"model": model, "file": (filename or "voice.m4a", data, mime)}
    if language in ("fa", "ar", "en"):
        kwargs["language"] = language
    return (prompts.client.audio.transcriptions.create(**kwargs).text or "").strip()


def validate_document_findings(raw: str) -> Optional[dict[str, Any]]:
    """Strict, bounded structure or None. Anything unexpected is dropped, never repaired."""
    try:
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, TypeError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None

    def s(v: Any, n: int = MAX_FIELD_CHARS) -> str:
        return " ".join(str(v or "").split())[:n]

    doc_type = s(data.get("document_type"), 20)
    if doc_type not in ("lab_result", "prescription", "report", "imaging", "other"):
        doc_type = "other"
    summary = s(data.get("summary"), MAX_SUMMARY_CHARS)
    if not summary:
        return None
    date = s(data.get("date"), 10)
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        date = ""
    findings = []
    for f in (data.get("findings") or [])[:MAX_FINDINGS]:
        if not isinstance(f, dict) or not s(f.get("name")):
            continue
        flag = s(f.get("flag"), 6)
        findings.append({"name": s(f.get("name")), "value": s(f.get("value")), "unit": s(f.get("unit"), 20),
                         "flag": flag if flag in ("low", "high", "normal") else ""})
    meds = [s(m) for m in (data.get("medications") or [])[:20] if s(m)]
    return {"document_type": doc_type, "summary": summary, "date": date, "findings": findings, "medications": meds}


def process_attachment(
    db: Session,
    user_id: int,
    attachment_id: int,
    *,
    language: str = "fa",
    analyzer: Optional[Callable[[bytes, str, str], str]] = None,
    transcriber: Optional[Callable[[bytes, str, str], str]] = None,
) -> dict[str, Any]:
    from backend.app.services.i6.consent_service import PERM_WRITE

    if not _has(db, user_id, PERM_WRITE):
        raise AttachmentError("MEMORY_WRITE_NOT_GRANTED", 403)
    row = _owned(db, user_id, attachment_id)
    data = AttachmentStore.get(row)
    if data is None:
        raise AttachmentError("CONTENT_NOT_AVAILABLE", 409)
    row.status = "processing"
    db.commit()
    try:
        if row.kind == "audio":
            text = (transcriber or (lambda b, n, m: _transcribe_with_openai(b, n, m, language)))(
                data, row.filename or "voice.m4a", row.mime
            )
            text = " ".join(text.split())[:MAX_TRANSCRIPT_CHARS]
            if not text:
                raise ValueError("empty transcript")
            row.summary = text
            row.status = "ready"
            AttachmentStore.drop(row)  # the voice itself is not kept — only the words the user said
        else:
            raw = (analyzer or (lambda b, m, lang: _analyze_with_openai(b, m, lang)))(data, row.mime, language)
            parsed = validate_document_findings(raw)
            if parsed is None:
                raise ValueError("unreadable document")
            row.summary = parsed["summary"]
            row.extracted_json = json.dumps(parsed, ensure_ascii=False)
            row.status = "ready"
    except Exception:
        row.status = "failed"
        row.processed_at = _utcnow()
        db.commit()
        raise AttachmentError("PROCESSING_FAILED", 502)
    row.processed_at = _utcnow()
    db.commit()
    db.refresh(row)
    out = _meta(row, with_findings=True)
    if row.kind == "audio":
        out["transcript"] = row.summary
    return out


def confirm_attachment(db: Session, user_id: int, attachment_id: int) -> dict[str, Any]:
    """The user says «yes, remember this»: the document lands on the I7 timeline (never automatic)."""
    from backend.app.services.i7.life_events import record_life_event

    row = _owned(db, user_id, attachment_id)
    if row.kind == "audio" or row.status not in ("ready", "confirmed") or not row.summary:
        raise AttachmentError("NOT_CONFIRMABLE", 409)
    if row.confirmed_event_id:
        return _meta(row, with_findings=True)
    findings = json.loads(row.extracted_json) if row.extracted_json else {}
    when = None
    if findings.get("date"):
        try:
            when = datetime.strptime(findings["date"], "%Y-%m-%d")
        except ValueError:
            when = None
    ev = record_life_event(
        db, user_id, kind="medical_document", summary=row.summary[:140], occurred_at=when,
        precision="day" if when else "approx", subject="self", source="document",
        evidence=findings.get("document_type"),
    )
    if ev is None:
        raise AttachmentError("MEMORY_WRITE_NOT_GRANTED", 403)
    row.confirmed_event_id = ev["id"]
    row.status = "confirmed"
    db.commit()
    db.refresh(row)
    return _meta(row, with_findings=True)


def delete_attachment(db: Session, user_id: int, attachment_id: int) -> bool:
    from backend.app.services.i6.consent_service import PERM_FORGET
    from backend.app.services.i7.life_events import delete_life_event

    if not _has(db, user_id, PERM_FORGET):
        raise AttachmentError("MEMORY_FORGET_NOT_GRANTED", 403)
    row = _owned(db, user_id, attachment_id)
    if row.confirmed_event_id:
        delete_life_event(db, user_id, int(row.confirmed_event_id))  # forgetting a document forgets what came from it
    db.delete(row)
    db.commit()
    return True
