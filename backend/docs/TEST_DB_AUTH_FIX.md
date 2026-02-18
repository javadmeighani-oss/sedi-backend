# Test Database Auth Fix: Peer Auth Failure on Unix Socket

## Why Peer Auth Fails

When tests use a PostgreSQL URL like `postgresql://postgres@/sedi_test?host=/var/run/postgresql`, the connection goes over a **Unix socket** (`/var/run/postgresql`). PostgreSQL then uses **peer authentication**: it maps the OS user running the client to a database user. If your OS user is not `postgres`, authentication fails with:

```
FATAL: Peer authentication failed for user "postgres"
```

Tests must connect via **TCP** (127.0.0.1:5432) with a dedicated test user and password so that PostgreSQL uses **md5** (or scram-sha-256) auth instead of peer.

## Single Source of Truth: `TEST_DATABASE_URL`

The test database URL is determined by:

1. **`TEST_DATABASE_URL`** (env var) – if set, use it.
2. **Fallback** – if not set:  
   `postgresql+psycopg2://sedi_test_user:StrongTestPass123@127.0.0.1:5432/sedi_test`

`DATABASE_URL` is **never** used when running tests. Tests use `backend/tests/test_db_config.get_test_database_url()`.

## Required Server-Side Steps

On the PostgreSQL host, create the test user and database, and enable TCP password auth:

### 1. Create test user and database

```bash
sudo -u postgres psql -c "
  CREATE USER sedi_test_user WITH PASSWORD 'StrongTestPass123';
  CREATE DATABASE sedi_test OWNER sedi_test_user;
  GRANT ALL PRIVILEGES ON DATABASE sedi_test TO sedi_test_user;
"
```

### 2. Allow TCP connections with password auth

Add to `pg_hba.conf` (before any `local` peer lines if needed):

```
# TCP connections from localhost for sedi_test_user (md5 auth)
host    sedi_test    sedi_test_user    127.0.0.1/32    md5
```

Reload or restart PostgreSQL:

```bash
sudo systemctl reload postgresql
# or
sudo systemctl restart postgresql
```

### 3. Ensure `listen_addresses` includes localhost

In `postgresql.conf`:

```
listen_addresses = 'localhost'
```

## How to Run Tests

Use `TEST_DATABASE_URL` (optional) and run pytest:

```bash
# Use fallback (sedi_test_user@127.0.0.1:5432/sedi_test)
pytest -q

# Or override with a custom test URL
TEST_DATABASE_URL="postgresql+psycopg2://user:pass@127.0.0.1:5432/sedi_test" pytest -q
```

Avoid Unix-socket URLs such as `host=/var/run/postgresql` in `TEST_DATABASE_URL`; use TCP (127.0.0.1 or localhost) instead.
