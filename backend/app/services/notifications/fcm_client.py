# app/services/notifications/fcm_client.py
"""
FCM HTTP v1 client for push notifications (Stage 16.6).
Uses service account JSON (path or content) and OAuth2; minimal deps (google-auth + requests).
When FCM_DISABLED=true, all sends are no-op and return success (dev mock).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_SEND_URL_TEMPLATE = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
MAX_TOKENS_PER_BATCH = 500  # scale: up to 1000 users


def _fcm_timeout_sec() -> int:
    """Stage 16.6.2: FCM_TIMEOUT_SECONDS env (default 5)."""
    try:
        return int(os.getenv("FCM_TIMEOUT_SECONDS", "5"))
    except ValueError:
        return 5


def _load_credentials():
    """Load service account credentials from env FCM_SERVICE_ACCOUNT_JSON (path or JSON string)."""
    raw = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
    except ImportError:
        logger.warning("[FCM] google-auth not installed; FCM disabled.")
        return None
    try:
        if raw.startswith("{"):
            info = json.loads(raw)
            return service_account.Credentials.from_service_account_info(
                info, scopes=[FCM_SCOPE]
            )
        # Path to JSON file
        return service_account.Credentials.from_service_account_file(
            raw, scopes=[FCM_SCOPE]
        )
    except Exception as e:
        logger.warning("[FCM] Failed to load credentials: %s", e)
        return None


def _get_access_token(credentials) -> Optional[str]:
    if credentials is None:
        return None
    try:
        from google.auth.transport.requests import Request
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        logger.warning("[FCM] Token refresh failed: %s", e)
        return None


def _build_fcm_message(
    token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
    android_priority: str = "normal",
    ttl_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Build FCM v1 message payload for one token."""
    message: Dict[str, Any] = {
        "message": {
            "token": token,
            "notification": {
                "title": title[:255] if title else "",
                "body": (body or "")[:1024],
            },
            "data": {k: str(v)[:1024] for k, v in (data or {}).items()},
            "android": {
                "priority": "high" if android_priority in ("high", "critical") else "normal",
            },
        }
    }
    if ttl_seconds is not None and ttl_seconds > 0:
        message["message"]["android"] = message["message"].get("android", {})
        message["message"]["android"]["ttl"] = f"{ttl_seconds}s"
    return message


def send_push_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
    android_priority: str = "normal",
    ttl_seconds: Optional[int] = None,
    project_id: Optional[str] = None,
    timeout_sec: Optional[int] = None,
) -> Tuple[int, List[Tuple[str, Optional[str], Optional[str]]]]:
    """
    Send the same notification to multiple FCM tokens (one request per token; batched by caller).
    Returns (success_count, [(token, message_id, error), ...]).
    When FCM_DISABLED=true, returns (len(tokens), [(t, "mock-id", None) for t in tokens]).
    Stage 16.6.2: Uses FCM_TIMEOUT_SECONDS env (default 5) when timeout_sec not provided.
    """
    effective_timeout = timeout_sec if timeout_sec is not None else _fcm_timeout_sec()
    if os.getenv("FCM_DISABLED", "").lower() in ("true", "1", "yes"):
        return (
            len(tokens),
            [(t, f"mock-{i}", None) for i, t in enumerate(tokens)],
        )

    pid = project_id or os.getenv("FCM_PROJECT_ID", "").strip()
    if not pid:
        logger.warning("[FCM] FCM_PROJECT_ID not set; skipping send.")
        return (0, [(t, None, "FCM_PROJECT_ID not set") for t in tokens])

    credentials = _load_credentials()
    token = _get_access_token(credentials)
    if not token:
        return (0, [(t, None, "FCM credentials unavailable") for t in tokens])

    url = FCM_SEND_URL_TEMPLATE.format(project_id=pid)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    results: List[Tuple[str, Optional[str], Optional[str]]] = []
    success_count = 0
    for fcm_token in tokens:
        if not fcm_token or not fcm_token.strip():
            results.append((fcm_token or "", None, "empty token"))
            continue
        payload = _build_fcm_message(
            token=fcm_token,
            title=title,
            body=body,
            data=data,
            android_priority=android_priority,
            ttl_seconds=ttl_seconds,
        )
        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=effective_timeout,
            )
            if resp.status_code == 200:
                out = resp.json()
                msg_id = (out.get("name") or "").split("/")[-1] if isinstance(out, dict) else None
                results.append((fcm_token, msg_id, None))
                success_count += 1
            else:
                err = resp.text[:500] if resp.text else str(resp.status_code)
                results.append((fcm_token, None, err))
                logger.warning("[NOTIF] failed fcm_send notification_id=%s error=%s",
                    (data or {}).get("notification_id", "?"), err)
        except requests.Timeout:
            results.append((fcm_token, None, "timeout"))
            logger.warning("[NOTIF] failed fcm_send timeout notification_id=%s",
                (data or {}).get("notification_id", "?"))
        except Exception as e:
            results.append((fcm_token, None, str(e)))
            logger.warning("[NOTIF] failed fcm_send notification_id=%s error=%s",
                (data or {}).get("notification_id", "?"), str(e))
    return (success_count, results)
