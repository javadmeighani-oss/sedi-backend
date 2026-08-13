# DCR-03 Durable user memory export — APPROVED MODEL

```text
DCR03_DECISION=APPROVE_MODEL
DCR03_SCHEMA_OR_STORAGE_CHANGE_REQUIRED=YES
EXPORT_ARTIFACT_IS_NOT_CANONICAL_STORE=YES
IMPLEMENTED=NO
```

Current: `export_memory_bundle` returns ephemeral JSON. Keep as the in-process
builder. Durable delivery needs a job + object store + receipt table.

## Decision

Asynchronous creation. Synchronous only if row count is below a small threshold
(implementation Gate). Format: versioned JSON (canonical) + optional UTF-8
Markdown companion generated from the same bundle.

Storage: object store (encrypted at rest) + DB metadata. DB is not the blob store.

## Later entities

`user_memory_export_jobs`

- id, user_id, status (queued|running|ready|expired|revoked|failed)
- schema_version, generator_version
- artifact_uri, artifact_sha256, bytes
- content_class (MEMORY_BUNDLE)
- created_at, expires_at, revoked_at, downloaded_at
- consent_id, actor_user_id
- error_code

Access: owner only (or legal-export grantee with consent). Signed URL TTL ≤ 1 hour.
Artifact expires ≤ 7 days BASE then delete blob + mark expired.
Revoke consent or forget → revoke job + delete blob.
Audit: interaction/export event with job id, not payload.

Large export: chunked JSON parts + manifest. Pagination by fact id.

Not a shadow SoT: imports are not auto-rehydrated; re-ingest would be a future
explicit user action Gate.

Encryption: server-side KMS + TLS. No secrets in logs. No cross-user URLs.

Rollback: drop jobs table; leave UMF intact; delete orphan blobs.
