# Legacy Deploy Sedi Backend (DISABLED)

This document archives the removed workflow `.github/workflows/deploy-backend.yml`.

## Why it was removed

The legacy workflow was a **disabled stub** that remained in `.github/workflows/` only as a safety notice. It created clutter in the GitHub Actions UI and could confuse operators looking for the real deploy path.

## What the old workflow targeted

- **Old server:** `91.107.168.130`
- **Method:** systemd / direct git pull style deployment (pre–Cloud.ir Docker architecture)
- **Not compatible** with the current production stack on Cloud.ir (Docker Compose, GHCR images, controlled recreate of `sedi-backend` only)

## Correct replacement

Use these root workflows instead:

| Purpose | Workflow file | Display name |
|---------|---------------|--------------|
| Production deploy | `.github/workflows/deploy-backend-ghcr.yml` | Deploy Sedi Backend from GHCR |
| SSH connectivity check | `.github/workflows/test-server-ssh.yml` | Test Server SSH |
| Backend image build | `.github/workflows/build-backend-image.yml` | Build Sedi Backend Image |

## Deploy policy (V1)

- Deploy is **manual only** (`workflow_dispatch`).
- Use a **commit SHA** GHCR image tag (not `latest`).
- Deploy pulls from GHCR, runs a **pre-deploy Postgres backup**, recreates **only** `sedi-backend`, runs health checks, and rolls back on failure.

## Nested copy

A duplicate stub also existed at `backend/.github/workflows/deploy-backend.yml`. GitHub Actions does **not** execute nested workflow files; only repository root `.github/workflows/` is active. That nested file was removed for the same reason.
