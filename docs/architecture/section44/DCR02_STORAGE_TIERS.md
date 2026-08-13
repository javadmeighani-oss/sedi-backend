# DCR-02 HOT / WARM / ARCHIVE + raw-chat policy — APPROVED MODEL

```text
DCR02_DECISION=APPROVE_MODEL
DCR02_SCHEMA_OR_INFRA_CHANGE_REQUIRED=YES
RAW_CHAT_UNLIMITED_RETENTION=FORBIDDEN
IMPLEMENTED=NO
```

Tiers are assigned by access frequency, canonical vs derived, consent, sensitivity,
rebuildability, and deletion duty — not age alone.

## HOT_MODEL

Online primary tables, frequent read:

- active `user_memory_facts`
- current `user_lifelong_profiles` (once exists)
- current-period `user_period_summaries`
- `memory` chat within retention window
- recent `interaction_events` / `physiological_measurements` (ops window)

## WARM_MODEL

Online, less frequent, still SQL:

- superseded UMF rows (historical truth)
- `user_events`, `user_lifestyle_events`, care events
- weekly/monthly UPS
- consent/audit rows

## ARCHIVE_MODEL

Low-frequency continuity. Logical first (status/partition key); physical archive
schema or object store only after an infra Gate.

- yearly UPS
- old superseded UMF beyond warm window
- compact profile history
- export receipts (metadata)

Archive remains user-owned and deletable. Backup copies must honor deletion
policy (legal/ops Gate).

## RAW_CHAT_RETENTION_MODEL

`memory` is ephemeral/HOT context, not canonical LTM.

BASE retain 30 days (LOW 14 / HIGH 90). After expiry: delete body; optional
SHA256 of user_message retained on a future `memory_source_hash` column only if
a fact cites that turn. No silent sentence→fact extraction.

After compaction, facts remain if they were explicitly written under consent.
Deleting a fact invalidates derived summaries/profile even if chat is gone.

Some raw rows may be retained longer only under explicit safety/audit legal hold
(separate status, not default).

## Later schema/infra

- `memory.retain_until` or job keyed by `created_at`
- optional `user_memory_facts.source_content_hash`
- partition/archive job for UPS/UMF
- no 066 / no RAG
