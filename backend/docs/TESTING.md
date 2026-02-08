# Backend testing

## How to run Release D acceptance on server

Use the dedicated script so tests run against the test database (`sedi_test_db`) and never touch production (`sedi_db`).

From the backend root (e.g. on the server):

```bash
cd /var/www/sedi/backend
./scripts/run_release_d_acceptance.sh
```

The script will:

- Activate `.venv` if present and not already active
- Ensure the Postgres test DB `sedi_test_db` exists (and create it if missing)
- Override `DATABASE_URL` to point at `sedi_test_db` only for the test run
- Refuse to run if `DATABASE_URL` is already set to production (`sedi_db`)
