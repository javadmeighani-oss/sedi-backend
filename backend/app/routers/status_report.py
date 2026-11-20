# app/routers/status_report.py
"""R-110 amendment 1: the STATUS REPORT (health status / doctor visit / nutrition / lifestyle / exercise plan), read-only.

The app lets the user review and remove lines, makes the PDF on the device and shares it itself; the server never sends it anywhere.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.database import get_db
from backend.app.routers.auth_otp import get_current_user
from backend.app.schemas import APIResponse

router = APIRouter()


def _guard() -> None:
    from backend.app.services.status_report import builder

    if not builder.enabled():
        raise HTTPException(status_code=404, detail="status report is not available")


@router.get("/kinds", response_model=APIResponse)
def status_report_kinds(auth_user: models.User = Depends(get_current_user)):
    """The kinds of report Sedi can prepare, with their titles in the user's language."""
    _guard()
    from backend.app.services.status_report import builder

    return APIResponse(ok=True, data={"kinds": builder.kinds(getattr(auth_user, "preferred_language", None))})


@router.get("", response_model=APIResponse)
def status_report(
    kind: str = Query(..., description="health_status | doctor_visit | nutrition | lifestyle | exercise_plan"),
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The report as titled sections of short lines with stable ids (state: ready | empty | no_consent). Read-only, consent-gated."""
    _guard()
    from backend.app.services.status_report import builder

    try:
        data = builder.build_status_report(db, auth_user.id, kind, getattr(auth_user, "preferred_language", None))
    except ValueError:
        raise HTTPException(status_code=422, detail="unknown report kind")
    return APIResponse(ok=True, data=data)
