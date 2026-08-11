# Section 39 — SCIS / I5 / I6 / I7 / I8 Responsibility & Roadmap Freeze

```text
DECISION_OWNER = Javad
DECISION_STATUS = APPROVED
RECORDED_AT_UTC = 2026-08-11T04:10:00Z
PREDECESSOR_HANDOFF = v566 (SCIS-01 PASS)
```

## Principles

| System | Principle |
|---|---|
| I5 | Sedi knows the world |
| SCIS/RAG | Retrieve the right eligible knowledge/context |
| I6 | Sedi knows me |
| I7 | Sedi understands my history over time |
| I8 | Sedi helps me using me + history + trusted knowledge |

```text
I8_IS_RAG = NO
```

## Order

```text
SCIS Design Freeze = CLOSED
SCIS-01 = CLOSED / PASS
SCIS_DIRECT_CONTINUATION = DEFERRED
SCIS-02 = DEFERRED (until I6 phase unless proven narrow dependency)

NEXT = COMPLETE REMAINING I5
THEN = I6 → I7 → I8
THEN = SCIS fusion as needed → Smart Notifications / Care → Frontend/E2E
```

## Approval boundary

This decision authorizes **roadmap/architecture ordering only**.  
It does **not** authorize crawler activation, Production 061, RAG Production activation, or any I5/I6/I7/I8/SCIS-02 implementation Gate.
