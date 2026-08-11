# 03 — Reference Book Registry (FROZEN)

```text
REGISTRY_NAME = Sedi Reference Book Registry
SEPARATE_FROM = Global Trusted Source Registry (linked by publisher)
MEDICAL_AUTHORITY ≠ LEGAL_PROCESSING_PERMISSION
```

## Rights classes

```text
OPEN_AUTOMATION_ALLOWED
PUBLIC_DOMAIN
OPEN_LICENSE_RESTRICTED
LICENSED
METADATA_ONLY
FULLTEXT_TDM_PROHIBITED
UNKNOWN_RIGHTS  → fail-closed for automation
```

## Fields

```text
book_id, title, edition, volume, chapter_set_ref
publisher, authors_editors, ISBN, publication_year
specialty, disease_coverage[]
canonical_access_route, license, automation_tdm_rights, retention_policy
current_edition_flag, superseded_by_edition_id
```

High medical authority books may remain `FULLTEXT_TDM_PROHIBITED` while still guiding human-curated KU ingestion.
