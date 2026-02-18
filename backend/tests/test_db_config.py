"""
Single source of truth for test database URL.

Tests connect via TCP (127.0.0.1:5432) using a dedicated test user + password,
never via Unix socket (host=/var/run/postgresql) which fails with peer auth.

Precedence:
  1. env var TEST_DATABASE_URL (if set)
  2. fallback: postgresql+psycopg2://sedi_test_user:StrongTestPass123@127.0.0.1:5432/sedi_test

When running tests, DATABASE_URL is NEVER used to avoid accidentally connecting
to production or to a Unix-socket URL that triggers peer authentication.
"""

import os

# TCP fallback: 127.0.0.1 (never Unix socket host=/var/run/postgresql)
_DEFAULT_TEST_URL = (
    "postgresql+psycopg2://sedi_test_user:StrongTestPass123@127.0.0.1:5432/sedi_test"
)


def get_test_database_url() -> str:
    """
    Return the test database URL for pytest.

    Uses TEST_DATABASE_URL if set; otherwise the TCP fallback.
    Never uses DATABASE_URL when running tests.
    """
    url = os.getenv("TEST_DATABASE_URL", "").strip()
    if url:
        return url
    return _DEFAULT_TEST_URL
