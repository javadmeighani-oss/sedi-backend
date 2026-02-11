# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from backend.app.database import engine, Base
from backend.app.routers import (
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
    memory,
    user_knowledge,
)
from backend.app.core.scheduler import start_scheduler  # For automatic notifications

# ------------------ Create Database Tables ------------------
Base.metadata.create_all(bind=engine)

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
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
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

# ------------------ Activate Scheduler ------------------
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
