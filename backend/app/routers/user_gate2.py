"""Gate 2 JWT CRUD + unified memory context."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse
from backend.app.schemas.gate2 import (
    CarePlanItemCreateIn,
    CarePlanItemUpdateIn,
    DoctorCreateIn,
    DoctorUpdateIn,
    EventCreateIn,
    EventUpdateIn,
    GoalCreateIn,
    GoalUpdateIn,
    HabitCreateIn,
    HabitUpdateIn,
    LifestyleEventCreateIn,
    RestrictionCreateIn,
    RestrictionUpdateIn,
)
from backend.app.routers.auth_otp import get_current_user
from backend.app.routers.jwt_guards import reject_legacy_user_id_query
from backend.app.services.gate2_data_service import (
    Gate2NotFoundError,
    create_care_plan_item,
    create_doctor,
    create_event,
    create_goal,
    create_habit,
    create_lifestyle_event,
    create_restriction,
    delete_care_plan_item,
    delete_doctor,
    delete_event,
    delete_goal,
    delete_habit,
    delete_restriction,
    list_care_plan_items,
    list_doctors,
    list_events,
    list_goals,
    list_habits,
    list_lifestyle_events,
    list_restrictions,
    update_care_plan_item,
    update_doctor,
    update_event,
    update_goal,
    update_habit,
    update_restriction,
)
from backend.app.services.memory_context_service import build_memory_context

router = APIRouter()


def _not_found():
    raise HTTPException(status_code=404, detail="Not found")


# --- Habits ---
@router.get("/habits", response_model=APIResponse)
def get_habits(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"habits": list_habits(db, auth_user.id)})


@router.post("/habits", response_model=APIResponse)
def post_habit(
    body: HabitCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=create_habit(db, auth_user.id, body))


@router.patch("/habits/{habit_id}", response_model=APIResponse)
def patch_habit(
    habit_id: int,
    body: HabitUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=update_habit(db, auth_user.id, habit_id, body))
    except Gate2NotFoundError:
        _not_found()


@router.delete("/habits/{habit_id}", response_model=APIResponse)
def delete_habit_route(
    habit_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        delete_habit(db, auth_user.id, habit_id)
    except Gate2NotFoundError:
        _not_found()
    return APIResponse(ok=True, data={"deleted": True, "id": habit_id})


# --- Goals ---
@router.get("/goals", response_model=APIResponse)
def get_goals(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"goals": list_goals(db, auth_user.id)})


@router.post("/goals", response_model=APIResponse)
def post_goal(
    body: GoalCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=create_goal(db, auth_user.id, body))


@router.patch("/goals/{goal_id}", response_model=APIResponse)
def patch_goal(
    goal_id: int,
    body: GoalUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=update_goal(db, auth_user.id, goal_id, body))
    except Gate2NotFoundError:
        _not_found()


@router.delete("/goals/{goal_id}", response_model=APIResponse)
def delete_goal_route(
    goal_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        delete_goal(db, auth_user.id, goal_id)
    except Gate2NotFoundError:
        _not_found()
    return APIResponse(ok=True, data={"deleted": True, "id": goal_id})


# --- Restrictions ---
@router.get("/restrictions", response_model=APIResponse)
def get_restrictions(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"restrictions": list_restrictions(db, auth_user.id)})


@router.post("/restrictions", response_model=APIResponse)
def post_restriction(
    body: RestrictionCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=create_restriction(db, auth_user.id, body))


@router.patch("/restrictions/{restriction_id}", response_model=APIResponse)
def patch_restriction(
    restriction_id: int,
    body: RestrictionUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=update_restriction(db, auth_user.id, restriction_id, body))
    except Gate2NotFoundError:
        _not_found()


@router.delete("/restrictions/{restriction_id}", response_model=APIResponse)
def delete_restriction_route(
    restriction_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        delete_restriction(db, auth_user.id, restriction_id)
    except Gate2NotFoundError:
        _not_found()
    return APIResponse(ok=True, data={"deleted": True, "id": restriction_id})


# --- Doctors ---
@router.get("/doctors", response_model=APIResponse)
def get_doctors(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"doctors": list_doctors(db, auth_user.id)})


@router.post("/doctors", response_model=APIResponse)
def post_doctor(
    body: DoctorCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=create_doctor(db, auth_user.id, body))


@router.patch("/doctors/{doctor_id}", response_model=APIResponse)
def patch_doctor(
    doctor_id: int,
    body: DoctorUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=update_doctor(db, auth_user.id, doctor_id, body))
    except Gate2NotFoundError:
        _not_found()


@router.delete("/doctors/{doctor_id}", response_model=APIResponse)
def delete_doctor_route(
    doctor_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        delete_doctor(db, auth_user.id, doctor_id)
    except Gate2NotFoundError:
        _not_found()
    return APIResponse(ok=True, data={"deleted": True, "id": doctor_id})


# --- Events (unified calendar/deadlines/appointments) ---
@router.get("/events", response_model=APIResponse)
def get_events(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"events": list_events(db, auth_user.id)})


@router.post("/events", response_model=APIResponse)
def post_event(
    body: EventCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=create_event(db, auth_user.id, body))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/events/{event_id}", response_model=APIResponse)
def patch_event(
    event_id: int,
    body: EventUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=update_event(db, auth_user.id, event_id, body))
    except Gate2NotFoundError:
        _not_found()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/events/{event_id}", response_model=APIResponse)
def delete_event_route(
    event_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        delete_event(db, auth_user.id, event_id)
    except Gate2NotFoundError:
        _not_found()
    return APIResponse(ok=True, data={"deleted": True, "id": event_id})


# --- Lifestyle events (logs) ---
@router.get("/lifestyle-events", response_model=APIResponse)
def get_lifestyle_events(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"lifestyle_events": list_lifestyle_events(db, auth_user.id)})


@router.post("/lifestyle-events", response_model=APIResponse)
def post_lifestyle_event(
    body: LifestyleEventCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=create_lifestyle_event(db, auth_user.id, body))


# --- Care plan items ---
@router.get("/care-plan-items", response_model=APIResponse)
def get_care_plan_items(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"care_plan_items": list_care_plan_items(db, auth_user.id)})


@router.post("/care-plan-items", response_model=APIResponse)
def post_care_plan_item(
    body: CarePlanItemCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=create_care_plan_item(db, auth_user.id, body))


@router.patch("/care-plan-items/{item_id}", response_model=APIResponse)
def patch_care_plan_item(
    item_id: int,
    body: CarePlanItemUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=update_care_plan_item(db, auth_user.id, item_id, body))
    except Gate2NotFoundError:
        _not_found()


@router.delete("/care-plan-items/{item_id}", response_model=APIResponse)
def delete_care_plan_item_route(
    item_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        delete_care_plan_item(db, auth_user.id, item_id)
    except Gate2NotFoundError:
        _not_found()
    return APIResponse(ok=True, data={"deleted": True, "id": item_id})


# --- Unified memory context ---
@router.get("/memory-context", response_model=APIResponse)
def get_memory_context(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=build_memory_context(db, auth_user.id))
