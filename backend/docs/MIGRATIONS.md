# Database migrations (Alembic)

Schema is managed **only** by Alembic. The FastAPI app does not create tables at runtime.

## Prerequisites

- `DATABASE_URL` set in environment or in `.env` (e.g. `postgresql+psycopg2://user:pass@host:5432/dbname`).
- Run commands from **backend** directory (or repo root with `-c backend/alembic.ini`).

## Create a revision (autogenerate from models)

From repo root (with `backend` as cwd for Python path):

```bash
cd backend
alembic revision --autogenerate -m "describe your change"
```

Or from repo root:

```bash
cd backend && alembic revision --autogenerate -m "add notifications columns"
```

New file appears in `backend/alembic/versions/`. Review and edit if needed, then run upgrade.

## Upgrade to head (apply all pending migrations)

```bash
cd backend
alembic upgrade head
```

## On the server (production)

1. Set `DATABASE_URL` on the server (env or `.env`).
2. Pull latest code (or ensure `backend/alembic/` and `backend/alembic/versions/*.py` are deployed).
3. From the backend directory (or project root):

   ```bash
   cd /path/to/backend
   alembic upgrade head
   ```

4. Restart the application service.

Run migrations **before** or **after** deploying new code, but ensure they run before the new app version expects the new schema.

## Fresh DB (no real data)

Use this when there is **no real data** and you want to recreate the schema from scratch (e.g. new environment or reset).

1. **Stop the application service**
   ```bash
   sudo systemctl stop sedi-backend.service
   ```

2. **Export DATABASE_URL** (same value as your systemd `EnvironmentFile` or `.env`):
   ```bash
   export DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/dbname"
   ```

3. **Drop and recreate the public schema** (or recreate the database):
   - Option A – drop/recreate schema (keeps DB, wipes all tables in `public`):
     ```bash
     psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
     ```
   - Option B – recreate database (replace `sedi_db` with your DB name):
     ```bash
     psql -h host -U postgres -c "DROP DATABASE IF EXISTS sedi_db; CREATE DATABASE sedi_db;"
     ```
     Then set `DATABASE_URL` to point at the new DB and continue.

4. **Run Alembic upgrade to head**
   ```bash
   cd /path/to/project
   alembic -c backend/alembic.ini upgrade head
   ```
   Or from the backend directory:
   ```bash
   cd /path/to/project/backend
   alembic upgrade head
   ```

5. **Start the service**
   ```bash
   sudo systemctl start sedi-backend.service
   ```

6. **Verify**
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/openapi.json
   ```
   Expect `200`.

**Safety:** Take a full DB backup **before** dropping the schema or database in any environment that might contain real data. This playbook is intended for environments with no real data (e.g. dev, staging reset, or initial production setup).

**Helper script:** From repo root, with `DATABASE_URL` set and confirmation:
```bash
CONFIRM_RESET=YES ./backend/scripts/reset_db_and_migrate.sh
```
The script checks `DATABASE_URL`, requires `CONFIRM_RESET=YES`, drops/recreates schema `public`, then runs `alembic -c backend/alembic.ini upgrade head`. Make the script executable with `chmod +x backend/scripts/reset_db_and_migrate.sh` if needed.

## Other useful commands

- **Current revision:** `alembic current`
- **History:** `alembic history`
- **Downgrade one revision:** `alembic downgrade -1`
