# app/routers/device.py
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo, ApiResponseV1
from backend.app.services.notification_engine import DecisionEngine
from backend.app.schemas.device import (
    DeviceIngestRequest,
    DeviceIngestResponse,
    DeviceHeartbeatRequest,
    DeviceAcknowledgeRequest,
    SensorSyncRequest,
    SensorSyncResponse,
    RawSignalBatchRequest,
    RawSignalBatchResponse,
    RawSignalBatchData,
)
from backend.app.schemas.device_packet import DevicePacketIngestRequest, DevicePacketIngestResponse
from backend.app.services.device_ingestion import ingest_event, DeviceRateLimitExceeded
from backend.app.services.i9.device_binding_service import resolve_subject_for_device, DeviceBindingError
from backend.app.services.i9.device_packet_service import (
    DevicePacketIngestInput,
    PacketObservationIn,
    ingest_device_packet,
)
from backend.app.services.i9.health_subject_service import resolve_linked_user_id_for_subject
from backend.app.services.gate5.gadget_hub_status import (
    apply_heartbeat_metadata,
    is_gadget_hub,
    sync_hub_sensors,
)
from backend.app.services.gate5.raw_signal_ingestion import (
    ingest_raw_signal_batch,
    RawSignalIngestionError,
)
from backend.app.core.device_auth import (
    get_device_token,
    authorize_device_or_legacy,
    authorize_operational_device,
    reject_legacy_user_id_query,
    resolve_device_from_token,
    resolve_device_credential_status,
)
from backend.app.services.vitals.vital_registry import VitalValidationError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/pending-commands", response_model=ApiResponseV1)
def get_pending_commands(
    device_id: str = Query(..., description="Logical device id"),
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
    _: None = Depends(reject_legacy_user_id_query),
):
    """
    Fetch pending audio commands for the device's owner.

    Requires X-DEVICE-TOKEN and device_id query. user_id is derived from the device row.
    """
    device = authorize_operational_device(db=db, device_id=device_id, token=token)
    user_id = device.user_id

    alerts = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .filter(models.Notification.is_read == False)
        .filter(models.Notification.priority.in_(["high", "critical"]))
        .order_by(models.Notification.created_at.desc())
        .all()
    )

    if not alerts:
        return APIResponse(ok=True, data={"commands": []})

    def priority_to_numeric(priority_str: str) -> int:
        priority_map = {"low": 1, "normal": 2, "high": 3, "critical": 4}
        return priority_map.get(priority_str, 2)

    commands = []
    for a in alerts:
        priority_num = priority_to_numeric(a.priority)
        command = {
            "sound_id": "alert_default",
            "text": a.body or a.title or "Health Alert",
            "volume": 90,
            "repeat": 2 if priority_num >= 3 else 1,
            "language": "fa",
            "priority": priority_num,
        }
        commands.append(command)
        a.is_read = True

    db.commit()
    return APIResponse(ok=True, data={"commands": commands})


@router.post("/heartbeat", response_model=ApiResponseV1)
def device_heartbeat(
    body: DeviceHeartbeatRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Device heartbeat. Requires X-DEVICE-TOKEN; user_id is derived from the device row.
    """
    device = authorize_operational_device(db=db, device_id=body.device_id, token=token)

    now = datetime.utcnow()
    battery_level = body.battery_level if body.battery_level is not None else body.battery

    apply_heartbeat_metadata(
        device,
        now=now,
        status=body.status,
        battery_level=battery_level,
        firmware_version=body.firmware_version,
        hardware_version=body.hardware_version,
        hub_status=body.hub_status,
        last_sync_at=body.last_sync_at,
    )

    db.add(device)
    db.commit()
    db.refresh(device)

    logger.info(
        "[DEVICE_HEARTBEAT] Updated device_id=%s user_id=%s last_seen_at=%s status=%s battery=%s fw=%s",
        device.device_id,
        device.user_id,
        device.last_seen_at,
        device.status,
        device.battery_level,
        device.firmware_version,
    )

    return APIResponse(ok=True, data={"message": "Heartbeat received successfully."})


@router.post("/acknowledge", response_model=ApiResponseV1)
def acknowledge_command(
    body: DeviceAcknowledgeRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Acknowledge audio command playback. Requires X-DEVICE-TOKEN; user_id from device row.
    """
    device = authorize_operational_device(db=db, device_id=body.device_id, token=token)

    decision_engine = DecisionEngine(db)
    decision_engine.create_insight_notification(
        user_id=device.user_id,
        insight_text=f"Sound '{body.sound_id}' executed with status: {body.status}",
        priority="low",
    )

    return APIResponse(ok=True, data={"acknowledged": True})


@router.post("/sensors/sync", response_model=SensorSyncResponse)
def sync_device_sensors(
    body: SensorSyncRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Sync sensor registry from Gadget Hub. Requires X-DEVICE-TOKEN.
    Upserts sensors by sensor_key; no raw signal ingestion.
    """
    if not body.sensors:
        return SensorSyncResponse(
            ok=False,
            error={"code": "EMPTY_SENSORS", "message": "At least one sensor is required"},
        )

    device = authorize_operational_device(db=db, device_id=body.device_id, token=token)
    if not is_gadget_hub(device):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sensor sync is only allowed for Gadget Hub devices",
        )

    sensors_payload = [s.model_dump() for s in body.sensors]
    result = sync_hub_sensors(db, device, sensors_payload)
    return SensorSyncResponse(ok=True, data=result)


@router.post(
    "/signals/raw",
    response_model=RawSignalBatchResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Duplicate batch replay (idempotent)"},
        403: {"description": "Forbidden — non-hub or unregistered sensor"},
        422: {"description": "Validation error"},
    },
)
def ingest_raw_signal_batch_endpoint(
    body: RawSignalBatchRequest,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Store-only raw heart/ECG signal batch from Gadget Hub.

    Requires X-DEVICE-TOKEN. No interpretation, alerts, or clinical side effects.
    """
    device = authorize_operational_device(db=db, device_id=body.device_id, token=token)

    try:
        result = ingest_raw_signal_batch(db, hub=device, body=body)
    except RawSignalIngestionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    data = RawSignalBatchData(
        batch_id=result.batch_id,
        dedupe_key=result.dedupe_key,
        received_at=result.received_at,
        sample_count=result.sample_count,
        storage_backend=result.storage_backend,
        dedupe_hit=result.dedupe_hit,
        message=result.message,
    )

    if result.dedupe_hit:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=RawSignalBatchResponse(ok=True, data=data).model_dump(mode="json"),
        )

    return RawSignalBatchResponse(ok=True, data=data)


@router.post("/packet", response_model=DevicePacketIngestResponse)
def ingest_device_packet_route(
    body: DevicePacketIngestRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Canonical I9 device packet ingest. Subject attribution resolved server-side from binding.
    Idempotent on device + client_packet_id. ACK contract for store-and-forward.
    """
    try:
        device, auth_reject = resolve_device_credential_status(db=db, token=token)
        if device is None or auth_reject:
            ack = auth_reject or "AUTH_FAILURE"
            return DevicePacketIngestResponse(
                ok=False,
                error={"code": ack, "message": "Device authentication failed"},
                data={"ack_status": ack},
            )

        trace_id = http_request.headers.get("X-TRACE-ID") or uuid.uuid4().hex
        packet_in = DevicePacketIngestInput(
            client_packet_id=body.client_packet_id,
            measured_at=body.measured_at,
            sequence_number=body.sequence_number,
            measured_interval_start=body.measured_interval_start,
            measured_interval_end=body.measured_interval_end,
            gateway_received_at=body.gateway_received_at,
            transport=body.transport,
            firmware_version=body.firmware_version,
            hardware_version=body.hardware_version,
            algorithm_version=body.algorithm_version,
            quality_metadata=body.quality_metadata,
            provenance=body.provenance,
            observations=[
                PacketObservationIn(
                    observation_type=o.observation_type,
                    payload=o.payload,
                    detected_at=o.detected_at,
                )
                for o in body.observations
            ],
        )
        try:
            result = ingest_device_packet(db, device=device, packet_in=packet_in, trace_id=trace_id)
        except ValueError as exc:
            if str(exc) == "NO_ACTIVE_DEVICE_SUBJECT_BINDING":
                return DevicePacketIngestResponse(
                    ok=False,
                    error={"code": "REJECTED_NO_BINDING", "message": str(exc)},
                    data={"ack_status": "REJECTED_NO_BINDING"},
                )
            raise
        packet = result.packet
        ack_status = "DUPLICATE" if result.dedupe_hit else "ACCEPTED"
        return DevicePacketIngestResponse(
            ok=True,
            data={
                "packet_id": packet.id if packet else None,
                "client_packet_id": body.client_packet_id,
                "dedupe_hit": result.dedupe_hit,
                "ack_status": ack_status,
                "health_subject_id": result.health_subject_id,
                "binding_id": result.binding_id,
                "physiological_measurement_ids": result.physiological_measurement_ids,
                "cardiac_event_ids": result.cardiac_event_ids,
                "trace_id": trace_id,
            },
        )
    except VitalValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except ValueError as e:
        return DevicePacketIngestResponse(
            ok=False,
            error={"code": "VALIDATION_ERROR", "message": str(e)},
            data={"ack_status": "REJECTED"},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to ingest device packet")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "code": "INTERNAL_ERROR", "message": "Failed to ingest device packet"},
        )


@router.post("/ingest", response_model=DeviceIngestResponse)
def ingest_device_event(
    request: DeviceIngestRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(get_device_token),
):
    """
    Ingest device event (vital signs) with deduplication and memory mapping.

    Requires X-DEVICE-TOKEN header.

    Auth modes (Release C2):
    - DEVICE_AUTH_MODE=legacy_only: validate shared DEVICE_INGEST_TOKEN (C1 behavior)
    - DEVICE_AUTH_MODE=db_only: validate per-device token from DB (requires request.device_id)
    - DEVICE_AUTH_MODE=hybrid (default): try DB first, then legacy if enabled
    """
    try:
        _auth_result, device = authorize_device_or_legacy(
            db=db,
            user_id=request.user_id,
            device_id=request.device_id,
            token=token,
        )

        effective_user_id = request.user_id
        health_subject_id = None
        if device is not None:
            request.device_id = device.device_id
            try:
                health_subject_id, _binding = resolve_subject_for_device(
                    db, device, measured_at=request.recorded_at
                )
                linked = resolve_linked_user_id_for_subject(db, health_subject_id)
                effective_user_id = linked if linked is not None else device.user_id
            except DeviceBindingError:
                if request.user_id != device.user_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="user_id does not match device owner and no subject binding",
                    )
                effective_user_id = device.user_id

        user = db.query(models.User).filter(models.User.id == effective_user_id).first()
        if not user:
            return DeviceIngestResponse(
                ok=False,
                error={"code": "USER_NOT_FOUND", "message": "User not found"},
            )

        if not request.payload:
            return DeviceIngestResponse(
                ok=False,
                error={"code": "INVALID_PAYLOAD", "message": "Payload must not be empty"},
            )

        trace_id = http_request.headers.get("X-TRACE-ID") or uuid.uuid4().hex
        event, dedupe_key, result = ingest_event(
            db=db,
            user_id=effective_user_id,
            event_type=request.event_type,
            payload=request.payload,
            device_id=request.device_id,
            recorded_at=request.recorded_at,
            trace_id=trace_id,
            health_subject_id=health_subject_id,
            device_row_id=device.id if device is not None else None,
        )

        if event is None:
            return DeviceIngestResponse(
                ok=True,
                data={
                    "event_id": None,
                    "dedupe_key": dedupe_key,
                    "message": "Event already exists (duplicate)",
                    **result,
                },
            )

        return DeviceIngestResponse(
            ok=True,
            data={
                "event_id": event.id,
                "dedupe_key": dedupe_key,
                **result,
            },
        )

    except ValueError as e:
        return DeviceIngestResponse(
            ok=False,
            error={"code": "VALIDATION_ERROR", "message": str(e)},
        )

    except VitalValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    except DeviceRateLimitExceeded as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    except HTTPException as e:
        logger.debug("[DEVICE_INGEST] Re-raising HTTPException status_code=%s", e.status_code)
        raise

    except Exception:
        logger.exception("Failed to ingest event")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "code": "INTERNAL_ERROR", "message": "Failed to ingest event"},
        )
