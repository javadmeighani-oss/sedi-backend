"""Smoke test: ensure backend.app.main imports without error."""


def test_import_app():
    from backend.app.main import app
    assert app is not None
