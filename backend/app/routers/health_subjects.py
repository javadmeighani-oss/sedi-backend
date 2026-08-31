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
from backend.app.schemas.i10_care_network import (
    SubjectCaregiverAccessGrantIn,
    SubjectNotificationGrantCreateIn,
    SubjectNotificationGrantRevokeIn,
)
from backend.app.services.i10.care_network_access import (
    CareNetworkAccessError,
    grant_caregiver_subject_access,
    list_subject_caregiver_access,
    revoke_caregiver_subject_access,
)
from backend.app.services.i10.care_network_actor import CareNetworkAuthorizationError
from backend.app.services.i10.care_network_grants import (
    CareNetworkGrantError,
    create_subject_notification_grant,
    list_subject_notification_grants,
    revoke_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
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


def _care_network_error(exc: CareNetworkAccessError | CareNetworkGrantError | CareNetworkAuthorizationError) -> HTTPException:
    if isinstance(exc, CareNetworkAuthorizationError):
        return HTTPException(status_code=403, detail={"ok": False, "error": {"code": exc.code}})
    status = 404 if exc.code.endswith("_NOT_FOUND") else 409
    if exc.code in ("RECIPIENT_LACKS_SUBJECT_ACCESS", "SELF_GRANT_NOT_REQUIRED", "CAREGIVER_SUBSTITUTION_BLOCKED"):
        status = 422
    return HTTPException(status_code=status, detail={"ok": False, "error": {"code": exc.code}})


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


@router.post("/{health_subject_id}/caregivers", response_model=HealthSubjectApiResponse)
def post_subject_caregiver_access(
    health_subject_id: int,
    body: SubjectCaregiverAccessGrantIn,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = grant_caregiver_subject_access(
            db,
            actor_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            recipient_account_user_id=body.recipient_account_user_id,
            access_role=body.access_role,
        )
    except (CareNetworkAccessError, CareNetworkAuthorizationError) as exc:
        raise _care_network_error(exc) from exc
    return HealthSubjectApiResponse(
        ok=True,
        data={
            "id": row.id,
            "account_user_id": row.account_user_id,
            "health_subject_id": row.health_subject_id,
            "access_role": row.access_role,
            "is_active": row.is_active,
        },
    )


@router.get("/{health_subject_id}/caregivers", response_model=HealthSubjectApiResponse)
def get_subject_caregiver_access(
    health_subject_id: int,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        items = list_subject_caregiver_access(
            db,
            actor_user_id=auth_user.id,
            health_subject_id=health_subject_id,
        )
    except CareNetworkAuthorizationError as exc:
        raise _care_network_error(exc) from exc
    return HealthSubjectApiResponse(ok=True, data={"caregivers": items})


@router.delete("/{health_subject_id}/caregivers/{recipient_account_user_id}", response_model=HealthSubjectApiResponse)
def delete_subject_caregiver_access(
    health_subject_id: int,
    recipient_account_user_id: int,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = revoke_caregiver_subject_access(
            db,
            actor_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            recipient_account_user_id=recipient_account_user_id,
        )
    except (CareNetworkAccessError, CareNetworkAuthorizationError) as exc:
        raise _care_network_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail={"ok": False, "error": {"code": "ACCESS_NOT_FOUND"}})
    return HealthSubjectApiResponse(ok=True, data={"revoked": True, "id": row.id})


@router.post("/{health_subject_id}/notification-grants", response_model=HealthSubjectApiResponse)
def post_subject_notification_grant(
    health_subject_id: int,
    body: SubjectNotificationGrantCreateIn,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = create_subject_notification_grant(
            db,
            actor_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            recipient_user_id=body.recipient_user_id,
            notification_scope=body.notification_scope,
            user_caregiver_id=body.user_caregiver_id,
            authorization_source=body.authorization_source,
        )
    except (CareNetworkGrantError, CareNetworkAuthorizationError) as exc:
        raise _care_network_error(exc) from exc
    return HealthSubjectApiResponse(
        ok=True,
        data={
            "id": row.id,
            "health_subject_id": row.health_subject_id,
            "recipient_user_id": row.recipient_user_id,
            "notification_scope": row.notification_scope,
            "is_active": row.is_active,
        },
    )


@router.get("/{health_subject_id}/notification-grants", response_model=HealthSubjectApiResponse)
def get_subject_notification_grants(
    health_subject_id: int,
    recipient_user_id: int | None = Query(default=None),
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        items = list_subject_notification_grants(
            db,
            actor_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            recipient_user_id=recipient_user_id,
        )
    except CareNetworkAuthorizationError as exc:
        raise _care_network_error(exc) from exc
    return HealthSubjectApiResponse(ok=True, data={"grants": items})


@router.delete("/{health_subject_id}/notification-grants/{grant_id}", response_model=HealthSubjectApiResponse)
def delete_subject_notification_grant(
    health_subject_id: int,
    grant_id: int,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = revoke_subject_notification_grant(
            db,
            actor_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            grant_id=grant_id,
        )
    except CareNetworkAuthorizationError as exc:
        raise _care_network_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail={"ok": False, "error": {"code": "GRANT_NOT_FOUND"}})
    return HealthSubjectApiResponse(ok=True, data={"revoked": True, "id": row.id})


@router.patch("/{health_subject_id}/notification-grants/revoke-by-scope", response_model=HealthSubjectApiResponse)
def patch_revoke_notification_grant_by_scope(
    health_subject_id: int,
    body: SubjectNotificationGrantRevokeIn,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = revoke_subject_notification_grant_by_scope(
            db,
            actor_user_id=auth_user.id,
            health_subject_id=health_subject_id,
            recipient_user_id=body.recipient_user_id,
            notification_scope=body.notification_scope,
        )
    except CareNetworkAuthorizationError as exc:
        raise _care_network_error(exc) from exc
    if row is None:
        return HealthSubjectApiResponse(ok=True, data={"revoked": False, "already_revoked": True})
    return HealthSubjectApiResponse(ok=True, data={"revoked": True, "id": row.id})
