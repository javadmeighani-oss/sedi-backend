# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from app.database import engine, Base
from app.routers import (
    auth,
    interact,
    health,
    lifestyle,
    notifications,
    ai_core,
)
from app.core.scheduler import start_scheduler  # Scheduler import

# ------------------ ایجاد جداول ------------------
Base.metadata.create_all(bind=engine)

# ------------------ ساخت اپلیکیشن FastAPI ------------------
app = FastAPI(
    title="Sedi Intelligent Health Assistant",
    description=(
        "Sedi is an AI-based health assistant that provides continuous, personalized care. "
        "It supports multilingual interaction (English + Persian + Arabic) and integrates "
        "GPT-powered intelligence, adaptive memory, and emotional engagement."
    ),
    version="2.0.1",
)

# ------------------ تنظیمات CORS ------------------
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ مسیرهای اصلی (Routers) ------------------
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(interact.router, prefix="/interact", tags=["Interaction"])
app.include_router(health.router, prefix="/health", tags=["Health Data"])
app.include_router(lifestyle.router, prefix="/lifestyle", tags=["Lifestyle Data"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(ai_core.router, prefix="/ai_core", tags=["AI Core"])

# ------------------ فعال‌سازی Scheduler ------------------
start_scheduler()

# ------------------ مسیر اصلی ------------------
@app.get("/")
def root():
    return {
        "status": "Sedi AI Backend Running",
        "version": "2.0.1",
        "supported_languages": ["en", "fa", "ar"],
        "server_time": str(datetime.utcnow()),
        "message": "Welcome to Sedi – your intelligent, caring, and proactive health companion"
    }
