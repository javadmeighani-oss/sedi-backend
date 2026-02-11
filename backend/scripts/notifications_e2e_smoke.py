#!/usr/bin/env python3
"""
Notifications E2E Smoke Script (Stage 16.6.1)

Reads BASE_URL, ADMIN_TOKEN, USER_ID from env. Calls admin endpoints,
enqueues test push, triggers deliver_pending, prints results.
Safe for local/dev. Do not use against production.
"""

import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
USER_ID = int(os.environ.get("USER_ID", "1"))


def main():
    headers = {}
    if ADMIN_TOKEN:
        headers["X-Admin-Token"] = ADMIN_TOKEN

    print(f"[E2E] BASE_URL={BASE_URL} USER_ID={USER_ID}")
    print("-" * 40)

    # 1. List push devices
    r = requests.get(
        f"{BASE_URL}/notifications/admin/push_devices",
        params={"user_id": USER_ID},
        headers=headers,
        timeout=10,
    )
    print(f"[1] GET push_devices: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        if data.get("ok"):
            devices = data.get("data", {}).get("devices", [])
            print(f"    -> {len(devices)} device(s)")
            for d in devices:
                print(f"       id={d.get('id')} token_masked={d.get('token_masked', 'N/A')}")
        else:
            print(f"    -> {data.get('error', {})}")
    else:
        print(f"    -> {r.text[:200]}")

    # 2. Enqueue test push
    r = requests.post(
        f"{BASE_URL}/notifications/admin/test_push",
        json={
            "user_id": USER_ID,
            "channel": "engagement",
            "title": "E2E Smoke",
            "body": "Test from notifications_e2e_smoke.py",
        },
        headers={**headers, "Content-Type": "application/json"},
        timeout=10,
    )
    print(f"[2] POST test_push: {r.status_code}")
    notif_id = None
    if r.status_code == 200:
        data = r.json()
        if data.get("ok"):
            notif_id = data.get("data", {}).get("notification_id")
            print(f"    -> notification_id={notif_id}")
        else:
            print(f"    -> {data.get('error', {})}")

    # 3. Deliver pending
    r = requests.post(
        f"{BASE_URL}/notifications/deliver_pending",
        params={"limit": 10},
        headers=headers,
        timeout=15,
    )
    print(f"[3] POST deliver_pending: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        if data.get("ok"):
            sent = data.get("data", {}).get("sent_count", 0)
            print(f"    -> sent_count={sent}")
        else:
            print(f"    -> {data.get('error', {})}")

    # 4. Submit feedback (optional; if we have notif_id)
    if notif_id:
        r = requests.post(
            f"{BASE_URL}/notifications/{notif_id}/feedback",
            json={"action": "like", "client_ts": "2025-02-11T12:00:00Z"},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        print(f"[4] POST feedback (action=like): {r.status_code}")
        if r.status_code == 200 and r.json().get("ok"):
            print("    -> feedback recorded")
        else:
            print(f"    -> {r.text[:100]}")

    print("-" * 40)
    print("[E2E] Done. Check DB for notification_feedback row if step 4 ran.")


if __name__ == "__main__":
    main()
