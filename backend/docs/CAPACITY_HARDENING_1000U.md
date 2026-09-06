# Capacity Hardening — 1000 registered / ~100 concurrent (Gate only)

GATE: SEDI-V1-BE-1000U-100CC-CAPACITY-HARDENING-01

## Targets

- REGISTERED_USERS_MAX=1000
- CONCURRENT_CONNECTED_TARGET≈100
- No production worker/pool activation in this Gate

## API / scheduler process roles

| Role | How | Scheduler |
|------|-----|-----------|
| API workers | `SEDI_DISABLE_SCHEDULER=1` or `SEDI_PROCESS_ROLE=api` | OFF |
| Scheduler | `python -m backend.ops.capacity.run_scheduler_role` (exactly one) | ON once |
| Combined (legacy) | unset (single process) | ON |

Increasing API worker count must NOT multiply schedulers: always disable scheduler on API workers.

Worker count is configurable via `UVICORN_WORKERS` / `WEB_CONCURRENCY` / `SEDI_API_WORKERS`.

- **API_MULTIWORKER_ARCHITECTURE_READY=YES**
- **PRODUCTION_MULTIWORKER_ACTIVATED=NO**
- **FINAL_WORKER_COUNT_SELECTED=NO** — choose after controlled load validation Gate.

## DB connection budget

```
TOTAL_POTENTIAL_APP_CONNECTIONS =
  API_WORKERS × (POOL_SIZE + MAX_OVERFLOW)
  + BACKGROUND_PROCESS_DB_CAPACITY
  + RESERVED_OPERATIONAL_MARGIN
```

Env (safe defaults unchanged):

- `SEDI_DB_POOL_SIZE` (default 5, max 50)
- `SEDI_DB_MAX_OVERFLOW` (default 10, max 50)
- `SEDI_DB_POOL_RECYCLE` (default 1800)
- `SEDI_DB_POOL_TIMEOUT` (default 30)

Invalid/out-of-range values fall back deterministically to defaults.

Example planning (not production activation):
`4 workers × (5+10) + 15 background + 5 margin = 80` potential app connections.

## Multi-worker state classification

| State | Class |
|-------|-------|
| SQLAlchemy pool / SessionLocal | SAFE_PER_PROCESS (budget via formula) |
| APScheduler + in-process job cursors (I8 schedule scan, optional I10 coaching cursor) | SAFE_ONLY_SINGLE_BACKGROUND_PROCESS |
| Delivery `threading.Lock` | SAFE_ONLY_SINGLE_BACKGROUND_PROCESS |
| HTTP inflight counter | SAFE_PER_PROCESS |
| I8/I10 DB idempotency / dedupe keys | cross-process safe via DB |
| Health-state request globals | SAFE_PER_PROCESS / NOT_APPLICABLE |

## Chat non-blocking

`POST /interact/chat` offloads `IntelligenceOrchestrator.process` via `asyncio.to_thread`
so OpenAI network I/O does not block the event loop. Semantics unchanged.

## Bounded scheduler scans

Morning / inactivity / engagement / health-check / medication / device-disconnected:
same-tick keyset pages (`SCHEDULER_USER_SCAN_BATCH_SIZE` default 200,
`SCHEDULER_USER_SCAN_MAX_PER_TICK` default 1000).

I10 coaching default: same-tick keyset pages; optional `use_inprocess_cursor=True`.

## Remaining capacity risks (not fixed here)

- DB session still spans orchestrator+OpenAI within the worker thread (releasing mid-request would alter transaction semantics → deferred).
- Production max_connections vs budget: NOT_PROVEN until controlled load Gate.
- RAG: no new index; governed path request-scoped; flags OFF remain near-zero work.

## Next Gate

SEDI-V1-BE-1000U-100CC-CONTROLLED-LOAD-VALIDATION-01
