"""
Alembic env helpers (testable without DB).
Support for % in DATABASE_URL (URL-encoded passwords) is handled in env.py by escaping
% to %% before set_main_option; do not set file_config._interpolation to None (that
breaks config.set_main_option which calls _interpolation.before_set).
"""


def _disable_interpolation(cfg):
    """No-op: do not set file_config._interpolation to None (would break set_main_option).
    Env.py escapes % to %% before set_main_option so DATABASE_URL can contain % safely."""
    pass
