"""PubMed official connector via NCBI E-utilities (esearch/esummary/efetch/elink).

Official policy (re-checked at Gate execution):
- tool + email identification parameters required for programmatic use
- <= 3 req/s without api_key; <= 10 req/s with api_key
- Credentials/config from environment only — never hard-code personal details
"""

from __future__ import annotations

import hashlib
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Optional, Sequence
from xml.etree.ElementTree import ParseError

from backend.app.services.i5.know04.change_intelligence import classify_pubmed_publication_types
from backend.app.services.i5.know04.contract import ConnectorCapabilities, ConnectorRecord
from backend.app.services.i5.know04.http_client import ConnectorHttpError, HardenedHttpClient
from backend.app.services.i5.know04.rate_limit import TokenBucketRateLimiter
from backend.app.services.i5.know04.rights_gate import assert_no_phi_in_request, evaluate_connector_rights
from backend.app.services.i5.know04.xml_safety import safe_parse_xml
from backend.app.services.i5.enums import ProcessingPermissionMode, RightDecision

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ALLOWED_DOMAINS = ("eutils.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov")


@dataclass
class PubMedConnectorConfig:
    tool: str
    email: str
    api_key: Optional[str] = None

    @classmethod
    def from_env(cls, *, allow_disallowed_email: bool = False) -> "PubMedConnectorConfig":
        tool = os.environ.get("SEDI_NCBI_TOOL", "").strip()
        email = os.environ.get("SEDI_NCBI_EMAIL", "").strip()
        api_key = os.environ.get("SEDI_NCBI_API_KEY", "").strip() or None
        if not tool or not email:
            raise EnvironmentError("NOT_EXECUTED_MISSING_CREDENTIALS:SEDI_NCBI_TOOL/SEDI_NCBI_EMAIL")
        if " " in tool:
            raise ValueError("NCBI_TOOL_MUST_HAVE_NO_SPACES")
        if not allow_disallowed_email:
            from backend.app.services.i5.know05.ncbi_identity import is_disallowed_operational_email

            if is_disallowed_operational_email(email):
                raise EnvironmentError("BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY")
        return cls(tool=tool, email=email, api_key=api_key)

    @property
    def max_per_second(self) -> float:
        return 10.0 if self.api_key else 3.0


@dataclass
class PubMedConnector:
    connector_key: str = "pubmed_ncbi_eutils"
    config: Optional[PubMedConnectorConfig] = None
    http_get: Optional[Callable[..., Any]] = None
    sleep_fn: Callable[[float], None] = field(default_factory=lambda: __import__("time").sleep)
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            discover=True,
            fetch_metadata=True,
            fetch_record=True,
            fetch_changes=True,
            fetch_related=True,
        )
    )

    def _client(self) -> HardenedHttpClient:
        cfg = self.config or PubMedConnectorConfig.from_env()
        limiter = TokenBucketRateLimiter(max_per_second=cfg.max_per_second, sleep_fn=self.sleep_fn)
        return HardenedHttpClient(
            allowed_domains=ALLOWED_DOMAINS,
            rate_limiter=limiter,
            http_get=self.http_get,
            sleep_fn=self.sleep_fn,
        )

    def _identity_params(self) -> dict[str, str]:
        cfg = self.config or PubMedConnectorConfig.from_env()
        params = {"tool": cfg.tool, "email": cfg.email}
        if cfg.api_key:
            params["api_key"] = cfg.api_key
        assert_no_phi_in_request(params)
        return params

    def classify_rights(self, record: Optional[ConnectorRecord] = None) -> Mapping[str, Any]:
        # PubMed metadata/abstracts: derived/metadata processing may be permitted when rights dims allow.
        # Full-text raw retention never inferred from PubMed presence alone.
        decision = evaluate_connector_rights(
            processing_mode=ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
            access_right=RightDecision.ALLOWED.value,
            automation_right=RightDecision.ALLOWED.value,
            tdm_right=RightDecision.ALLOWED.value,
            transform_right=RightDecision.ALLOWED.value,
            retain_raw_right=RightDecision.DENIED.value,
            retain_derived_right=RightDecision.ALLOWED.value,
            redistribute_right=RightDecision.DENIED.value,
            robots_state="ALLOWED",
            full_text_explicitly_allowed=False,
        )
        return decision.__dict__

    def discover(self, query: str, *, retmax: int = 20, retstart: int = 0) -> Mapping[str, Any]:
        if retmax > 100:
            raise ValueError("BOUNDED_DISCOVERY_RETMAX")
        client = self._client()
        params = {
            **self._identity_params(),
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": str(retmax),
            "retstart": str(retstart),
        }
        resp = client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params, expect_content_types={"application/json", "text/plain", "text/html"})
        data = resp.json()
        result = data.get("esearchresult") or data.get("esearchResult") or {}
        ids = result.get("idlist") or result.get("idList") or []
        return {
            "count": int(result.get("count") or len(ids)),
            "retstart": retstart,
            "retmax": retmax,
            "ids": list(ids),
            "querytranslation": result.get("querytranslation") or result.get("queryTranslation"),
        }

    def fetch_metadata(self, pmids: Sequence[str]) -> list[dict[str, Any]]:
        if not pmids:
            return []
        if len(pmids) > 50:
            raise ValueError("BOUNDED_METADATA_BATCH")
        client = self._client()
        params = {
            **self._identity_params(),
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        }
        resp = client.get(f"{EUTILS_BASE}/esummary.fcgi", params=params, expect_content_types={"application/json", "text/plain", "text/html"})
        data = resp.json()
        result = data.get("result") or {}
        out = []
        for pmid in pmids:
            row = result.get(str(pmid))
            if row:
                out.append(row)
        return out

    def fetch_record(self, pmid: str) -> ConnectorRecord:
        client = self._client()
        params = {
            **self._identity_params(),
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml",
            "rettype": "abstract",
        }
        resp = client.get(
            f"{EUTILS_BASE}/efetch.fcgi",
            params=params,
            expect_content_types={"application/xml", "text/xml", "text/plain", "application/xhtml+xml"},
        )
        raw = self.parse_pubmed_xml(resp.content)
        return self.normalize(raw)

    def fetch_related(self, pmid: str) -> list[str]:
        client = self._client()
        params = {
            **self._identity_params(),
            "dbfrom": "pubmed",
            "db": "pubmed",
            "id": pmid,
            "retmode": "json",
            "cmd": "neighbor",
        }
        resp = client.get(f"{EUTILS_BASE}/elink.fcgi", params=params, expect_content_types={"application/json", "text/plain", "text/html"})
        data = resp.json()
        ids: list[str] = []
        for linkset in data.get("linksets") or data.get("linkSets") or []:
            for lsdb in linkset.get("linksetdbs") or linkset.get("linkSetDbs") or []:
                for link in lsdb.get("links") or []:
                    ids.append(str(link))
        return ids

    def fetch_changes(self, raw_xml_or_types: Any) -> list[str]:
        if isinstance(raw_xml_or_types, (bytes, str)):
            parsed = self.parse_pubmed_xml(raw_xml_or_types if isinstance(raw_xml_or_types, bytes) else raw_xml_or_types.encode())
            return classify_pubmed_publication_types(parsed.get("publication_types") or [])
        if isinstance(raw_xml_or_types, Mapping):
            return classify_pubmed_publication_types(raw_xml_or_types.get("publication_types") or [])
        return classify_pubmed_publication_types(list(raw_xml_or_types or []))

    def parse_pubmed_xml(self, content: bytes) -> dict[str, Any]:
        root = safe_parse_xml(content)
        article = root.find(".//PubmedArticle")
        if article is None:
            article = root.find(".//PubmedBookArticle")
        if article is None:
            article = root
        medline = article.find(".//MedlineCitation") if article is not None else None
        pmid_el = medline.find("PMID") if medline is not None else None
        if pmid_el is None:
            pmid_el = root.find(".//PMID")
        pmid = (pmid_el.text or "").strip() if pmid_el is not None else ""
        title_el = root.find(".//ArticleTitle")
        abstract_texts = [t.text or "" for t in root.findall(".//AbstractText")]
        pub_types = [pt.text or "" for pt in root.findall(".//PublicationType") if pt.text]
        mesh = []
        for mh in root.findall(".//MeshHeading"):
            desc = mh.find("DescriptorName")
            if desc is not None and desc.text:
                mesh.append(desc.text)
        dates = {}
        for d in root.findall(".//PubDate"):
            y = d.findtext("Year")
            m = d.findtext("Month")
            day = d.findtext("Day")
            dates["pub_date"] = "-".join(x for x in (y, m, day) if x)
        # Comments/Corrections relations
        relations = []
        for cc in root.findall(".//CommentsCorrections"):
            relations.append(
                {
                    "ref_type": cc.get("RefType") or "",
                    "pmid": (cc.findtext("PMID") or "").strip(),
                    "ref_source": cc.findtext("RefSource") or "",
                }
            )
        return {
            "pmid": pmid,
            "title": (title_el.text or "") if title_el is not None else "",
            "abstract": "\n".join(a for a in abstract_texts if a),
            "publication_types": pub_types,
            "mesh_terms": mesh,
            "dates": dates,
            "relations": relations,
            "change_kinds": classify_pubmed_publication_types(pub_types),
        }

    def normalize(self, raw: Mapping[str, Any]) -> ConnectorRecord:
        pmid = str(raw.get("pmid") or "")
        blob = repr(sorted(raw.items())).encode("utf-8")
        rights = self.classify_rights()
        return ConnectorRecord(
            source_identity="pubmed",
            source_role="SCIENTIFIC_LITERATURE",
            official_authority="NCBI PubMed / NLM",
            resource_type="ARTICLE_METADATA",
            external_identifier=f"PMID:{pmid}",
            canonical_locator=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            version_revision=str((raw.get("dates") or {}).get("pub_date") or ""),
            retrieved_at=datetime.utcnow(),
            content_hash=hashlib.sha256(blob).hexdigest(),
            license_observation="PUBMED_METADATA_ABSTRACT",
            processing_decision=rights.get("processing_decision", "BLOCK"),
            storage_decision=rights.get("storage_decision", "NO_STORE"),
            change_state=(raw.get("change_kinds") or [None])[0],
            retraction_state="RETRACTED" if "RETRACTED" in (raw.get("change_kinds") or []) else None,
            provenance={"connector": self.connector_key, "relations": raw.get("relations") or []},
            payload=dict(raw),
            synthetic_fixture=bool(raw.get("synthetic_fixture")),
        )
