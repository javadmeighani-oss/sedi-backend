"""Health Subject management routes (I9 foundation)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import User
from backend.app.routers.auth_otp import get_current_user
from backend.app.schemas.health_subject import (
    HealthSubjectApiResponse,
    ManagedHealthSubjectCreate,
)
from backend.app.schemas.longitudinal import AggregateRebuildRequest
from backend.app.services.i9.aggregation_service import (
    rebuild_daily_bucket,
    rebuild_higher_bucket_from_daily_rollups,
)
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
    preferred_language_for_subject,
    require_account_subject_access,
)
from backend.app.services.i9.longitudinal_read_service import (
    list_aggregates,
    list_baselines,
    list_cardiac_events,
    list_observations,
)

router = APIRouter()


def _access_denied() -> HTTPException:
    return HTTPException(status_code=403, detail={"ok": False, "error": {"code": "HEALTH_SUBJECT_ACCESS_DENIED"}})


@router.post("/self", response_model=HealthSubjectApiResponse)
def ensure_self_health_subject(
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ensure account holder has a SELF health subject."""
    subject = ensure_self_subject_for_account(db, auth_user.id)
    return HealthSubjectApiResponse(
        ok=True,
        data={
            "health_subject_id": subject.id,
            "display_name": subject.display_name,
            "linked_user_id": subject.linked_user_id,
            "subject_kind": subject.subject_kind,
        },
    )


@router.post("/managed", response_model=HealthSubjectApiResponse)
def create_managed_health_subject(
    body: ManagedHealthSubjectCreate,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a managed health subject without a linked Sedi account."""
    subject = create_managed_subject_without_account(
        db,
        account_user_id=auth_user.id,
        display_name=body.display_name,
        access_role=body.access_role,
    )
    return HealthSubjectApiResponse(
        ok=True,
        data={
            "health_subject_id": subject.id,
            "display_name": subject.display_name,
            "linked_user_id": subject.linked_user_id,
            "subject_kind": subject.subject_kind,
            "access_role": body.access_role,
        },
    )


@router.get("/{health_subject_id}/vitals/observations", response_model=HealthSubjectApiResponse)
def get_subject_vitals_observations(
    health_subject_id: int,
    measurement_type: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import datetime

    def _dt(v: str | None):
        return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None

    try:
        rows = list_observations(
            db,
            account_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            measurement_type=measurement_type,
            start=_dt(start),
            end=_dt(end),
            limit=limit,
            offset=offset,
        )
    except HealthSubjectAccessDenied:
        raise _access_denied()
    return HealthSubjectApiResponse(ok=True, data={"observations": rows, "limit": limit, "offset": offset})


@router.get("/{health_subject_id}/vitals/aggregates", response_model=HealthSubjectApiResponse)
def get_subject_vitals_aggregates(
    health_subject_id: int,
    measurement_type: str = Query(...),
    bucket_kind: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import datetime

    try:
        rows = list_aggregates(
            db,
            account_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            measurement_type=measurement_type,
            bucket_kind=bucket_kind,
            start=datetime.fromisoformat(start.replace("Z", "+00:00")),
            end=datetime.fromisoformat(end.replace("Z", "+00:00")),
        )
    except HealthSubjectAccessDenied:
        raise _access_denied()
    return HealthSubjectApiResponse(ok=True, data={"aggregates": rows})


@router.get("/{health_subject_id}/vitals/events", response_model=HealthSubjectApiResponse)
def get_subject_vitals_events(
    health_subject_id: int,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import datetime

    def _dt(v: str | None):
        return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None

    try:
        rows = list_cardiac_events(
            db,
            account_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            start=_dt(start),
            end=_dt(end),
            limit=limit,
            offset=offset,
        )
    except HealthSubjectAccessDenied:
        raise _access_denied()
    return HealthSubjectApiResponse(ok=True, data={"events": rows})


@router.get("/{health_subject_id}/vitals/baselines", response_model=HealthSubjectApiResponse)
def get_subject_vitals_baselines(
    health_subject_id: int,
    measurement_type: str | None = Query(default=None),
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        payload = list_baselines(
            db,
            account_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            measurement_type=measurement_type,
        )
    except HealthSubjectAccessDenied:
        raise _access_denied()
    return HealthSubjectApiResponse(ok=True, data=payload)


@router.post("/{health_subject_id}/vitals/aggregates/rebuild", response_model=HealthSubjectApiResponse)
def rebuild_subject_vitals_aggregate(
    health_subject_id: int,
    body: AggregateRebuildRequest,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        subject = require_account_subject_access(db, auth_user.id, health_subject_id)
    except HealthSubjectAccessDenied:
        raise _access_denied()
    lang = preferred_language_for_subject(db, subject)
    if body.bucket_kind == "daily":
        stats = rebuild_daily_bucket(
            db,
            subject=subject,
            measurement_type=body.measurement_type,
            ref=body.ref,
            preferred_language=lang,
        )
    elif body.bucket_kind in ("weekly", "calendar_month", "yearly"):
        rebuild_daily_bucket(
            db,
            subject=subject,
            measurement_type=body.measurement_type,
            ref=body.ref,
            preferred_language=lang,
        )
        stats = rebuild_higher_bucket_from_daily_rollups(
            db,
            subject=subject,
            measurement_type=body.measurement_type,
            bucket_kind=body.bucket_kind,
            ref=body.ref,
            preferred_language=lang,
        )
    else:
        raise HTTPException(status_code=400, detail={"ok": False, "error": {"code": "UNSUPPORTED_BUCKET"}})
    return HealthSubjectApiResponse(
        ok=True,
        data={
            "bucket_kind": body.bucket_kind,
            "sample_count": stats.sample_count,
            "avg_value": stats.avg_value,
            "min_value": stats.min_value,
            "max_value": stats.max_value,
        },
    )
