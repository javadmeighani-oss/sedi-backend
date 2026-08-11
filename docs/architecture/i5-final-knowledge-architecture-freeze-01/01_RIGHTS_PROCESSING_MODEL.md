# 01 — Rights / Processing Model (FROZEN)

```text
DESIGN_ONLY = YES
NO_STORAGE_RIGHT == AUTOMATED_PROCESSING_ALLOWED = FALSE (HARD)
UNKNOWN_RIGHTS = FAIL_CLOSED
```

## Processing permission modes (logical)

| Mode | Meaning |
|---|---|
| `FULL_PROCESS_AND_RETAIN` | Automate + retain raw under governance |
| `TRANSIENT_PROCESS_ONLY` | Automate; destroy raw after derived persist |
| `DERIVED_KNOWLEDGE_ONLY` | May persist extracted KU/facts; no durable raw |
| `METADATA_ABSTRACT_ONLY` | Title/abstract/metadata only |
| `FULLTEXT_AUTOMATION_BLOCKED` | Human/manual or licensed path only |
| `LICENSED_CONNECTOR_ONLY` | Requires paid/licensed connector Gate |

## Map → existing `RawRetentionMode`

| Processing mode | Primary RawRetentionMode | Notes |
|---|---|---|
| FULL_PROCESS_AND_RETAIN | `RAW_FULL_GOVERNED_RETENTION` | Rare; explicit rights review |
| TRANSIENT_PROCESS_ONLY | `RAW_TRANSIENT_PROCESSING` | Ephemeral bytes lifecycle |
| DERIVED_KNOWLEDGE_ONLY | `RAW_MINIMAL_EVIDENCE_ONLY` or transient + derived | Prefer minimal durable raw |
| METADATA_ABSTRACT_ONLY | `RAW_LINK_AND_CITATION_ONLY` (+ abstract if allowed) | |
| FULLTEXT_AUTOMATION_BLOCKED | `RAW_EXCLUDED_PROTECTED_ELEMENTS` | Registry may still list source |
| LICENSED_CONNECTOR_ONLY | TBD per license Gate | No default automation |

## Distinct rights dimensions (all required on source profile)

```text
access_right
automation_right
tdm_right
transform_right
retain_raw_right
retain_derived_right
redistribution_right
attribution_requirement
robots_access_state
rate_limit_policy
```

Unknown on any automation-critical dimension → **fail closed** (no fetch/automation).

## Transient lifecycle (FROZEN)

```text
authorized fetch
→ ephemeral bytes (memory/temp; no durable path unless allowed)
→ security/MIME validation
→ parser
→ structured extraction
→ provenance/hash/citation
→ persist ONLY authorized derived data (KU/evidence links/metadata)
→ destroy transient raw bytes
→ verify no durable raw residue (audit hook)
```

## Legal stance

```text
FACT: free-to-read / public URL / accessible PDF ≠ processing permission
DECISION: rights review is a first-class Gate before connector activation
ASSUMPTION: none invented as blanket TDM permission
```
