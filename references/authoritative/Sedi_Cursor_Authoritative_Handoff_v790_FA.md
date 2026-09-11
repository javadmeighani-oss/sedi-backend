# SEDI Cursor Authoritative Handoff - v790

I5/I6/I7/I8 Lifestyle weekly Nutrition+Exercise backend — **CLOSED**.

Do not modify v789 / §496 history. This file supersedes v789 as CURRENT tip.

```
VERSION=v790
STATUS=CURRENT
LOGICAL_PREDECESSOR=v789
v789_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§497
GATE=SEDI-V1-I5-I6-I7-I8-LIFESTYLE-WEEKLY-PLAN-DIFF-VERIFY-COMMIT-PUSH-CI-CLOSURE-01
GATE_RESULT=PASS
WEEKLY_NUTRITION_EXERCISE_BACKEND=CLOSED
FRONTEND_WEEKLY_UI=PENDING
SCHEMA_OR_MIGRATION_CHANGED=NO
PROD_DEPLOY_PERFORMED=NO
FRONTEND_MUTATION=NO
WORKFLOW_MUTATION=NO
FORCE_PUSH=NO
NEXT_GATE_AUTHORIZED=NO
```

## Heads / commits

```
BASELINE_HEAD=c725d771064f79c8069d279a7b69c55124bb4795
CODE_COMMIT_SHA=bfe59ff4a21de410f1043edbd4b873cd9fe2a88f
IMPLEMENTATION_DOCS_COMMIT_SHA=b1523001662630c92a5277754de5c00e11bb17ca
BRANCH=feature/a3-authority-chat-stream-profile-foundation
```

## CI (relevant)

```
CI_RUN_ID=34639894762
CI_WORKFLOW=A3 Lifestyle Hub Minimal PG16
CI_RESULT=PASS
CI_ADJACENT_PASS=A3 Self Other (34639894992); A3 Profile I6 I8 Summary (34639894907)
CI_COLLATERAL=stale alembic head pins in older workflows (not delta-caused; workflow edits forbidden)
```

## Authority proof

```
SHARED_DAILY_PLAN=YES
CYCLE_MODEL=ROLLING_7_LOCAL_DAYS
CYCLE_START_BACKEND_ONLY=YES (I8 presentation_json.cycle_start_local_date)
CYCLE_START_CLIENT_OVERRIDE=NO
ISO_WEEK_AUTHORITY=NO
PARALLEL_WEEKLY_SOT=NO
NUTRITION_EXERCISE_COEXIST=YES
NO_CROSS_DOMAIN_SUPERSEDE=PASS
AUTO_NEXT_CYCLE=NO
MY_SCHEDULE_UNCHANGED=YES
```

## Next FE Gate requirements (record only — no FE mutation)

```
- Official Sedi AppTheme / A3 Lifestyle visual match
- SediLocaleController locale authority
- en / fa / ar; fa/ar RTL; en LTR
- No hard-coded English weekday labels
- Localized dates/day names, empty states, Review with Sedi CTA
- Display backend-governed local times only
- Presentation-only; no FE plan generation/inference
```

## Continuity

```
MASTER_LOG_TIP=§497
CURSOR_HANDOFF_TIP=v790
CHATGPT_DROPBOX_UPDATED_BY_CURSOR=NO
```
