# Smoke Test: Notification Engine Import

## Quick Import Test

Test that the notification_engine module can be imported without conflicts:

```bash
cd backend
python -c "from app.services import notification_engine; print('✅ Import successful')"
```

## Expected Output

```
✅ Import successful
```

## What This Tests

This smoke test verifies that:
1. The `app/services/notification_engine.py` module can be imported
2. There is no import ambiguity between the module and package
3. The module correctly imports from `notification_runtime` package

## Troubleshooting

If you see an import error:
- Check that `app/services/notification_runtime/` exists
- Verify `app/services/notification_engine.py` imports from `notification_runtime`
- Ensure no `app/services/notification_engine/` folder exists (it should be renamed to `notification_runtime/`)
