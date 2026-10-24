# app/routers/memory_attachments.py
"""R-021 / M4: upload documents / images / voice from the chat box (I7-owned, mounted under /memory).

JWT identity only; every call is ownership-scoped and consent-gated inside ``services/i7/attachments``.
The whole surface answers 404 FEATURE_DISABLED until SEDI_ATTACHMENTS_ENABLED is set.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.database import get_db
from backend.app.routers.auth_otp import get_current_user
from backend.app.schemas import APIResponse
from backend.app.services.i7 import attachments as att

router = APIRouter()


def _guard() -> None:
    if not att.attachments_enabled():
        raise HTTPException(status_code=404, detail="FEATURE_DISABLED")


def _http(exc: att.AttachmentError) -> HTTPException:
    return HTTPException(status_code=exc.http, detail=exc.code)


def _lang(user: models.User) -> str:
    raw = (getattr(user, "preferred_language", None) or "fa").split("-")[0].lower()
    return raw if raw in ("fa", "en", "ar") else "fa"


@router.post("/attachments", response_model=APIResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _guard()
    limit = max(att.MAX_BYTES.values()) + 1
    data = await file.read(limit)  # never buffer more than the biggest allowed file (+1 to detect overflow)
    try:
        return APIResponse(ok=True, data=att.store_attachment(db, auth_user.id, data, file.filename, file.content_type or ""))
    except att.AttachmentError as exc:
        raise _http(exc)


@router.get("/attachments", response_model=APIResponse)
def list_my_attachments(auth_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    _guard()
    return APIResponse(ok=True, data={"items": att.list_attachments(db, auth_user.id)})


@router.get("/attachments/{attachment_id}", response_model=APIResponse)
def get_my_attachment(
    attachment_id: int, auth_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _guard()
    try:
        return APIResponse(ok=True, data=att.get_attachment(db, auth_user.id, attachment_id))
    except att.AttachmentError as exc:
        raise _http(exc)


@router.post("/attachments/{attachment_id}/process", response_model=APIResponse)
def process_my_attachment(
    attachment_id: int, auth_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Documents/images: read into a bounded summary. Voice: transcribe (the app then sends the transcript as the message)."""
    _guard()
    try:
        return APIResponse(ok=True, data=att.process_attachment(db, auth_user.id, attachment_id, language=_lang(auth_user)))
    except att.AttachmentError as exc:
        raise _http(exc)


@router.post("/attachments/{attachment_id}/confirm", response_model=APIResponse)
def confirm_my_attachment(
    attachment_id: int, auth_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """«Yes, remember this»: the document is added to my life timeline."""
    _guard()
    try:
        return APIResponse(ok=True, data=att.confirm_attachment(db, auth_user.id, attachment_id))
    except att.AttachmentError as exc:
        raise _http(exc)


@router.delete("/attachments/{attachment_id}", response_model=APIResponse)
def delete_my_attachment(
    attachment_id: int, auth_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _guard()
    try:
        return APIResponse(ok=True, data={"deleted": att.delete_attachment(db, auth_user.id, attachment_id)})
    except att.AttachmentError as exc:
        raise _http(exc)
