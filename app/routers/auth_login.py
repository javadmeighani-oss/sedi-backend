# app/routers/auth_login.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from random import randint
import requests

from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.core.security import create_access_token, create_refresh_token, verify_token

router = APIRouter()

otp_store = {}  # حافظه موقت برای PIN


@router.post("/request-pin", response_model=APIResponse)
def request_pin(phone: str, db: Session = Depends(get_db)):
    """ارسال PIN چهار رقمی از طریق Gateway داخلی صدی"""
    user = db.query(models.User).filter(models.User.phone == phone).first()
    if not user:
        user = models.User(phone=phone, created_at=datetime.utcnow())
        db.add(user)
        db.commit()
        db.refresh(user)

    pin_code = str(randint(1000, 9999))
    otp_store[phone] = {"pin": pin_code, "expires": datetime.utcnow() + timedelta(minutes=5)}

    try:
        res = requests.post("http://127.0.0.1:8000/sms/send", json={
            "to": phone,
            "message": f"Your Sedi verification code is {pin_code}. It will expire in 5 minutes."
        })
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail="SMS gateway error.")
    except Exception as e:
        print(f"[SMS Gateway Error] {e}")
        return APIResponse(ok=False, error=ErrorInfo(code="SMS_FAILED", message="Failed to send SMS."))

    print(f"[LOGIN] PIN sent to {phone}: {pin_code}")
    return APIResponse(ok=True, data={"sent": True, "expires_in": 300})


@router.post("/verify-pin", response_model=APIResponse)
def verify_pin(phone: str, pin: str, db: Session = Depends(get_db)):
    """تأیید PIN و صدور JWT Token"""
    if phone not in otp_store:
        return APIResponse(ok=False, error=ErrorInfo(code="PIN_NOT_REQUESTED", message="PIN not requested."))

    data = otp_store[phone]
    if datetime.utcnow() > data["expires"]:
        del otp_store[phone]
        return APIResponse(ok=False, error=ErrorInfo(code="PIN_EXPIRED", message="PIN expired."))

    if pin != data["pin"]:
        return APIResponse(ok=False, error=ErrorInfo(code="PIN_INVALID", message="Incorrect PIN."))

    user = db.query(models.User).filter(models.User.phone == phone).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    del otp_store[phone]  # حذف پس از موفقیت

    access_token = create_access_token({"user_id": user.id})
    refresh_token = create_refresh_token({"user_id": user.id})

    print(f"[LOGIN SUCCESS] User {user.phone} verified successfully.")

    return APIResponse(ok=True, data={
        "user_id": user.id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 3600
    })


@router.post("/refresh-token", response_model=APIResponse)
def refresh_token(token: str):
    """تولید Access Token جدید با استفاده از Refresh Token"""
    payload = verify_token(token)
    if not payload or payload.get("scope") != "refresh_token":
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_TOKEN", message="Invalid refresh token."))

    user_id = payload.get("user_id")
    new_access = create_access_token({"user_id": user_id})
    return APIResponse(ok=True, data={"access_token": new_access, "expires_in": 3600})


@router.get("/verify-token", response_model=APIResponse)
def verify_access(token: str):
    """بررسی اعتبار توکن دسترسی"""
    payload = verify_token(token)
    if not payload:
        return APIResponse(ok=False, error=ErrorInfo(code="EXPIRED", message="Token expired or invalid."))
    return APIResponse(ok=True, data={"valid": True, "user_id": payload.get("user_id")})
