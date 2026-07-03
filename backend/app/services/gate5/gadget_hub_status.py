"""Gate 5-A — Gadget Hub status and sensor registry helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.models import Device, DeviceSensor

GADGET_HUB_DEVICE_TYPE = "gadget_hub"

OPERATIONAL_HUB_STATUSES = frozenset(
    {"not_registered", "connected", "recently_seen", "disconnected", "revoked", "unknown"}
)

SENSOR_TYPES = frozenset(
    {
        "ecg",
        "heart_rate",
        "blood_pressure",
        "glucose",
        "temperature",
        "spo2",
        "steps",
        "activity",
        "balance",
        "fall",
        "sweat",
        "respiratory_rate",
        "unknown",
    }
)

SENSOR_CONNECTION_STATUSES = frozenset(
    {"connected", "recently_seen", "disconnected", "disabled", "unknown"}
)

CONNECTED_THRESHOLD_MIN = int(os.getenv("DEVICE_DISCONNECTED_THRESHOLD_MIN", "15"))
RECENTLY_SEEN_THRESHOLD_MIN = int(os.getenv("GADGET_HUB_RECENTLY_SEEN_THRESHOLD_MIN", "60"))


def is_gadget_hub(device: Device) -> bool:
    return (device.device_type or "").strip() == GADGET_HUB_DEVICE_TYPE


def find_active_gadget_hub_for_user(db: Session, user_id: int) -> Optional[Device]:
    """Return the user's active Gadget Hub row, if any."""
    return (
        db.query(Device)
        .filter(
            Device.user_id == user_id,
            Device.device_type == GADGET_HUB_DEVICE_TYPE,
            Device.status == "active",
            Device.revoked_at.is_(None),
        )
        .order_by(Device.id.desc())
        .first()
    )


def find_gadget_hub_for_user(db: Session, user_id: int) -> Optional[Device]:
    """Latest gadget_hub row for user (active or revoked), for status display."""
    return (
        db.query(Device)
        .filter(Device.user_id == user_id, Device.device_type == GADGET_HUB_DEVICE_TYPE)
        .order_by(Device.id.desc())
        .first()
    )


def compute_hub_operational_status(device: Optional[Device], now: Optional[datetime] = None) -> str:
    """Operational connectivity label only — not clinical."""
    if device is None:
        return "not_registered"
    if device.status == "revoked" or device.revoked_at is not None:
        return "revoked"

    now = now or datetime.utcnow()
    reference = device.last_heartbeat_at or device.last_seen_at
    if reference is None:
        return "unknown"

    age_min = (now - reference).total_seconds() / 60.0
    if age_min <= CONNECTED_THRESHOLD_MIN:
        return "connected"
    if age_min <= RECENTLY_SEEN_THRESHOLD_MIN:
        return "recently_seen"
    return "disconnected"


def _serialize_hub_device(device: Device, operational_status: str) -> Dict[str, Any]:
    return {
        "device_id": device.device_id,
        "device_type": device.device_type,
        "status": operational_status,
        "last_seen_at": device.last_seen_at,
        "last_heartbeat_at": device.last_heartbeat_at,
        "last_sync_at": device.last_sync_at,
        "battery_level": device.battery_level,
        "firmware_version": device.firmware_version,
        "hardware_version": device.hardware_version,
    }


def _parse_capabilities(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _serialize_sensor(sensor: DeviceSensor) -> Dict[str, Any]:
    return {
        "sensor_key": sensor.sensor_key,
        "sensor_type": sensor.sensor_type,
        "display_name": sensor.display_name,
        "connection_status": sensor.connection_status,
        "battery_level": sensor.battery_level,
        "firmware_version": sensor.firmware_version,
        "hardware_version": sensor.hardware_version,
        "last_seen_at": sensor.last_seen_at,
        "last_signal_at": sensor.last_signal_at,
        "capabilities": _parse_capabilities(sensor.capabilities_json),
    }


def list_active_sensors_for_hub(db: Session, hub: Device) -> List[DeviceSensor]:
    return (
        db.query(DeviceSensor)
        .filter(DeviceSensor.hub_device_id == hub.id, DeviceSensor.revoked_at.is_(None))
        .order_by(DeviceSensor.sensor_key.asc())
        .all()
    )


def build_hub_status_payload(db: Session, user_id: int, now: Optional[datetime] = None) -> Dict[str, Any]:
    hub = find_gadget_hub_for_user(db, user_id)
    if hub is None:
        return {
            "has_hub": False,
            "status": "not_registered",
            "hub": None,
            "sensors": [],
        }

    operational = compute_hub_operational_status(hub, now=now)
    sensors = list_active_sensors_for_hub(db, hub)
    return {
        "has_hub": True,
        "status": operational,
        "hub": _serialize_hub_device(hub, operational),
        "sensors": [_serialize_sensor(s) for s in sensors],
    }


def apply_heartbeat_metadata(
    device: Device,
    *,
    now: datetime,
    status: Optional[str] = None,
    battery_level: Optional[float] = None,
    firmware_version: Optional[str] = None,
    hardware_version: Optional[str] = None,
    hub_status: Optional[str] = None,
    last_sync_at: Optional[datetime] = None,
) -> None:
    device.last_seen_at = now
    device.last_heartbeat_at = now
    if status is not None:
        device.status = str(status)
    if battery_level is not None:
        device.battery_level = float(battery_level)
    if firmware_version is not None:
        device.firmware_version = str(firmware_version)[:64]
    if hardware_version is not None:
        device.hardware_version = str(hardware_version)[:64]
    if hub_status is not None:
        device.hub_status = str(hub_status)[:32]
    if last_sync_at is not None:
        device.last_sync_at = last_sync_at


def sync_hub_sensors(
    db: Session,
    hub: Device,
    sensors_payload: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Upsert sensors by hub + sensor_key. No health interpretation."""
    now = now or datetime.utcnow()
    synced_keys: List[str] = []
    created = 0
    updated = 0

    for item in sensors_payload:
        sensor_key = str(item["sensor_key"]).strip()
        if not sensor_key:
            continue

        sensor_type = str(item.get("sensor_type") or "unknown").strip().lower()
        if sensor_type not in SENSOR_TYPES:
            sensor_type = "unknown"

        connection_status = str(item.get("connection_status") or "unknown").strip().lower()
        if connection_status not in SENSOR_CONNECTION_STATUSES:
            connection_status = "unknown"

        capabilities = item.get("capabilities")
        capabilities_json = json.dumps(capabilities, ensure_ascii=False) if capabilities is not None else None

        last_signal_at = item.get("last_signal_at")
        last_seen_at = item.get("last_seen_at") or now

        row = (
            db.query(DeviceSensor)
            .filter(DeviceSensor.hub_device_id == hub.id, DeviceSensor.sensor_key == sensor_key)
            .first()
        )
        if row is None:
            row = DeviceSensor(
                hub_device_id=hub.id,
                sensor_key=sensor_key,
                sensor_type=sensor_type,
                display_name=item.get("display_name"),
                connection_status=connection_status,
                capabilities_json=capabilities_json,
                battery_level=item.get("battery_level"),
                firmware_version=item.get("firmware_version"),
                hardware_version=item.get("hardware_version"),
                last_seen_at=last_seen_at,
                last_signal_at=last_signal_at,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            created += 1
        else:
            row.sensor_type = sensor_type
            row.display_name = item.get("display_name") if item.get("display_name") is not None else row.display_name
            row.connection_status = connection_status
            if capabilities_json is not None:
                row.capabilities_json = capabilities_json
            if item.get("battery_level") is not None:
                row.battery_level = item.get("battery_level")
            if item.get("firmware_version") is not None:
                row.firmware_version = item.get("firmware_version")
            if item.get("hardware_version") is not None:
                row.hardware_version = item.get("hardware_version")
            row.last_seen_at = last_seen_at
            if last_signal_at is not None:
                row.last_signal_at = last_signal_at
            row.updated_at = now
            row.revoked_at = None
            updated += 1

        synced_keys.append(sensor_key)

    hub.last_sync_at = now
    hub.last_seen_at = now
    db.add(hub)
    db.commit()

    return {
        "synced_count": len(synced_keys),
        "created": created,
        "updated": updated,
        "sensor_keys": synced_keys,
    }
