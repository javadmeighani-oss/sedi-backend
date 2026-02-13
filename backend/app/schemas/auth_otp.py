# app/schemas/auth_otp.py – Stage 25 Phone OTP
from pydantic import BaseModel
from typing import Optional


class OtpRequestIn(BaseModel):
    phone: str


class OtpRequestOut(BaseModel):
    ok: bool
    next: str = "verify_otp"


class OtpVerifyIn(BaseModel):
    phone: str
    code: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    user_id: int
    phone: Optional[str] = None
    display_name: Optional[str] = None
    language: Optional[str] = None
