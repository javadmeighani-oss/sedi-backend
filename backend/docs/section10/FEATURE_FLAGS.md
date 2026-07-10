# Section 10 Feature Flags Registry

All flags default **OFF**. Do not enable in production without controlled rollout.

| Flag | Default | Purpose | Dependencies | Safe activation order | Rollback |
|------|---------|---------|--------------|----------------------|----------|
| `SEDI_CAREGIVER_DELIVERY_ENABLED` | false | Master switch for caregiver notification intent processing | Migrations 045–046, delivery channel (future) | After migration + channel ready | Set false |
| `SEDI_CAREGIVER_DAILY_REPORT_ENABLED` | false | Daily health status caregiver intents | Above + resolver tests | After master delivery flag | Set false |
| `SEDI_CAREGIVER_VITAL_ALERT_ENABLED` | false | Vital-alert caregiver intents | `notify_vital_alerts` migration 045 | After vital prefs deployed | Set false |
| `SEDI_CAREGIVER_CARE_SUMMARY_ENABLED` | false | Care summary caregiver intents | Migration 045 | After care summary QA | Set false |
| `SEDI_EMERGENCY_ESCALATION_ENABLED` | false | Emergency escalation state machine runtime | Migration 047, policy env vars | After escalation QA | Set false |
| `SEDI_VOICE_CALL_REQUESTS_ENABLED` | false | Create voice-call request records | Migration 047 | After telephony provider integration | Set false |
| `SEDI_VOICE_CALL_PROVIDER_ENABLED` | false | Allow provider dispatch (not implemented) | Voice provider credentials | Last | Set false |
| `SEDI_MEDICATION_STOCK_NOTIFICATIONS_ENABLED` | false | Low/empty stock user notifications | Migration 048 | After inventory UI QA | Set false |
| `SEDI_EVENT_REMINDER_SCHEDULER_ENABLED` | false | Event reminder job execution | Migration 023 (existing) | After event reminder QA | Set false |
| `SEDI_LIFESTYLE_REMINDER_SCHEDULER_ENABLED` | false | Lifestyle reminder job execution | Existing habits/events | After lifestyle data present | Set false |
| `SEDI_PROACTIVE_INTERACTION_ENABLED` | false | Proactive care policy engine | Quiet hours config | After policy review | Set false |
| `SEDI_PROACTIVE_FOLLOWUP_ENABLED` | false | Proactive follow-up notifications | Proactive master flag | After master flag | Set false |
| `SEDI_INACTIVITY_POLICY_ENABLED` | false | Inactivity policy integration | Escalation foundation | After escalation review | Set false |
| `SEDI_KB_EMBEDDINGS_ENABLED` | false | Generate KB chunk embedding metadata | Migration 049 | After embedding provider or fake provider tests | Set false |
| `SEDI_KB_VECTOR_RETRIEVAL_ENABLED` | false | Vector leg of hybrid retrieval | Embeddings populated | After embeddings | Set false |
| `SEDI_KB_HYBRID_RETRIEVAL_ENABLED` | false | Merge keyword + vector scores | Vector retrieval | After vector retrieval stable | Set false |

Optional policy env vars (no defaults that activate escalation):

- `SEDI_ESCALATION_INACTIVITY_WINDOW_MIN`
- `SEDI_ESCALATION_NOTIFICATION_ATTEMPTS`
- `SEDI_ESCALATION_NOTIFICATION_INTERVAL_MIN`
- `SEDI_ESCALATION_FEEDBACK_GRACE_MIN`
- `SEDI_ESCALATION_MAX_CAREGIVERS`
- `SEDI_ESCALATION_COOLDOWN_MIN`
- `SEDI_VITALS_ACTIVE_MINUTES` (default 5)
- `SEDI_VITALS_RECENT_MINUTES` (default 30)
- `SEDI_VITALS_STALE_MINUTES` (default 120)
