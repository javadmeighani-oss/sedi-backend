# Controlled Load Validation — 1000 registered / ~100 connected

GATE: SEDI-V1-BE-1000U-100CC-CONTROLLED-LOAD-VALIDATION-01

**THIS IS NOT PRODUCTION LOAD.**

## Endpoint mix (Profile B)

Documented before execution:

| Weight | Method | Path |
|-------:|--------|------|
| 0.25 | GET | `/auth/me` |
| 0.15 | GET | `/health-subjects/` |
| 0.15 | GET | `/notifications/unread` |
| 0.10 | GET | `/notifications/` |
| 0.10 | GET | `/lifestyle/context` |
| 0.10 | GET | `/user/habits` |
| 0.05 | GET | `/memory/latest` |
| 0.10 | POST | `/interact/chat` (AI stub) |

Chat share is bounded (~10%). Think time 50–250 ms between actions.

## Concurrency definitions

1. **CONNECTED/MIXED** — virtual users with think time (primary PASS/FAIL)
2. **SIMULTANEOUS BURST** — instant fan-out (stress characterization)

## AI stub

`SEDI_CAPACITY_AI_LATENCY_MS` (default 50). No real OpenAI.

## Worker matrix

1 / 2 / 4 API workers with `SEDI_DISABLE_SCHEDULER=1`; one scheduler process for Profile E.
