# Section43 — Lifelong user memory architecture (schema-safe)

```text
GATE=SEDI-V1 SECTION43
I7_IS_NOT_ONLY_SUMMARY_STORAGE=YES
USER_OWNS_MEMORY=YES
SEDI_MANAGES_UNDER_GOVERNANCE=YES
HISTORY_IS_NOT_DIAGNOSIS=YES
CANONICAL_DB_IS_SOURCE_OF_TRUTH=YES
VECTOR_IS_DERIVED_ARTIFACT=YES
```

## Principle

Sedi is a long-term health companion. Understanding must improve through
consent-controlled, versioned, reconstructable memory: Remember, Understand,
Correct, Forget, Evolve. The user owns the memory.

## Layer classification (current code, not memory)

| Layer | Status | Notes |
|---|---|---|
| 4.1 Canonical I6 facts (`user_memory_facts`) | PARTIAL→DONE for V1 control | Consent, source, validity, correction, deletion, supersede chain, audit timestamps. History retained. Chat auto-extract still off (intentional). |
| 4.2 User event timeline | PARTIAL | Fragmented: `user_events`, `user_lifestyle_events`, `interaction_events`, `care_episodes`, `device_events`, `notification_feedback`. Who/when/source exist per table; no unified lifelong timeline view. |
| 4.3 Health/lifestyle timeline | PARTIAL | Lifestyle/events/physiology stored as history. I6 blocks diagnosis/dose/prescription keys. Competing `user_facts` / `kc_user_facts` remain non-canonical. |
| 4.4 Semantic summaries (`user_period_summaries`) | DONE service + PARTIAL jobs | DAILY/WEEKLY/MONTHLY/YEARLY, version, rebuild, invalidation, generator_version in JSON. Jobs registered dormant. |
| 4.5 Long-term compact profile | MISSING | Must be derived. New table = DCR. |
| Legacy `daily_memory_summaries` | CONFLICTING | Not I7 SoT. Do not revive as authority. |
| Raw `memory` chat turns | PARTIAL | Hot context only. No 100-year prune job yet (DCR). |

## Current truth without losing history

`list_facts` = currently true (active, not expired).
`list_fact_history` = superseded/rejected chain via `supersedes_fact_id`.
Forget is soft-invalidation, not hard wipe (hard-delete/export-delivery = DCR).

## Scientific vs personal retrieval

I5 governed knowledge → future scientific RAG.
I6/I7 personal facts/summaries → personal context retrieval.
Must never merge user-memory vectors into the medical KU/KCE corpus.

## Crawler time (unchanged)

CANONICAL_GLOBAL_TIME=Friday 00:00 UTC
LOCAL_REFERENCE=Friday 03:30 Asia/Tehran
CURRENT_WEEKLY_SOURCE_SCOPE=NHS_ONLY_BOUNDED
I7 user week remains Tehran Monday ISO week and is NOT the I5 knowledge week.
