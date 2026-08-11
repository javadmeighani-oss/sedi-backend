"""PMC rights-aware connector — PMC_PRESENT != FULL_TEXT_STORAGE_ALLOWED.

Uses only officially supported routes (E-utilities + OA service metadata).
No non-official bulk scraping.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from backend.app.services.i5.enums import ProcessingPermissionMode, RightDecision
from backend.app.services.i5.know04.contract import ConnectorCapabilities, ConnectorRecord
from backend.app.services.i5.know04.http_client import HardenedHttpClient
from backend.app.services.i5.know04.pubmed import PubMedConnectorConfig
from backend.app.services.i5.know04.rate_limit import TokenBucketRateLimiter
from backend.app.services.i5.know04.rights_gate import assert_no_phi_in_request, evaluate_connector_rights
from backend.app.services.i5.know04.xml_safety import safe_parse_xml

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OA_BASE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
ALLOWED = ("eutils.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov")


@dataclass
class PmcConnector:
    connector_key: str = "pubmed_central"
    config: Optional[PubMedConnectorConfig] = None
    http_get: Optional[Callable[..., Any]] = None
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            discover=True, fetch_metadata=True, fetch_record=True, fetch_changes=True
        )
    )

    def classify_rights(
        self,
        *,
        open_access: bool = False,
        license_allows_storage: bool = False,
        full_text_explicitly_allowed: bool = False,
    ) -> Mapping[str, Any]:
        # Critical: presence in PMC does not imply full-text storage.
        mode = (
            ProcessingPermissionMode.FULL_PROCESS_AND_RETAIN.value
            if full_text_explicitly_allowed and license_allows_storage
            else ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value
        )
        retain_raw = RightDecision.ALLOWED.value if full_text_explicitly_allowed and license_allows_storage else RightDecision.DENIED.value
        decision = evaluate_connector_rights(
            processing_mode=mode,
            access_right=RightDecision.ALLOWED.value,
            automation_right=RightDecision.ALLOWED.value,
            tdm_right=RightDecision.ALLOWED.value if open_access else RightDecision.REVIEW_REQUIRED.value,
            transform_right=RightDecision.ALLOWED.value,
            retain_raw_right=retain_raw,
            retain_derived_right=RightDecision.ALLOWED.value,
            redistribute_right=RightDecision.DENIED.value,
            robots_state="ALLOWED",
            full_text_explicitly_allowed=full_text_explicitly_allowed and license_allows_storage,
        )
        return decision.__dict__

    def _client(self) -> HardenedHttpClient:
        cfg = self.config
        rate = 3.0
        if cfg is not None:
            rate = cfg.max_per_second
        return HardenedHttpClient(
            allowed_domains=ALLOWED,
            rate_limiter=TokenBucketRateLimiter(max_per_second=rate),
            http_get=self.http_get,
        )

    def fetch_oa_metadata(self, pmcid: str) -> dict[str, Any]:
        """Official PMC OA web service — metadata/license indicators only at this Gate."""
        client = self._client()
        params = {"id": pmcid}
        assert_no_phi_in_request(params)
        resp = client.get(OA_BASE, params=params, expect_content_types={"text/xml", "application/xml", "text/html", "text/plain"})
        root = safe_parse_xml(resp.content)
        records = []
        for rec in root.findall(".//record"):
            records.append(
                {
                    "id": rec.get("id"),
                    "citation": rec.get("citation"),
                    "license": rec.get("license"),
                    "retracted": rec.get("retracted"),
                    "formats": [
                        {"format": link.get("format"), "href": link.get("href")}
                        for link in rec.findall("link")
                    ],
                }
            )
        return {"pmcid": pmcid, "records": records, "open_access_designation": bool(records)}

    def normalize(self, raw: Mapping[str, Any]) -> ConnectorRecord:
        pmcid = str(raw.get("pmcid") or raw.get("id") or "")
        license_obs = None
        open_access = bool(raw.get("open_access_designation"))
        for rec in raw.get("records") or []:
            license_obs = rec.get("license") or license_obs
        # Never infer full-text storage from OA presence alone without explicit rights.
        rights = self.classify_rights(
            open_access=open_access,
            license_allows_storage=False,
            full_text_explicitly_allowed=False,
        )
        if rights.get("full_text_storage_allowed"):
            raise RuntimeError("PMC_UNAUTHORIZED_FULLTEXT_STORAGE_GUARD")
        blob = repr(sorted(raw.items())).encode("utf-8")
        return ConnectorRecord(
            source_identity="pmc",
            source_role="SCIENTIFIC_LITERATURE",
            official_authority="NCBI PMC / NLM",
            resource_type="PMC_METADATA",
            external_identifier=f"PMCID:{pmcid}",
            canonical_locator=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/" if pmcid else None,
            retrieved_at=datetime.utcnow(),
            content_hash=hashlib.sha256(blob).hexdigest(),
            license_observation=license_obs,
            processing_decision=rights["processing_decision"],
            storage_decision=rights["storage_decision"],
            retraction_state="RETRACTED" if any((r.get("retracted") or "").lower() == "yes" for r in (raw.get("records") or [])) else None,
            provenance={"connector": self.connector_key, "pmc_present": True, "full_text_storage_allowed": False},
            payload=dict(raw),
            synthetic_fixture=bool(raw.get("synthetic_fixture")),
        )

    def may_persist_fulltext(self, rights: Mapping[str, Any]) -> bool:
        return bool(rights.get("full_text_storage_allowed")) and rights.get("storage_decision") == "RAW_RETAIN"
