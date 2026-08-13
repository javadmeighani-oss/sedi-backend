#!/usr/bin/env bash
# READ-ONLY NF16 / activation / identity probe. Never print NCBI email or API key.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
summary() { echo "NF16_PROBE|$1|$2"; }

ENV_FILE="/etc/sedi/sedi-backend.env"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/sedi/backend}"

log "=== NF16 READ-ONLY PROBE (no secret values) ==="
summary "production_write" "NO"
summary "production_activation_executed" "NO"

python3 - <<'PY'
import os, re, hashlib
from pathlib import Path

ENV = Path("/etc/sedi/sedi-backend.env")
pfx = "NF16_PROBE"

def out(k, v):
    print(f"{pfx}|{k}|{v}", flush=True)

DISALLOWED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
DISALLOWED_LOCAL = {"test", "example", "noreply", "no-reply"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def disallowed(email: str) -> bool:
    e = (email or "").strip().lower()
    if not e or not EMAIL_RE.match(e):
        return True
    local, _, domain = e.partition("@")
    if any(domain.endswith(s) or domain == s.lstrip(".") for s in DISALLOWED_SUFFIXES):
        return True
    if domain in {"example.com", "example.org", "example.net", "sedi.test"}:
        return True
    if local in DISALLOWED_LOCAL:
        return True
    return False

kv = {}
if ENV.is_file():
    out("env_file_present", "YES")
    for line in ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        kv[k.strip()] = v.strip()
else:
    out("env_file_present", "NO")

tool = kv.get("SEDI_NCBI_TOOL", "")
email = kv.get("SEDI_NCBI_EMAIL", "")
api = kv.get("SEDI_NCBI_API_KEY", "")
out("ncbi_tool_present", "YES" if tool else "NO")
out("ncbi_tool_valid", "YES" if tool and " " not in tool else "NO")
out("ncbi_tool_value", tool if tool and " " not in tool else "EMPTY_OR_INVALID")
out("ncbi_email_present", "YES" if email else "NO")
if email:
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    out("ncbi_email_domain", domain)
    out("ncbi_email_valid", "NO" if disallowed(email) else "YES")
    out("ncbi_email_redacted_in_evidence", "YES")
else:
    out("ncbi_email_domain", "")
    out("ncbi_email_valid", "NO")
    out("ncbi_email_redacted_in_evidence", "YES")
out("ncbi_api_key_present", "YES" if api else "NO")

# Other email-like keys: report names + domain only, never values
other = []
for k, v in kv.items():
    if k in {"SEDI_NCBI_EMAIL", "SEDI_NCBI_API_KEY"}:
        continue
    if "EMAIL" in k.upper() or k.upper().endswith("_FROM") or "SMTP" in k.upper():
        if "@" in v and "." in v:
            domain = v.rsplit("@", 1)[-1]
            local = v.rsplit("@", 1)[0].lower()
            other.append(f"{k}:domain={domain}:disallowed={'YES' if disallowed(v) else 'NO'}")
        else:
            other.append(f"{k}:non_email_or_empty")
out("other_email_like_keys", ";".join(other) if other else "NONE")

status = "LIVE_READY" if (tool and " " not in tool and email and not disallowed(email)) else "BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY"
out("ncbi_operational_identity_status", status)
out("nf16_operational_live_ready", "YES" if status == "LIVE_READY" else "NO")

# Activation flags (values are not secrets)
for flag in (
    "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED",
    "SEDI_I5_SOURCE_ACTIVATION_ENABLED",
    "SEDI_I5_MULTISOURCE_ENABLED",
    "SEDI_DISABLE_SCHEDULER",
):
    out(f"flag_{flag}", kv.get(flag, "UNSET"))
PY

# Compose / health / alembic / image (read-only)
if docker container inspect sedi-postgres >/dev/null 2>&1; then
  PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
  PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
  ALEMBIC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT version_num FROM alembic_version;" | tr -d '\r')"
  PGV="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';" | tr -d '\r')"
  KCE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM knowledge_chunk_embeddings;" | tr -d '\r')"
  USERS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM users;" | tr -d '\r')"
  SESS="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database();" | tr -d '\r')"
  summary "production_alembic" "${ALEMBIC}"
  summary "production_pgvector_version" "${PGV:-none}"
  summary "kce_count" "${KCE:-0}"
  summary "users_count" "${USERS:-0}"
  summary "db_sessions" "${SESS:-0}"
else
  summary "production_alembic" "UNAVAILABLE"
fi

IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || echo none)"
IMG_ID="$(docker inspect sedi-backend --format '{{.Image}}' 2>/dev/null || echo none)"
DIGEST="$(docker image inspect "${IMG_ID}" --format '{{range .RepoDigests}}{{println .}}{{end}}' 2>/dev/null | head -n 1 || true)"
summary "backend_image" "${IMG}"
summary "backend_digest" "${DIGEST:-none}"

PGIMG="$(docker inspect sedi-postgres --format '{{.Config.Image}}' 2>/dev/null || echo none)"
summary "postgres_image" "${PGIMG}"

if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
  summary "backend_health_local" "PASS"
else
  summary "backend_health_local" "FAIL"
fi
if curl -fsS https://api.sedi-ai.com/healthz >/dev/null 2>&1; then
  summary "backend_health_public" "PASS"
else
  summary "backend_health_public" "FAIL"
fi

for svc in sedi-crawler sedi-scheduler sedi-rag; do
  st="$(docker container inspect "${svc}" --format '{{.State.Running}}' 2>/dev/null || echo absent)"
  st="$(printf '%s' "${st}" | tr -d '\r\n')"
  summary "service_${svc}" "${st:-absent}"
done
summary "production_crawler" "NO"
summary "production_scheduler" "NO"
summary "production_rag" "NO"
summary "production_connector_activation" "NO"
summary "production_knowledge_ingestion" "NO"
summary "production_activation_at_start" "NO"
log "=== NF16 PROBE DONE ==="
