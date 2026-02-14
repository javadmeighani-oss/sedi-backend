# app/routers/system.py – Production monitoring (Freeze B1)
import os
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.database import get_db

router = APIRouter()


@router.get("/health")
def get_health(request: Request, db: Session = Depends(get_db)):
    """
    Lightweight health check for production monitoring.
    Returns 200 JSON: ok, version, env (prod/dev), db status, timestamp. No secrets.
    """
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    env_raw = os.environ.get("ENV", "").strip().lower()
    env = "prod" if env_raw == "prod" else "dev"

    return {
        "ok": True,
        "version": getattr(request.app, "version", "2.0.1"),
        "env": env,
        "db": db_status,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
    }
