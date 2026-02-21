# app/routers/system.py – Production monitoring (Freeze B1)
import os
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.database import get_db

router = APIRouter()


def _app_version(request: Request) -> str:
    return getattr(request.app, "version", "2.0.1")


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
        "version": _app_version(request),
        "env": env,
        "db": db_status,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
    }


@router.get("/healthz")
def get_healthz(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Pilot-ready healthz: ok, data.db_ok, data.server_time, data.version.
    Returns 503 if DB check fails.
    """
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
        response.status_code = 503

    now_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return {
        "ok": db_ok,
        "data": {
            "db_ok": db_ok,
            "server_time": now_utc,
            "version": _app_version(request),
        },
        "error": None,
    }
