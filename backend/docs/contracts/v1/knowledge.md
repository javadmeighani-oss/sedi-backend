# V1 Contract: Knowledge

**Base path:** `/knowledge` (public), `/knowledge/admin` (admin).  
**Envelope:** Public endpoints use `ApiResponse` (`ok`, `data`, `error`). Admin endpoints may return raw models or `ApiResponse` (see OpenAPI).

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /knowledge/next_question | Next question for user (optional notify, in_app, lang) |
| POST | /knowledge/extract_from_message | Extract facts from chat message |
| POST | /knowledge/apply_answer | Apply user answer (confirm_candidate or profile/fact) |
| POST | /knowledge/admin/candidates/create | Create candidate (admin) |
| POST | /knowledge/admin/candidates/{id}/accept | Accept candidate → fact |
| POST | /knowledge/admin/candidates/{id}/reject | Reject candidate |
| POST | /knowledge/admin/answers/apply | Apply answer (admin) |
| GET | /knowledge/admin/users/{user_id}/facts | List facts for user (admin) |

---

## Headers

| Header | Required | Notes |
|--------|----------|------|
| Content-Type | Yes (POST) | application/json |
| X-Admin-Token | For /knowledge/admin/* | If ADMIN_TOKEN env set |

---

## 1. GET /knowledge/next_question

**Query params:** `user_id` (required), `lang` (optional: fa | en), `notify` (bool), `in_app` (bool).

**Success (200) – question:**
```json
{
  "ok": true,
  "data": {
    "question_type": "confirm_candidate",
    "candidate_id": 5,
    "field_key": "sleep_window",
    "text": "Do you usually sleep between 10pm and 6am?",
    "options": ["Yes", "No"],
    "display_title": "Quick question",
    "display_body": "Do you usually sleep between 10pm and 6am?",
    "policy": { "asked_today": 1, "max_per_day": 3 }
  },
  "error": null
}
```

**Success (200) – no question (fatigue or none available):**
```json
{
  "ok": true,
  "data": {
    "status": "no_question",
    "reason": "fatigue_control",
    "next_eligible_at": "2025-02-23T00:00:00",
    "policy": { "asked_today": 3, "max_per_day": 3 }
  },
  "error": null
}
```

**Error (404):** User not found (HTTPException, may be non-envelope).

---

## 2. POST /knowledge/extract_from_message

**Request body:**
```json
{
  "user_id": 1,
  "text": "I usually sleep at 11pm and wake at 6am.",
  "language": "fa",
  "source_message_id": null
}
```

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "extracted_count": 1,
    "created_candidates_count": 1,
    "auto_accepted_count": 0,
    "ignored_count": 0
  },
  "error": null
}
```

---

## 3. POST /knowledge/apply_answer

**Request body (confirm_candidate):**
```json
{
  "user_id": 1,
  "candidate_id": 5,
  "question_type": "confirm_candidate",
  "value": "Yes",
  "field_key": null,
  "answer": null
}
```

**Request body (profile/fact):**
```json
{
  "user_id": 1,
  "field_key": "birth_year",
  "value": 1990,
  "candidate_id": null,
  "question_type": null,
  "answer": null
}
```

**Success (200):** `ApiResponse` with `data` containing outcome, policy, etc.

---

## 4. Admin endpoints (V1 in scope)

- **POST /knowledge/admin/candidates/create:** Body: user_id, source, fact_type, value_json, confidence, evidence. Returns `KcCandidateRead` (no envelope).
- **POST /knowledge/admin/candidates/{id}/accept:** Returns `KcUserFactRead` (no envelope).
- **POST /knowledge/admin/answers/apply:** Returns `{"ok": true, ...}` or similar (see OpenAPI).
- **GET /knowledge/admin/users/{user_id}/facts:** Returns list of `KcUserFactRead`.

---

## Notes

- **Idempotency / dedupe:** next_question with notify=true uses dedupe for kc_confirm notifications (e.g. 10-minute window). in_app=true creates inbox notification only, skips push delivery.
- **Fatigue:** next_question may return `status: no_question` with `reason: fatigue_control` or `no_available_question` and `next_eligible_at`.
