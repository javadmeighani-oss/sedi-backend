# app/routers/__init__.py
# auth_login is intentionally excluded: Stage 25 OTP is the only supported auth; legacy router disabled.
from . import (
    auth,
    interact,
    health,
    lifestyle,
    notifications,
    ai_core,
    conditions,
    device,
    devices,
    decision,
    data,
    medical,
    memory,
    user_knowledge,
    sms_gateway,
    device_data,
)

__all__ = [
    "auth",
    "interact",
    "health",
    "lifestyle",
    "notifications",
    "ai_core",
    "conditions",
    "device",
    "devices",
    "decision",
    "data",
    "medical",
    "memory",
    "user_knowledge",
    "sms_gateway",
    "device_data",
]
