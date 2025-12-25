# Notification Contract

## Section 1: Notification Object Structure

```json
{
  "id": "string",
  "type": "info" | "alert" | "reminder" | "check_in" | "achievement",
  "priority": "low" | "normal" | "high" | "urgent",
  "title": "string | null",
  "message": "string",
  "actions": [Action] | null,
  "metadata": NotificationMetadata | null,
  "created_at": "ISO 8601 datetime string",
  "is_read": boolean
}
```

## Section 4: Action Object

```json
{
  "id": "string",
  "label": "string",
  "type": "quick_reply" | "navigate" | "dismiss" | "custom",
  "payload": object | null
}
```

## Section 5: Feedback Payload

```json
{
  "notification_id": "string",
  "action_id": "string | null",
  "reaction": "seen" | "interact" | "dismiss" | "like" | "dislike",
  "feedback_text": "string | null",
  "timestamp": "ISO 8601 datetime string"
}
```

## Section 6: NotificationMetadata Object

```json
{
  "language": "ISO 639-1 code | null",
  "tone": "string | null",
  "context": "string | null",
  "source": "string | null"
}
```

## Section 7: GET /notifications Response

```json
{
  "ok": boolean,
  "data": {
    "notifications": [Notification],
    "total": number,
    "unread_count": number
  },
  "error": ErrorInfo | null
}
```

