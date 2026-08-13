# Section44 100-year storage capacity model

```text
STORAGE_MODEL_100Y=PASS
UNLIMITED_RAW_CONVERSATION=FORBIDDEN
OPTIONAL_EMBEDDINGS=NOT_ACTIVE_ZERO
INFRASTRUCTURE_PURCHASE=NO
CALCULATION_METHOD=explicit_assumption_table_times_row_overhead_times_fleet_multipliers
CALCULATOR=backend/app/services/i7/storage_capacity_model.py
```

Display figures are BASE unless noted. LOW/HIGH live in the calculator. Not measured
production telemetry. Device high-frequency vitals and I5 scientific corpus are
out of scope for user-memory sizing.

## Assumptions (BASE)

- UMF: 80 active facts + 40 new versions/year after year 1; 1200 B payload + 24 B heap
- lifestyle events: 156/year × 600 B
- user_events: 24/year × 800 B
- interaction_events: HOT window 180 d × 2/day (does not grow for 100y)
- daily UPS retained 1 year; weekly/monthly/yearly retained for horizon; rebuild factor 1.20
- profile: 2 versions/year × 4000 B (derived; not yet a table)
- consent/audit: 20 KB/year
- raw chat: 30 days × 12 msgs × 700 B (capped; not lifelong)
- embeddings: 0 (NOT ACTIVE)
- indexes 0.55× heap; 1 standby replica; backup 2.5× live

## Per-user BASE (from calculator)

| Horizon | Lifelong no chat | Capped chat | Primary heap | /year | /day |
|---|---:|---:|---:|---:|---:|
| 1y | ~0.78 MB | ~0.25 MB | ~1.03 MB | ~1.03 MB | ~2.9 KB |
| 5y | ~1.77 MB | ~0.25 MB | ~2.02 MB | ~0.40 MB | ~1.1 KB |
| 10y | ~3.00 MB | ~0.25 MB | ~3.25 MB | ~0.33 MB | ~0.91 KB |
| 50y | ~12.9 MB | ~0.25 MB | ~13.1 MB | ~0.26 MB | ~0.73 KB |
| 100y | ~25.2 MB | ~0.25 MB | ~25.4 MB | ~0.25 MB | ~0.71 KB |

Chat stays flat after the HOT window. Lifelong growth is facts + events + weekly/monthly/yearly UPS.

## Fleet BASE primary heap

| Users | 1y | 5y | 10y | 50y | 100y |
|---|---:|---:|---:|---:|---:|
| 100 | ~103 MB | ~202 MB | ~325 MB | ~1.31 GB | ~2.54 GB |
| 1,000 | ~1.03 GB | ~2.02 GB | ~3.25 GB | ~13.1 GB | ~25.4 GB |
| 5,000 | ~5.17 GB | ~10.1 GB | ~16.3 GB | ~65.6 GB | ~127 GB |
| 100,000 | ~103 GB | ~202 GB | ~325 GB | ~1.31 TB | ~2.54 TB |
| 1,000,000 | ~1.03 TB | ~2.02 TB | ~3.25 TB | ~13.1 TB | ~25.4 TB |

BASE 1M users / 100y backup envelope (heap + 0.55 index, ×2 replica, ×2.5 backup) ≈ 0.19 PB order.

LOW 1M/100y heap is smaller; HIGH is larger (see calculator). Exact assertions live in
`test_i7_section44_storage_model.py`.

## Unlimited chat contrast (FORBIDDEN)

20 msgs/day × 1000 B × 100 years × 1,000,000 users ≈ 0.73 PB of chat alone —
~30× the BASE lifelong+capped-chat heap. This is why raw chat is not LTM.

## Residual risk

Row sizes will drift with JSON growth. Re-run the calculator before any infra buy.
No purchase/deployment is authorized by this Gate.
