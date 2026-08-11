# I5-KNOW-05 Evidence Pack — NF23/NF24 Remediation

GATE = Canonical source rights + real governance + trial-registry non-runtime semantics

- Predecessor: §285 / v576 / ChatGPT **v588**
- Closure: §286 / v577 / ChatGPT successor required from v588
- CI: run `31493592092` — 45 + 6 passed — RAW_LOG_AUDIT=PASS — FRESH_065=PASS
- GREEN SHA: `93dc0803a1074a1150981331ec63007d564d5d75`
- NEW_MIGRATION=NO / Production activation=NO

## Modules

- `know05/canonical_rights.py` — NF24
- `know05/publication.py` — NF23 gate evidence
- `know05/bounded_ingestion.py` — no synthetic GSP; trial NOT_ELIGIBLE
- `know05/source_selection.py` — rights from DB not connector key
- `know05/eligibility_integrity.py` — hard-zero counters

## Invariants proven

- PIPELINE_STAGE ≠ POLICY_DECISION
- CONNECTOR_READY ≠ RIGHTS_ALLOWED
- TRIAL_REGISTRATION ≠ PROVEN_TREATMENT
- UNKNOWN_RIGHTS → NO_STORE
- UNKNOWN_SAFETY → NOT clinical runtime eligible
