"""
Alembic env helpers (testable without DB).
Disable configparser interpolation so DATABASE_URL can contain % (URL-encoded passwords).
"""


def _disable_interpolation(cfg):
    """Set file_config._interpolation to None so % in DATABASE_URL does not raise ValueError."""
    try:
        cfg.file_config._interpolation = None
    except Exception:
        pass
