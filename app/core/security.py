# app/core/security.py
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "sedi_secret_key_2025"  # بعداً با ENV جایگزین میشه
ALGORITHM = "HS256"


def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=1)):
    """تولید Access Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta = timedelta(days=7)):
    """تولید Refresh Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire, "scope": "refresh_token"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    """بررسی اعتبار Token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
