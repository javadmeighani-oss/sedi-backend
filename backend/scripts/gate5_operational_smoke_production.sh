#!/usr/bin/env bash
# A4 Gate 75.2 — production READ-ONLY inbox smoke (has_user_response).
# Replaces Gate 5 script body ONLY on ops/a4-75-2-inbox-smoke-readonly.
# NO env mutation, NO DB writes, NO migration, NO canary, NO backlog flush.
set -Eeuo pipefail

echo "=== GATE ==="
echo "GATE=SEDI-V1-A4-BACKEND-PROMOTION-PROD-ACTIVATION-75.2-SMOKE"
echo "MODE=READ_ONLY"
docker inspect sedi-backend --format 'RUNNING_TAG={{.Config.Image}}'

echo "=== ENV PRESENCE ==="
docker exec -i sedi-backend python - <<'PY'
import os
print(f"SEDI_NOTIFICATION_PROVIDER_DELIVERY_ENABLED={os.getenv('SEDI_NOTIFICATION_PROVIDER_DELIVERY_ENABLED', 'UNSET')}")
print(f"SEDI_DISABLE_SCHEDULER={os.getenv('SEDI_DISABLE_SCHEDULER', 'UNSET')}")
PY

echo "=== ALEMBIC ==="
docker exec sedi-backend python -m alembic -c backend/alembic.ini current

echo "=== HEALTH ==="
curl -fsS http://127.0.0.1:8000/health
echo ""
echo "=== HEALTHZ ==="
curl -fsS http://127.0.0.1:8000/healthz
echo ""

echo "=== INBOX SMOKE (primary user_id=1; token never logged) ==="
docker exec -i sedi-backend python - <<'PY'
from __future__ import annotations

import json
from typing import Any

import httpx
from sqlalchemy import text

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import SessionFactory

PRIMARY_USER_ID = 1
BASE = "http://127.0.0.1:8000"


def summarize_item(n: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": n.get("id"),
        "is_read": n.get("is_read"),
        "has_user_response": n.get("has_user_response"),
        "type": n.get("type"),
    }


db = SessionFactory()
try:
    db.rollback()
    db.execute(text("SET TRANSACTION READ ONLY"))
    user = db.query(models.User).filter(models.User.id == PRIMARY_USER_ID).first()
    if not user:
        raise SystemExit("PRIMARY_USER_MISSING")
    print(f"PRIMARY_USER_ID={user.id}")
finally:
    db.close()

token = create_access_token({"user_id": PRIMARY_USER_ID})
headers = {"Authorization": f"Bearer {token}"}

with httpx.Client(timeout=30.0) as client:
    r = client.get(f"{BASE}/notifications/", headers=headers, params={"limit": 50, "offset": 0})
    print(f"GET_NOTIFICATIONS_HTTP={r.status_code}")
    if r.status_code >= 500:
        print("PRODUCTION_5XX=YES")
        print(r.text[:500])
        raise SystemExit(1)
    print("PRODUCTION_5XX=NO")
    if r.status_code != 200:
        print(f"UNEXPECTED_STATUS={r.status_code}")
        print(r.text[:500])
        raise SystemExit(1)

    body = r.json()
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        print(f"ENVELOPE_KEYS={list(body.keys()) if isinstance(body, dict) else type(body)}")
        raise SystemExit("UNEXPECTED_ENVELOPE")

    items = data.get("notifications") or data.get("items") or []
    unread = data.get("unread_count")
    print(f"ITEM_COUNT={len(items)}")
    print(f"UNREAD_COUNT={unread}")

    if not items:
        print("HAS_USER_RESPONSE_FIELD=NOT_OBSERVED_EMPTY_INBOX")
        print("READ_ONLY_CASE=NOT_OBSERVED")
        print("RESPONDED_CASE=NOT_OBSERVED")
        print(
            "UNREAD_PROJECTION_SMOKE=PASS_EMPTY_OR_COUNT_PRESENT"
            if unread is not None
            else "UNREAD_PROJECTION_SMOKE=FAIL"
        )
        raise SystemExit(0 if unread is not None else 1)

    missing = [i for i, n in enumerate(items) if "has_user_response" not in n]
    non_bool = [n.get("id") for n in items if not isinstance(n.get("has_user_response"), bool)]
    if missing or non_bool:
        print(f"HAS_USER_RESPONSE_FIELD=FAIL missing={missing} non_bool_ids={non_bool}")
        print("SAMPLE=", json.dumps(summarize_item(items[0]), default=str))
        raise SystemExit(1)

    print("HAS_USER_RESPONSE_FIELD=PASS")
    print("SAMPLE_ITEMS=" + json.dumps([summarize_item(n) for n in items[:5]], default=str))

    read_only = next(
        (n for n in items if n.get("is_read") is True and n.get("has_user_response") is False),
        None,
    )
    if read_only is None:
        false_any = next((n for n in items if n.get("has_user_response") is False), None)
        if false_any is not None:
            print(
                "READ_ONLY_CASE=PASS_FALSE_OBSERVED id=%s is_read=%s"
                % (false_any.get("id"), false_any.get("is_read"))
            )
        else:
            print("READ_ONLY_CASE=NOT_OBSERVED")
    else:
        print("READ_ONLY_CASE=PASS id=%s" % read_only.get("id"))

    responded = next((n for n in items if n.get("has_user_response") is True), None)
    if responded is None:
        print("RESPONDED_CASE=NOT_OBSERVED")
    else:
        print("RESPONDED_CASE=PASS id=%s" % responded.get("id"))

    if unread is None:
        print("UNREAD_PROJECTION_SMOKE=FAIL_MISSING_UNREAD_COUNT")
        raise SystemExit(1)
    print("UNREAD_PROJECTION_SMOKE=PASS")
PY

echo "=== SMOKE_DONE ==="
