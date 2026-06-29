# app/routers/auth_otp.py – Stage 25 Phone OTP endpoints
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo, ApiResponseV1
from backend.app.schemas.auth_otp import OtpRequestIn, OtpVerifyIn, TokenOut, MeUpdateIn
from backend.app.core.security import verify_token
from backend.app.services import auth_otp_service as svc
from backend.app.services.user_profile_service import apply_profile_update, build_me_response

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


def _me_out(user: models.User, db: Session) -> dict:
    """Build GET/PATCH /auth/me response payload (no user_id from client)."""
    return build_me_response(db, user)


def _handle_request_otp(
    body: OtpRequestIn,
    request: Request,
    db: Session,
) -> ApiResponseV1:
    """Internal: request OTP logic (shared by /request_otp and /otp/request)."""
    accept_language = request.headers.get("Accept-Language")
    ok, err, dev_code = svc.request_otp(db, body.phone, accept_language=accept_language)
    if not ok:
        return APIResponse(ok=False, error=ErrorInfo(code="OTP_REQUEST_FAILED", message=err))
    data: dict = {"ok": True, "next": "verify_otp"}
    if dev_code:
        data["dev_code"] = dev_code
    return APIResponse(ok=True, data=data)


@router.post("/request_otp", response_model=ApiResponseV1)
def request_otp(
    body: OtpRequestIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Request OTP for phone. Rate-limited; SMS via gateway or [OTP_DEV] log. Accept-Language for OTP text.
    When SMS is not sent (dev mode or gateway unavailable), dev_code is returned for testing."""
    return _handle_request_otp(body, request, db)


@router.post("/otp/request", response_model=ApiResponseV1)
def otp_request_alias(
    body: OtpRequestIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Alias for /request_otp. Use POST /auth/otp/request for REST-style paths."""
    return _handle_request_otp(body, request, db)


def _handle_verify_otp(
    body: OtpVerifyIn,
    request: Request,
    db: Session,
) -> ApiResponseV1:
    """Internal: verify OTP logic (shared by /verify_otp and /otp/verify)."""
    user, err = svc.verify_otp(db, body.phone, body.code)
    if err:
        code = "OTP_INVALID"
        if "expired" in err.lower():
            code = "OTP_EXPIRED"
        elif "attempts" in err.lower():
            code = "TOO_MANY_ATTEMPTS"
        return APIResponse(ok=False, error=ErrorInfo(code=code, message=err))
    device_info = request.headers.get("X-Device-Info") if request else None
    ip = (request.headers.get("X-Client-IP") or (request.client.host if request.client else None)) if request else None
    access_token, refresh_token, expires_in = svc.issue_tokens(db, user, device_info=device_info, ip=ip)
    payload = TokenOut(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    ).model_dump()
    payload["user_id"] = user.id
    payload["phone"] = user.phone
    payload["language"] = user.preferred_language or "en"
    return APIResponse(ok=True, data=payload)


@router.post("/verify_otp", response_model=ApiResponseV1)
def verify_otp(
    body: OtpVerifyIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Verify OTP; create user if missing; return tokens. Optional X-Device-Info / X-Client-IP for audit."""
    return _handle_verify_otp(body, request, db)


@router.post("/otp/verify", response_model=ApiResponseV1)
def otp_verify_alias(
    body: OtpVerifyIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Alias for /verify_otp. Use POST /auth/otp/verify for REST-style paths."""
    return _handle_verify_otp(body, request, db)


@router.get("/me", response_model=ApiResponseV1)
def auth_me(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return current user unified profile (requires access token)."""
    return APIResponse(ok=True, data=_me_out(user, db))


@router.patch("/me", response_model=ApiResponseV1)
def patch_auth_me(
    body: MeUpdateIn,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update authenticated user profile (JWT-only; never accepts user_id in body)."""
    user = apply_profile_update(db, user, body)
    return APIResponse(ok=True, data=_me_out(user, db))


@router.post("/refresh", response_model=ApiResponseV1)
def refresh_tokens(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
):
    """Exchange refresh token for new access + new refresh; used token is revoked (rotation)."""
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    refresh_plain = credentials.credentials
    device_info = request.headers.get("User-Agent") if request else None
    ip = request.client.host if request and request.client else None
    access_token, new_refresh, expires_in = svc.rotate_refresh_token(
        db, refresh_plain, device_info=device_info, ip=ip
    )
    if access_token is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return APIResponse(
        ok=True,
        data=TokenOut(
            access_token=access_token,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=expires_in,
        ).model_dump(),
    )


@router.post("/logout", response_model=ApiResponseV1)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
):
    """Revoke refresh token (send as Bearer)."""
    if not credentials or credentials.scheme != "Bearer":
        return APIResponse(ok=True, data={"revoked": False})  # nothing to revoke
    revoked = svc.revoke_refresh_token(db, credentials.credentials)
    return APIResponse(ok=True, data={"revoked": revoked})
