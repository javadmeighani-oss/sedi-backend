"""Legacy onboarding deprecation + prefreeze schema-authority canaries."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.app.routers import interact as interact_mod


def test_legacy_onboarding_default_disabled(monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_ONBOARDING_ENABLED", raising=False)
    assert interact_mod._legacy_onboarding_enabled() is False


def test_legacy_onboarding_explicit_true(monkeypatch):
    monkeypatch.setenv("SEDI_LEGACY_ONBOARDING_ENABLED", "true")
    assert interact_mod._legacy_onboarding_enabled() is True


def test_onboarding_returns_410_by_default(client, monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_ONBOARDING_ENABLED", raising=False)
    r = client.post("/interact/onboarding", json={"name": "Blocked"})
    assert r.status_code == 410


def test_onboarding_returns_410_when_disabled(client):
    with patch(
        "backend.app.routers.interact._legacy_onboarding_enabled",
        return_value=False,
    ):
        r = client.post("/interact/onboarding", json={"name": "Blocked"})
    assert r.status_code == 410


def test_onboarding_works_when_legacy_enabled_without_schema_mutation(client):
    create_all = MagicMock()
    with patch(
        "backend.app.routers.interact._legacy_onboarding_enabled",
        return_value=True,
    ), patch(
        "backend.app.core.conversation.brain.ConversationBrain.get_initial_message",
        return_value="Hello!",
    ), patch(
        "backend.app.database.Base.metadata.create_all",
        create_all,
    ):
        r = client.post("/interact/onboarding", json={"name": "Legacy User"})
    assert r.status_code == 200
    create_all.assert_not_called()


def test_onboarding_source_has_no_runtime_schema_mutation():
    import inspect
    import re

    src = inspect.getsource(interact_mod.setup_onboarding)
    assert not re.search(r"metadata\.create_all\s*\(", src)
    assert not re.search(r"Base\.metadata\.create_all\s*\(", src)
    assert "ALTER TABLE" not in src
    assert "DROP CONSTRAINT" not in src
