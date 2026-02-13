# backend/tests/test_alembic_env_interpolation.py – no DB required
"""Ensure Alembic env supports % in DATABASE_URL (URL-encoded passwords)."""
import configparser
import pytest

# Test the helper used by env.py so we don't need to load DB
from alembic.env_utils import _disable_interpolation


def test_disable_interpolation_sets_none():
    """Calling _disable_interpolation(cfg) sets file_config._interpolation to None."""
    cfg = type("Config", (), {})()
    cfg.file_config = configparser.ConfigParser()
    _disable_interpolation(cfg)
    assert cfg.file_config._interpolation is None


def test_disable_interpolation_no_error_when_no_file_config():
    """_disable_interpolation does not raise when file_config is missing or has no _interpolation."""
    cfg = type("Config", (), {})()
    cfg.file_config = None
    _disable_interpolation(cfg)  # should not raise

    cfg.file_config = type("Fake", (), {})()  # no _interpolation attr
    _disable_interpolation(cfg)  # should not raise


def test_configparser_with_percent_after_disable():
    """With interpolation disabled, a value containing %21 is not interpreted (no ValueError)."""
    parser = configparser.ConfigParser()
    parser._interpolation = None  # same as what _disable_interpolation does
    parser.add_section("alembic")
    url_with_percent = "postgresql://u:p%21%40%23@localhost/db"
    parser.set("alembic", "sqlalchemy.url", url_with_percent)
    assert parser.get("alembic", "sqlalchemy.url") == url_with_percent
