# app/core/device_auth.py
"""
Device Authentication (Release C1)

Simple token-based auth for device ingestion endpoints.
Uses X-DEVICE-TOKEN header and DEVICE_INGEST_TOKEN environment variable.
"""

import os
from fastapi import Header, HTTPException, status

# Read token from environment (default: empty, must be set)
DEVICE_INGEST_TOKEN = os.getenv("DEVICE_INGEST_TOKEN", "")


def verify_device_token(x_device_token: str = Header(..., alias="X-DEVICE-TOKEN")) -> str:
    """
    Verify device token from X-DEVICE-TOKEN header.
    
    Args:
        x_device_token: Token from X-DEVICE-TOKEN header
    
    Returns:
        Token string if valid
    
    Raises:
        HTTPException 401 if token is missing or invalid
    """
    if not DEVICE_INGEST_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device ingestion is not configured (DEVICE_INGEST_TOKEN not set)"
        )
    
    if x_device_token != DEVICE_INGEST_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token"
        )
    
    return x_device_token
