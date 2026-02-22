# V1 Contract: Interact

**Base path:** `/interact`  
**Envelope:** Endpoints return `InteractionResponse` directly (no `ApiResponse` envelope). Errors may be HTTPException (4xx/5xx) with non-envelope body.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /interact/introduce | Introduce user (secret_key); optional user_id to upgrade anonymous |
| POST | /interact/chat | Send message to Sedi (GPT) |
| POST | /interact/onboarding | Onboarding step (if exists) |
| POST | /interact/greeting | Get greeting (if exists) |
| GET  | /interact/history | Chat history (if exists) |

---

## Headers

| Header | Required | Notes |
|--------|----------|------|
| Content-Type | Yes (POST) | application/json |

---

## 1. POST /interact/introduce

**Query params:** `secret_key` (required), `lang` (default en), `user_id` (optional).

**Example:**
```bash
curl -sS -X POST "http://127.0.0.1:8000/interact/introduce?secret_key=dev-key&lang=en" -H "Content-Type: application/json"
```

**Success (200):**
```json
{
  "message": "Hello! I'm Sedi...",
  "language": "en",
  "user_id": 1,
  "timestamp": "2025-02-22T12:00:00",
  "requires_security_check": false,
  "detected_name": null
}
```

**Error (4xx/5xx):** Standard HTTPException; no envelope.

---

## 2. POST /interact/chat

**Request body:**
```json
{
  "user_id": 1,
  "message": "Hello, how are you?"
}
```

**Success (200):**
```json
{
  "message": "I'm doing well, thank you! ...",
  "language": "en",
  "user_id": 1,
  "timestamp": "2025-02-22T12:00:00",
  "requires_security_check": false,
  "detected_name": null
}
```

**Error (400):** Empty message or invalid user_id.
```json
{
  "detail": "Message cannot be empty"
}
```

**Error (404):**
```json
{
  "detail": "User with id 999 not found. Please check your user_id or start a new conversation."
}
```

---

## 3. Onboarding / Greeting / History

Where implemented: same base path `/interact/...`. Request/response shapes are endpoint-specific; see OpenAPI schema. No `ApiResponse` envelope.

---

## Notes

- Interact does **not** use the `ApiResponse` envelope; it uses `InteractionResponse` for success.
- Language is detected from message content only (no query param override for chat).
- Idempotency: not required for chat; introduce is idempotent for same secret_key + user_id.
