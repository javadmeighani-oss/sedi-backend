# SEDI Cursor Authoritative Handoff - v791

A3 Lifestyle weekly Nutrition+Exercise UI — **PASS** (frontend delta; uncommitted).

Do not modify v790 / §497 history. This file supersedes v790 as CURRENT tip.

```
VERSION=v791
STATUS=CURRENT
LOGICAL_PREDECESSOR=v790
v790_MODIFIED=NO
SUCCESSOR_MODE=CREATE_ONLY
MASTER_LOG=§498
GATE=SEDI-V1-A3-LIFESTYLE-WEEKLY-NUTRITION-EXERCISE-UI-01
GATE_RESULT=PASS
WEEKLY_NUTRITION_EXERCISE_BACKEND=CLOSED
FRONTEND_WEEKLY_UI=IMPLEMENTED_LOCAL (uncommitted)
SCHEMA_OR_MIGRATION_CHANGED=NO
PROD_DEPLOY_PERFORMED=NO
BACKEND_PRODUCT_MUTATION=NO
DEPENDENCY_CHANGE=NO
WORKFLOW_MUTATION=NO
FORCE_PUSH=NO
COMMIT=NO
PUSH=NO
NEXT_GATE_AUTHORIZED=NO
```

## Heads / branch

```
REPO=sedi-frontend
BASELINE_HEAD=c9ce4f1e37699ac78d392e73c8f70474b198fb0c
BRANCH=feature/a3-authority-chat-stream-profile-foundation
WORKTREE_CLEAN_AT_START=YES
```

## Implementation summary

```
- Shared DTO + LifestyleWeeklyPlanService → GET /lifestyle/weekly-plan
- Shared LifestyleWeeklyPlanView reused by Nutrition + Exercise
- States: active / empty / review_due / unavailable
- No fabricated meals/exercises; backend day order only
- AppTheme only; LifestyleL10n en/fa/ar + RTL/LTR
- CalendarDateMath (Gregorian/Jalali/Hijri); BirthCalendarHelper delegates
- Gate3InteractivePage(initialDraft) + Gate3Composer(initialText) composer-only; no auto-send
- initialMessage notification/Sedi transcript path unchanged
```

## Tests

```
LOCAL_FLUTTER_RUNTIME=UNAVAILABLE
TARGETED_TESTS_AUTHORED=test/a3_lifestyle_weekly_plan_ui_test.dart + a3_lifestyle_hub_minimal_test update
TARGETED_TESTS_EXECUTED=STATIC_CHECKS_ONLY
LOCALE_CALENDAR_REGRESSION=STATIC (BirthCalendarHelper delegate + CalendarDateMath)
```

## Changed paths (FE worktree)

```
lib/core/locale/calendar_date_math.dart (new)
lib/data/dto/lifestyle/lifestyle_weekly_plan_dto.dart (new)
lib/services/lifestyle/lifestyle_weekly_plan_service.dart (new)
lib/features/lifestyle/presentation/widgets/lifestyle_weekly_plan_view.dart (new)
lib/features/lifestyle/presentation/pages/lifestyle_nutrition_page.dart
lib/features/lifestyle/presentation/pages/lifestyle_exercise_page.dart
lib/features/lifestyle/presentation/pages/lifestyle_page.dart
lib/features/lifestyle/presentation/lifestyle_l10n.dart
lib/features/auth_otp/presentation/birth_calendar_helper.dart
lib/features/gate3_interactive/presentation/pages/gate3_interactive_page.dart
lib/features/gate3_interactive/presentation/widgets/gate3_composer.dart
test/a3_lifestyle_weekly_plan_ui_test.dart (new)
test/a3_lifestyle_hub_minimal_test.dart
docs: Master Log §498 + this handoff (workspace governance)
```

## Open items

```
- Run Flutter targeted tests when SDK available / CI closure Gate
- FE commit+push+CI not authorized by this Gate
- Gadgets / Notifications / Profile / Health redesign still out of scope
```

## Continuity

```
MASTER_LOG_TIP=§498
CURSOR_HANDOFF_TIP=v791
CHATGPT_DROPBOX_UPDATED_BY_CURSOR=NO
```
