from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.core.passkey_utils import hash_passkey, verify_passkey

router = APIRouter()

_failed_attempts = {}
LOCK_THRESHOLD = 5
LOCK_SECONDS = 300


def _record_failure(user_id: int):
    rec = _failed_attempts.get(user_id) or {"count": 0, "locked_until": None}
    rec["count"] += 1
    if rec["count"] >= LOCK_THRESHOLD:
        rec["locked_until"] = datetime.utcnow() + timedelta(seconds=LOCK_SECONDS)
    _failed_attempts[user_id] = rec


def _is_locked(user_id: int) -> bool:
    rec = _failed_attempts.get(user_id)
    if not rec:
        return False
    locked_until = rec.get("locked_until")
    if locked_until and datetime.utcnow() < locked_until:
        return True
    if locked_until and datetime.utcnow() >= locked_until:
        _failed_attempts[user_id] = {"count": 0, "locked_until": None}
    return False


@router.post("/set-passkey", response_model=APIResponse)
def set_passkey(user_id: int, passkey: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    if not passkey or len(passkey.strip()) < 1:
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_KEY", message="Passkey cannot be empty."))

    hashed = hash_passkey(passkey.strip())
    user.passkey = hashed
    db.commit()
    db.refresh(user)

    return APIResponse(ok=True, data={"user_id": user.id, "passkey_set": True})


@router.post("/verify-passkey", response_model=APIResponse)
def verify_passkey_endpoint(user_id: int, passkey: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    if _is_locked(user_id):
        return APIResponse(ok=False, error=ErrorInfo(code="LOCKED", message="Too many failed attempts. Try later."))

    ok = verify_passkey(passkey, user.passkey or "")
    if not ok:
        _record_failure(user_id)
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_KEY", message="Incorrect passkey."))

    _failed_attempts[user_id] = {"count": 0, "locked_until": None}
    return APIResponse(ok=True, data={"user_id": user.id, "verified": True})
