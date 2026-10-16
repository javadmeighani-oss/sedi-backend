import pytest

from backend.app.services.i5.iran_directory_commercial_connector import (
    ConnectorConfig, ConnectorNotEnabledError, fetch_commercial,
)


class _Fake:
    source_key = "fake"
    called = False

    def fetch(self, entity_family, country):
        self.called = True
        return [{"name": "X", "city": "Tehran"}]


@pytest.mark.parametrize("cfg", [ConnectorConfig("fake"), ConnectorConfig("fake", True), ConnectorConfig("fake", False, "C-1")])
def test_disabled_or_no_contract_never_fetches(cfg):
    c = _Fake()
    with pytest.raises(ConnectorNotEnabledError):
        fetch_commercial(c, cfg, "LABORATORY")
    assert c.called is False


def test_enabled_with_contract_tags_records():
    recs = fetch_commercial(_Fake(), ConnectorConfig("fake", True, "C-1"), "LABORATORY", "IR")
    assert recs[0]["trust_tier"] == "COMMERCIAL_UNVERIFIED" and recs[0]["country"] == "IR"
