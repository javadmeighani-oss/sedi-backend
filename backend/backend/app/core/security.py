# app/core/security.py
import logging
import os
import jwt
from datetime import datetime, timedelta

ALGORITHM = "HS256"

# Canonical JWT signing key: env SECRET_KEY, backward-compat JWT_SECRET. No hardcoded fallback in production.
_raw = os.environ.get("SECRET_KEY") or os.environ.get("JWT_SECRET")
_debug = os.environ.get("DEBUG", "").strip().lower() in ("", "1", "true", "yes")
_env_prod = os.environ.get("ENV", "").strip().lower() == "prod"
if not _raw:
    if not _debug or _env_prod:
        raise RuntimeError("SECRET_KEY must be set when DEBUG=false or ENV=prod")
    _raw = "x" * 64  # dev-only fallback; 64 bytes to avoid InsecureKeyLengthWarning
_key_bytes = _raw.encode("utf-8")
if not _debug or _env_prod:
    if len(_key_bytes) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 bytes in production (recommended 64)")
SECRET_KEY = _raw
logging.getLogger(__name__).info("[auth] SECRET_KEY length=%s", len(_key_bytes))


def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=1)):
    """Generate Access Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta = timedelta(days=7)):
    """Generate Refresh Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire, "scope": "refresh_token"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    """Verify Token validity"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
