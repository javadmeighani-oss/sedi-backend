# I7 week semantics — APPROVED

```text
I7_WEEK_SEMANTICS=APPROVED
I7_WEEK_SEMANTICS_DECISION=CANONICAL_UTC_BOUNDS_PLUS_USER_LOCAL_WEEK_START
I7_JOB_CHANGE_REQUIRED_LATER=YES
THIS_GATE_JOB_BEHAVIOR_UNCHANGED=YES
I5_KNOWLEDGE_WEEK_UNRELATED=YES
```

Option D: store `period_start`/`period_end` as UTC instants. Week-start is a
user-local preference, not a global religious/product lock-in.

- Default for `fa-IR` / Iran product: Saturday
- Default otherwise: Monday ISO
- User may set `week_start` (0=Monday … 6=Sunday) on profile/timezone facts
- Presentation always localizes; analytics groups by stored bounds + week_start
- DST: bounds computed in user timezone then stored UTC
- Idempotent key: (user_id, summary_type, period_start, version)
- I5 crawler week remains Friday 00:00 UTC / 03:30 Asia/Tehran and is not I7

Current code: Tehran Monday ISO in `period_bounds` + weekly job `day_of_week=mon`.
Do not change in this Gate. Later enablement/change Gate must:

1. read user week_start
2. keep job clock Asia/Tehran (or user tz) but target *closed local week*
3. rebuild historical Monday weeks as historical, not rewrite

I7_JOB_CHANGE_REQUIRED_LATER=YES only to honor user-local week after preference
exists. Production flag remains OFF until that Gate or an explicit enablement Gate.
