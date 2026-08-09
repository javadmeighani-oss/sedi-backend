# app/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from backend.app.routers import (
    auth,
    auth_otp,
    interact,
    health,
    lifestyle,
    notifications,
    ai_core,
    conditions,
    device,
    devices,
    decision,
    memory,
    user_knowledge,
    user_medications,
    user_profile_facts,
    user_caregivers,
    user_dependents,
    user_gate2,
    knowledge,
    knowledge_admin,
    knowledge_base,
    care_gate3,
    health_care,
    system,
    i5_iran_directory,
)
from backend.app.routers import ops
from backend.app.core.scheduler import start_scheduler  # For automatic notifications

# ------------------ Create FastAPI Application ------------------
app = FastAPI(
    title="Sedi Intelligent Health Assistant",
    description=(
        "Sedi is an AI-based health assistant that provides continuous, personalized care. "
        "It supports multilingual interaction (English base + Persian + Arabic) "
        "and integrates GPT-powered intelligence, adaptive memory, and emotional engagement."
    ),
    version="2.0.1",
)

# ------------------ CORS Configuration ------------------
origins = [
    "*",  # Should be restricted in production environment
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ Main Routes (Routers) ------------------
app.include_router(system.router, tags=["System"])  # GET /health for monitoring (Freeze B1)
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(auth_otp.router, prefix="/auth", tags=["Authentication"])
app.include_router(interact.router, prefix="/interact", tags=["Interaction"])
app.include_router(health.router, prefix="/health", tags=["Health Data"])
app.include_router(lifestyle.router, prefix="/lifestyle", tags=["Lifestyle Data"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(ai_core.router, prefix="/ai_core", tags=["AI Core"])
app.include_router(conditions.router, prefix="/conditions", tags=["Medical Conditions"])
app.include_router(device.router, prefix="/device", tags=["Device"])
app.include_router(devices.router, prefix="/devices", tags=["Devices"])
app.include_router(decision.router)
app.include_router(memory.router, prefix="/memory", tags=["Memory"])
app.include_router(user_knowledge.router, prefix="/user", tags=["User"])
app.include_router(user_medications.router, prefix="/user", tags=["User"])
app.include_router(user_profile_facts.router, prefix="/user", tags=["User"])
app.include_router(user_caregivers.router, prefix="/user", tags=["User"])
app.include_router(user_dependents.router, prefix="/user", tags=["User"])
app.include_router(user_gate2.router, prefix="/user", tags=["User"])
app.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
app.include_router(knowledge_admin.router, prefix="/knowledge/admin", tags=["Knowledge Admin"])
app.include_router(knowledge_base.router, prefix="/knowledge-base", tags=["Knowledge Base"])
app.include_router(care_gate3.router, prefix="/care", tags=["Care Intelligence"])
app.include_router(health_care.router, prefix="/health", tags=["Health Care"])
app.include_router(ops.router)
app.include_router(i5_iran_directory.router)

# ------------------ Activate Scheduler ------------------
def _should_start_scheduler() -> bool:
    """Return False if tests (pytest or SEDI_DISABLE_SCHEDULER); True otherwise. Safe for production."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    v = os.getenv("SEDI_DISABLE_SCHEDULER", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return False
    return True


if _should_start_scheduler():
    start_scheduler()

# ------------------ Root Endpoint for Testing ------------------
@app.get("/")
def root():
    return {
        "status": "Sedi AI Backend Running ✅",
        "version": "2.0.1",
        "base_language": "en",
        "supported_languages": ["en", "fa", "ar"],
        "server_time": datetime.utcnow(),
        "message": "Welcome to Sedi – your intelligent, caring, and proactive health companion 🌿"
    }
