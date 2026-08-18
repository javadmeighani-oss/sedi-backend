# SEDI Cursor Authoritative Handoff - v608

> Complete successor to v607. I5-S49 remediation-03 closure: lexical-only FTS path verified, domain fail-closed, CI head 067 green on KNOW-01/KNOW-05/SCIS-01. Master Log §317.

```text
VERSION=v608
STATUS=CURRENT
PREDECESSOR=v607
RECORDED_AT_UTC=2026-08-18T05:35:00Z
MASTER_LOG=§317
CURSOR_HANDOFF=v608
CHATGPT_CONTINUITY=v622
GATE_OUTCOME=PASS
FULL_GATE_CLOSURE=PASS
HARD_STOP=NO
RULES_IN_FORCE_CHECK=PASS
TOKEN_EFFICIENCY_CHECK=PASS

I5_S49_REMEDIATION_03=PASS
LEXICAL_ONLY_SERVING=YES
VECTOR_GENERATION_FROM_I5_S49=0
EMBEDDING_VECTOR_WRITES_FROM_I5_S49=0
DOMAIN_FAIL_CLOSED=YES
CI_ALEMBIC_HEAD=067_i7_lifelong_memory_foundation
CI_KNOW01=PASS
CI_KNOW05=PASS
CI_SCIS01=PASS
FINAL_HEAD=9cc0339053dd95ab142bdafad557096e1945f5ff
PRODUCTION_MUTATION=NO
NEW_MIGRATION=NO

NEXT_GATE=SEDI-V1 I5-S49 PRODUCTION OBSERVE-02 POST-2026-08-21 WEEKLY FIRE (PROPOSED ONLY)
NEXT_GATE_AUTHORIZED=NO
```

## Key paths

- `backend/app/services/scis/lexical_indexing.py` — lexical-only KCE writer (no embed_texts, no embedding_vector)
- `backend/app/services/scis/serving_bridge.py` — eligible KU bridge
- `backend/app/services/i5/governed_low_risk_eligibility.py` — manifest-governed fail-closed domain eligibility
- `backend/tests/test_i5_s49_trusted_source_control.py` — regression proof suite
- `.github/workflows/i5-know01-source-registry-runtime.yml` — Alembic head 067
- `.github/workflows/i5-know05-weekly-acquisition-runtime.yml` — Alembic head 067
- `.github/workflows/scis-01-core-retrieval-runtime.yml` — Alembic head 067

## Constraints still in force

- No automatic vector generation from I5-S49 path
- No new migrations / schema changes without explicit gate
- No production deploy or data mutation
- PubMed / high-risk connectors remain REVIEW_REQUIRED / fail-closed
