"""
Alembic env: uses DATABASE_URL from environment and backend.app.database Base/engine.
Run from repo root or backend with DATABASE_URL set (or in .env).
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure backend.app is importable when running from backend/
_backend_dir = Path(__file__).resolve().parent.parent
_repo_root = _backend_dir.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

load_dotenv(_backend_dir / ".env")
load_dotenv(_repo_root / ".env")

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Set it (or add to .env) before running Alembic."
    )

from logging.config import fileConfig
from alembic import context
from backend.app.database import Base, engine

# Import works when run by Alembic CLI (no package context); prefer package import, fallback to same-dir
try:
    from alembic.env_utils import _disable_interpolation
except ImportError:
    _alembic_dir = Path(__file__).resolve().parent
    if str(_alembic_dir) not in sys.path:
        sys.path.insert(0, str(_alembic_dir))
    import env_utils as _env_utils_mod
    _disable_interpolation = _env_utils_mod._disable_interpolation

# Alembic Config object
config = context.config
# Allow % in DATABASE_URL (URL-encoded passwords); configparser would otherwise interpolate % and raise
_disable_interpolation(config)
config.set_main_option("sqlalchemy.url", database_url)

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
    """Run migrations in 'online' mode using engine from backend.app.database."""
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
