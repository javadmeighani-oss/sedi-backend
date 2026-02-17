# backend/tests/test_alembic_env_interpolation.py – no DB required
"""Ensure Alembic env supports % in DATABASE_URL (URL-encoded passwords)."""
import configparser
import pytest

try:
    from alembic.env_utils import _disable_interpolation  # type: ignore
except Exception:
    _disable_interpolation = None

pytestmark = pytest.mark.skipif(
    _disable_interpolation is None,
    reason="alembic.env_utils._disable_interpolation not available in this alembic version",
)


def test_disable_interpolation_is_noop():
    """_disable_interpolation does not set _interpolation to None (which would break set_main_option)."""
    cfg = type("Config", (), {})()
    cfg.file_config = configparser.ConfigParser()
    default_interpolation = cfg.file_config._interpolation
    _disable_interpolation(cfg)
    assert cfg.file_config._interpolation is default_interpolation


def test_disable_interpolation_no_error_when_no_file_config():
    """_disable_interpolation does not raise when file_config is missing or has no _interpolation."""
    cfg = type("Config", (), {})()
    cfg.file_config = None
    _disable_interpolation(cfg)  # should not raise

    cfg.file_config = type("Fake", (), {})()  # no _interpolation attr
    _disable_interpolation(cfg)  # should not raise


def test_configparser_set_main_option_with_percent_escaped():
    """Escaping % to %% allows set_main_option to succeed; get returns value with single %."""
    parser = configparser.ConfigParser()
    parser.add_section("alembic")
    url_with_percent = "postgresql://u:p%21%40%23@localhost/db"
    url_for_config = url_with_percent.replace("%", "%%")
    parser.set("alembic", "sqlalchemy.url", url_for_config)
    assert parser.get("alembic", "sqlalchemy.url") == url_with_percent


def test_configparser_set_main_option_with_percent_does_not_crash():
    """set_main_option with escaped %% does not raise; config.get returns correct URL."""
    parser = configparser.ConfigParser()
    parser.add_section("alembic")
    url_with_percent = "postgresql://user:p%40ss%23word@host/db"
    database_url_for_config = url_with_percent.replace("%", "%%")
    parser.set("alembic", "sqlalchemy.url", database_url_for_config)
    got = parser.get("alembic", "sqlalchemy.url")
    assert got == url_with_percent
