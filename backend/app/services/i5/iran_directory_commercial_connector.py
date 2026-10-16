"""Contract-gated connector interface for commercial directory platforms.

Infrastructure only: no network, no data pull. A connector can return records only
when it is explicitly enabled AND a contract reference is configured (D-010/D-012).
Records carry TRUST_TIER=COMMERCIAL_UNVERIFIED and country, and still pass the
existing normalization/import path (facts only, source attribution).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

TRUST_TIER_COMMERCIAL = "COMMERCIAL_UNVERIFIED"


class ConnectorNotEnabledError(RuntimeError):
    """Raised when a commercial connector is used without contract + enable flag."""


class DirectoryConnector(Protocol):
    source_key: str

    def fetch(self, entity_family: str, country: str) -> Iterable[dict[str, Any]]: ...


@dataclass(frozen=True)
class ConnectorConfig:
    source_key: str
    enabled: bool = False
    contract_ref: str | None = None

    def assert_usable(self) -> None:
        if not self.enabled or not (self.contract_ref or "").strip():
            raise ConnectorNotEnabledError(f"CONNECTOR_NOT_ENABLED:{self.source_key}")


def fetch_commercial(
    connector: DirectoryConnector, config: ConnectorConfig, entity_family: str, country: str = "IR"
) -> list[dict[str, Any]]:
    config.assert_usable()
    out = []
    for rec in connector.fetch(entity_family, country):
        out.append({**rec, "country": country, "trust_tier": TRUST_TIER_COMMERCIAL,
                    "source_system_label": config.source_key})
    return out
