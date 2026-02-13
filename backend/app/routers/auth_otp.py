# app/routers/auth_otp.py – Stage 25 Phone OTP endpoints
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.auth_otp import OtpRequestIn, OtpVerifyIn, TokenOut, MeOut
from backend.app.core.security import verify_token
from backend.app.services import auth_otp_service as svc

router = APIRouter()
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    """Require Bearer access token and return current user. Raises 401 if invalid."""
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/request_otp", response_model=APIResponse)
def request_otp(
    body: OtpRequestIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Request OTP for phone. Rate-limited; SMS via gateway or [OTP_DEV] log. Accept-Language for OTP text."""
    accept_language = request.headers.get("Accept-Language")
    ok, err = svc.request_otp(db, body.phone, accept_language=accept_language)
    if not ok:
        return APIResponse(ok=False, error=ErrorInfo(code="OTP_REQUEST_FAILED", message=err))
    return APIResponse(ok=True, data={"ok": True, "next": "verify_otp"})


@router.post("/verify_otp", response_model=APIResponse)
def verify_otp(body: OtpVerifyIn, db: Session = Depends(get_db)):
    """Verify OTP; create user if missing; return tokens."""
    user, err = svc.verify_otp(db, body.phone, body.code)
    if err:
        code = "OTP_INVALID"
        if "expired" in err.lower():
            code = "OTP_EXPIRED"
        elif "attempts" in err.lower():
            code = "TOO_MANY_ATTEMPTS"
        return APIResponse(ok=False, error=ErrorInfo(code=code, message=err))
    access_token, refresh_token, expires_in = svc.issue_tokens(db, user)
    return APIResponse(
        ok=True,
        data=TokenOut(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        ).model_dump(),
    )


@router.get("/me", response_model=APIResponse)
def auth_me(user: models.User = Depends(get_current_user)):
    """Return current user info (requires access token)."""
    # display_name: prefer name from user_profile_knowledge or user.name
    return APIResponse(
        ok=True,
        data=MeOut(
            user_id=user.id,
            phone=user.phone,
            display_name=user.name,
            language=user.preferred_language or "en",
        ).model_dump(),
    )


@router.post("/refresh", response_model=APIResponse)
def refresh_tokens(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
):
    """Exchange refresh token for new access token (Bearer refresh_token)."""
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    refresh_plain = credentials.credentials
    user = svc.get_user_by_refresh_token(db, refresh_plain)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    access_token, new_refresh, expires_in = svc.issue_tokens(db, user)
    # Optional: revoke old refresh (rotation). For minimal we issue new and leave old valid.
    return APIResponse(
        ok=True,
        data=TokenOut(
            access_token=access_token,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=expires_in,
        ).model_dump(),
    )


@router.post("/logout", response_model=APIResponse)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
):
    """Revoke refresh token (send as Bearer)."""
    if not credentials or credentials.scheme != "Bearer":
        return APIResponse(ok=True, data={"revoked": False})  # nothing to revoke
    revoked = svc.revoke_refresh_token(db, credentials.credentials)
    return APIResponse(ok=True, data={"revoked": revoked})
