"""
Alembic env: prefers TEST_DATABASE_URL (for pytest) then DATABASE_URL.
Run from repo root or backend with DATABASE_URL set (or in .env).
"""
import os
import sys
from pathlib import Path
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import create_engine

# Ensure backend.app is importable when running from backend/
_backend_dir = Path(__file__).resolve().parent.parent
_repo_root = _backend_dir.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

load_dotenv(_backend_dir / ".env")
load_dotenv(_repo_root / ".env")

# Prefer test DB when running pytest / CI
database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Set it (or add to .env) before running Alembic."
    )

from alembic import context
from backend.app.database import Base

# Import works when run by Alembic CLI (no package context); prefer package import, fallback to same-dir
try:
    from alembic.env_utils import _disable_interpolation
except ImportError:
    _alembic_dir = Path(__file__).resolve().parent
    if str(_alembic_dir) not in sys.path:
        sys.path.insert(0, str(_alembic_dir))
    import env_utils as _env_utils_mod
    _disable_interpolation = _env_utils_mod._disable_interpolation

config = context.config
_disable_interpolation(config)

# Allow % in URL (URL-encoded passwords): escape % for configparser
database_url_for_config = database_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", database_url_for_config)

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL only)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using engine built from selected URL."""
    url = config.get_main_option("sqlalchemy.url")
    engine = create_engine(url, future=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
