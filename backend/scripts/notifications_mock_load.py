#!/usr/bin/env python3
"""
Notifications Mock Load Script (Stage 16.6.7)

Calls POST /notifications/admin/test_push?deliver=true for multiple users.
Use with FCM_DISABLED=true for mock delivery (no real FCM sends).
Prints summary metrics. Does not log tokens or secrets.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
USER_ID_START = int(os.environ.get("USER_ID_START", "1"))
USER_COUNT = int(os.environ.get("USER_COUNT", "200"))
PUSH_PER_USER = int(os.environ.get("PUSH_PER_USER", "2"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "10"))


def _request(user_id: int, channel: str = "engagement") -> Tuple[bool, float, int]:
    """
    POST test_push?deliver=true. Returns (ok, latency_sec, sent_count).
    """
    url = f"{BASE_URL}/notifications/admin/test_push"
    params = {"deliver": "true"}
    headers = {
        "Content-Type": "application/json",
        "X-Admin-Token": ADMIN_TOKEN,
    }
    payload = {"user_id": user_id, "channel": channel}

    start = time.perf_counter()
    try:
        r = requests.post(
            url,
            params=params,
            json=payload,
            headers=headers,
            timeout=30,
        )
        latency = time.perf_counter() - start
        if r.status_code != 200:
            return False, latency, 0
        data = r.json()
        if not isinstance(data, dict) or not data.get("ok"):
            return False, latency, 0
        sent = data.get("data", {}).get("sent_count", 0)
        return True, latency, int(sent) if isinstance(sent, (int, float)) else 0
    except Exception:
        latency = time.perf_counter() - start
        return False, latency, 0


def main():
    if not ADMIN_TOKEN:
        print("ADMIN_TOKEN is required. Set it in the environment.")
        sys.exit(1)

    tasks = []
    for u in range(USER_ID_START, USER_ID_START + USER_COUNT):
        for _ in range(PUSH_PER_USER):
            tasks.append(u)

    requested = len(tasks)
    delivered = 0
    failures = 0
    latencies = []

    print(f"[Load] BASE_URL={BASE_URL} users={USER_ID_START}..{USER_ID_START + USER_COUNT - 1}")
    print(f"[Load] requested={requested} concurrency={CONCURRENCY}")
    print("-" * 40)

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = {ex.submit(_request, uid): uid for uid in tasks}
        for fut in as_completed(futures):
            ok, lat, sent = fut.result()
            latencies.append(lat)
            if ok:
                delivered += sent
            else:
                failures += 1

    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    print(f"requested: {requested}")
    print(f"delivered (sent_count sum): {delivered}")
    print(f"failures: {failures}")
    print(f"avg_latency_sec: {avg_lat:.3f}")
    print("-" * 40)
    print("[Load] Done. Use FCM_DISABLED=true for mock delivery.")


if __name__ == "__main__":
    main()
