"""JWT CRUD for Gate 1 caregiver contact registry."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse
from backend.app.schemas.gate1 import CaregiverCreateIn, CaregiverUpdateIn
from backend.app.schemas.i10_care_network import (
    CaregiverAccountLinkIn,
    CaregiverHealthSubjectAssociateIn,
    CaregiverPhoneCandidateIn,
    CaregiverPhoneConfirmIn,
)
from backend.app.routers.auth_otp import get_current_user
from backend.app.routers.jwt_guards import reject_legacy_user_id_query
from backend.app.services.i10.care_network_actor import CareNetworkAuthorizationError
from backend.app.services.i10.care_network_identity import (
    CareNetworkIdentityError,
    associate_caregiver_health_subject,
    confirm_phone_candidate_link,
    link_caregiver_to_account,
    lookup_account_candidate_by_phone,
    unlink_caregiver_account,
)
from backend.app.services.user_caregiver_service import (
    CaregiverDuplicateError,
    CaregiverNotFoundError,
    CaregiverValidationError,
    create_caregiver,
    deactivate_caregiver,
    list_caregivers,
    update_caregiver,
)

router = APIRouter()


def _identity_error(exc: CareNetworkIdentityError | CareNetworkAuthorizationError) -> HTTPException:
    status = 404 if exc.code in ("USER_CAREGIVER_NOT_FOUND", "RECIPIENT_ACCOUNT_NOT_FOUND", "HEALTH_SUBJECT_NOT_FOUND") else 409
    if exc.code in ("ACTOR_CANNOT_MANAGE_SUBJECT_CARE_NETWORK",):
        status = 403
    if exc.code in ("INVALID_PHONE", "CAREGIVER_PHONE_REQUIRED", "PHONE_CANDIDATE_MISMATCH"):
        status = 422
    return HTTPException(status_code=status, detail={"ok": False, "error": {"code": exc.code}})


@router.get("/caregivers", response_model=APIResponse)
def get_caregivers(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    items = list_caregivers(db, auth_user.id)
    return APIResponse(ok=True, data={"caregivers": items})


@router.post("/caregivers", response_model=APIResponse)
def post_caregiver(
    body: CaregiverCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        item = create_caregiver(db, auth_user.id, body)
    except CaregiverDuplicateError:
        raise HTTPException(status_code=409, detail="A contact with this phone already exists") from None
    except CaregiverValidationError:
        raise HTTPException(status_code=422, detail="Invalid phone number") from None
    return APIResponse(ok=True, data=item)


@router.patch("/caregivers/{caregiver_id}", response_model=APIResponse)
def patch_caregiver(
    caregiver_id: int,
    body: CaregiverUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        item = update_caregiver(db, auth_user.id, caregiver_id, body)
    except CaregiverNotFoundError:
        raise HTTPException(status_code=404, detail="Caregiver not found") from None
    except CaregiverDuplicateError:
        raise HTTPException(status_code=409, detail="A contact with this phone already exists") from None
    except CaregiverValidationError:
        raise HTTPException(status_code=422, detail="Invalid phone number") from None
    return APIResponse(ok=True, data=item)


@router.delete("/caregivers/{caregiver_id}", response_model=APIResponse)
def delete_caregiver_route(
    caregiver_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Soft-deactivate caregiver contact (is_active=false)."""
    try:
        deactivate_caregiver(db, auth_user.id, caregiver_id)
    except CaregiverNotFoundError:
        raise HTTPException(status_code=404, detail="Caregiver not found") from None
    return APIResponse(ok=True, data={"deleted": True, "id": caregiver_id, "soft": True})


@router.post("/caregivers/{caregiver_id}/account-candidates", response_model=APIResponse)
def post_caregiver_account_candidates(
    caregiver_id: int,
    body: CaregiverPhoneCandidateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Locate candidate Sedi account by phone — does not authorize or link."""
    try:
        data = lookup_account_candidate_by_phone(
            db,
            owner_user_id=auth_user.id,
            user_caregiver_id=caregiver_id,
            phone=body.phone,
        )
    except CareNetworkIdentityError as exc:
        raise _identity_error(exc) from exc
    except CareNetworkAuthorizationError as exc:
        raise _identity_error(exc) from exc
    return APIResponse(ok=True, data=data)


@router.post("/caregivers/{caregiver_id}/link-account", response_model=APIResponse)
def post_caregiver_link_account(
    caregiver_id: int,
    body: CaregiverAccountLinkIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        row = link_caregiver_to_account(
            db,
            owner_user_id=auth_user.id,
            user_caregiver_id=caregiver_id,
            recipient_account_user_id=body.recipient_account_user_id,
            replace_existing=body.replace_existing,
        )
    except CareNetworkIdentityError as exc:
        raise _identity_error(exc) from exc
    except CareNetworkAuthorizationError as exc:
        raise _identity_error(exc) from exc
    from backend.app.services.user_caregiver_service import _row_to_dict

    return APIResponse(ok=True, data=_row_to_dict(row))


@router.post("/caregivers/{caregiver_id}/confirm-phone-candidate", response_model=APIResponse)
def post_caregiver_confirm_phone_candidate(
    caregiver_id: int,
    body: CaregiverPhoneConfirmIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        row = confirm_phone_candidate_link(
            db,
            owner_user_id=auth_user.id,
            user_caregiver_id=caregiver_id,
            recipient_account_user_id=body.recipient_account_user_id,
        )
    except CareNetworkIdentityError as exc:
        raise _identity_error(exc) from exc
    except CareNetworkAuthorizationError as exc:
        raise _identity_error(exc) from exc
    from backend.app.services.user_caregiver_service import _row_to_dict

    return APIResponse(ok=True, data=_row_to_dict(row))


@router.delete("/caregivers/{caregiver_id}/link-account", response_model=APIResponse)
def delete_caregiver_link_account(
    caregiver_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        row = unlink_caregiver_account(
            db,
            owner_user_id=auth_user.id,
            user_caregiver_id=caregiver_id,
        )
    except CareNetworkIdentityError as exc:
        raise _identity_error(exc) from exc
    except CareNetworkAuthorizationError as exc:
        raise _identity_error(exc) from exc
    from backend.app.services.user_caregiver_service import _row_to_dict

    return APIResponse(ok=True, data=_row_to_dict(row))


@router.patch("/caregivers/{caregiver_id}/health-subject", response_model=APIResponse)
def patch_caregiver_health_subject(
    caregiver_id: int,
    body: CaregiverHealthSubjectAssociateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        row = associate_caregiver_health_subject(
            db,
            owner_user_id=auth_user.id,
            user_caregiver_id=caregiver_id,
            health_subject_id=body.health_subject_id,
        )
    except CareNetworkIdentityError as exc:
        raise _identity_error(exc) from exc
    except CareNetworkAuthorizationError as exc:
        raise _identity_error(exc) from exc
    from backend.app.services.user_caregiver_service import _row_to_dict

    return APIResponse(ok=True, data=_row_to_dict(row))
