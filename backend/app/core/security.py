# app/core/security.py
import os
import jwt
from datetime import datetime, timedelta

ALGORITHM = "HS256"

# JWT signing key; prefer env in production (Stage 25).
SECRET_KEY = os.environ.get("JWT_SECRET", "sedi_secret_key_2025")


def create_access_token(data: dict, expires_delta: timedelta = timedelta(minutes=60)):
    """Generate short-lived access JWT (default 60 min)."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta = timedelta(days=7)):
    """Legacy: JWT refresh (used by auth_login). Stage 25 uses opaque refresh tokens in DB."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire, "scope": "refresh_token"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    """Verify JWT (access or legacy refresh). Returns payload or None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
