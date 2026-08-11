"""PMC OAI-PMH official programmatic route — metadata only, bounded."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from backend.app.services.i5.know04.http_client import HardenedHttpClient
from backend.app.services.i5.know04.rate_limit import TokenBucketRateLimiter
from backend.app.services.i5.know04.rights_gate import assert_no_phi_in_request
from backend.app.services.i5.know04.xml_safety import safe_parse_xml

PMC_OAI_BASE = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi"
PMC_ALLOWED = ("www.ncbi.nlm.nih.gov",)


@dataclass
class PmcOaiConnector:
    connector_key: str = "pmc_oai_pmh"
    http_get: Optional[Callable[..., Any]] = None

    def list_records(self, *, max_records: int = 1) -> list[dict[str, Any]]:
        if max_records > 3:
            raise ValueError("BOUNDED_PMC_OAI_MAX")
        client = HardenedHttpClient(
            allowed_domains=PMC_ALLOWED,
            rate_limiter=TokenBucketRateLimiter(max_per_second=1.0),
            http_get=self.http_get,
        )
        params = {
            "verb": "ListRecords",
            "metadataPrefix": "pmc",
        }
        assert_no_phi_in_request(params)
        resp = client.get(
            PMC_OAI_BASE,
            params=params,
            expect_content_types={"text/xml", "application/xml", "text/plain"},
        )
        return self.parse_list_records(resp.content, max_records=max_records)

    def parse_list_records(self, content: bytes, *, max_records: int = 1) -> list[dict[str, Any]]:
        root = safe_parse_xml(content)
        ns = {"oai": "http://www.openarchives.org/OAI/2.0/"}
        out: list[dict[str, Any]] = []
        for rec in root.findall(".//oai:record", ns):
            header = rec.find("oai:header", ns)
            identifier = (header.findtext("oai:identifier", default="", namespaces=ns) if header is not None else "").strip()
            if not identifier:
                continue
            pmcid = identifier.split(":")[-1] if ":" in identifier else identifier
            out.append(
                {
                    "oai_identifier": identifier,
                    "pmcid": pmcid,
                    "content_hash": hashlib.sha256(identifier.encode()).hexdigest(),
                }
            )
            if len(out) >= max_records:
                break
        return out
