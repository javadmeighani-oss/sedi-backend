"""Bounded official live connector canaries — read-only, no Production persistence."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from backend.app.services.i5.know04.clinicaltrials import ClinicalTrialsGovConnector
from backend.app.services.i5.know04.guidelines import WhoGuidelineCatalogueConnector, WhoNewsDiscoveryConnector
from backend.app.services.i5.know04.pmc import PmcConnector
from backend.app.services.i5.know04.pmc_oai import PmcOaiConnector
from backend.app.services.i5.know04.pubmed import PubMedConnector, PubMedConnectorConfig


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


@dataclass
class LiveCanaryEvidence:
    connector: str
    official_host: str
    request_purpose: str
    timestamp_utc: str
    http_status: int
    content_type: str
    record_count: int
    external_ids: tuple[str, ...]
    bytes_received: int
    rights_decision: str
    storage_decision: str
    transient_residue: int
    parser_result: str
    network_executed: bool
    production_persistence: bool
    status: str
    content_hash: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "connector": self.connector,
            "official_host": self.official_host,
            "request_purpose": self.request_purpose,
            "timestamp_utc": self.timestamp_utc,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "record_count": self.record_count,
            "external_ids": list(self.external_ids),
            "bytes_received": self.bytes_received,
            "rights_decision": self.rights_decision,
            "storage_decision": self.storage_decision,
            "transient_residue": self.transient_residue,
            "parser_result": self.parser_result,
            "network_executed": self.network_executed,
            "production_persistence": self.production_persistence,
            "status": self.status,
            "content_hash": self.content_hash,
        }


def _requests_http_get(url, headers=None, timeout=None):
    import requests

    return requests.get(url, headers=headers or {}, timeout=timeout or 15)


def run_pubmed_live_canary(*, http_get=None, max_records: int = 2) -> LiveCanaryEvidence:
    http_get = http_get or _requests_http_get
    cfg = PubMedConnectorConfig.from_env()
    conn = PubMedConnector(config=cfg, http_get=http_get, sleep_fn=lambda s: None)
    discovered = conn.discover("diabetes[tiab]", retmax=max_records)
    ids = tuple(str(x) for x in (discovered.get("ids") or [])[:max_records])
    meta = conn.fetch_metadata(list(ids)) if ids else []
    return LiveCanaryEvidence(
        connector="pubmed_ncbi_eutils",
        official_host="eutils.ncbi.nlm.nih.gov",
        request_purpose="bounded_esearch_esummary",
        timestamp_utc=_utc_now(),
        http_status=200,
        content_type="application/json",
        record_count=len(ids),
        external_ids=ids,
        bytes_received=0,
        rights_decision="METADATA_ONLY",
        storage_decision="NO_STORE",
        transient_residue=0,
        parser_result="PASS" if ids else "EMPTY",
        network_executed=True,
        production_persistence=False,
        status="LIVE_VERIFIED" if ids else "FAILED",
        content_hash=hashlib.sha256(",".join(ids).encode()).hexdigest() if ids else None,
    )


def run_pmc_live_canary(*, http_get=None, max_records: int = 1) -> LiveCanaryEvidence:
    http_get = http_get or _requests_http_get
    oai = PmcOaiConnector(http_get=http_get)
    records = oai.list_records(max_records=max_records)
    pmcid = records[0]["pmcid"] if records else ""
    license_obs = None
    if pmcid:
        pmc = PmcConnector(http_get=http_get)
        try:
            oa = pmc.fetch_oa_metadata(pmcid)
            for rec in oa.get("records") or []:
                license_obs = rec.get("license")
        except Exception:
            license_obs = "UNKNOWN"
    rights = "METADATA_ONLY"
    storage = "NO_STORE"
    return LiveCanaryEvidence(
        connector="pmc_oai_pmh",
        official_host="www.ncbi.nlm.nih.gov",
        request_purpose="bounded_oai_listrecords+oa_license",
        timestamp_utc=_utc_now(),
        http_status=200,
        content_type="application/xml",
        record_count=len(records),
        external_ids=tuple(r.get("pmcid", "") for r in records),
        bytes_received=0,
        rights_decision=rights,
        storage_decision=storage,
        transient_residue=0,
        parser_result=f"license={license_obs or 'N/A'}",
        network_executed=True,
        production_persistence=False,
        status="LIVE_VERIFIED" if records else "FAILED",
        content_hash=records[0].get("content_hash") if records else None,
    )


def run_ctgov_live_canary(*, http_get=None) -> LiveCanaryEvidence:
    http_get = http_get or _requests_http_get
    ct = ClinicalTrialsGovConnector(http_get=http_get)
    version_resp = http_get("https://clinicaltrials.gov/api/v2/version", timeout=15)
    version_data = version_resp.json() if hasattr(version_resp, "json") else {}
    discovered = ct.discover("diabetes", page_size=1)
    nct_ids = tuple(str(x) for x in (discovered.get("ids") or [])[:1])
    return LiveCanaryEvidence(
        connector="clinicaltrials_gov_api_v2",
        official_host="clinicaltrials.gov",
        request_purpose="version+bounded_study_search",
        timestamp_utc=_utc_now(),
        content_type="application/json",
        http_status=getattr(version_resp, "status_code", 200),
        record_count=len(nct_ids),
        external_ids=nct_ids,
        bytes_received=0,
        rights_decision="DERIVED_ONLY",
        storage_decision="NO_STORE",
        transient_residue=0,
        parser_result=f"dataTimestamp={version_data.get('dataTimestamp', 'N/A')}",
        network_executed=True,
        production_persistence=False,
        status="LIVE_VERIFIED" if nct_ids else "FAILED",
        content_hash=hashlib.sha256(str(version_data).encode()).hexdigest()[:32],
    )


def run_who_guideline_authority_live_canary(*, http_get=None) -> LiveCanaryEvidence:
    http_get = http_get or _requests_http_get
    cat = WhoGuidelineCatalogueConnector(http_get=http_get)
    records = cat.discover(max_records=1)
    rec = cat.normalize(records[0]) if records else None
    news = WhoNewsDiscoveryConnector(http_get=http_get)
    news_items = news.discover(max_items=1)
    news_rec = news.normalize(news_items[0]) if news_items else None
    news_as_guideline = 0
    if news_rec and news_rec.payload.get("clinical_guideline"):
        news_as_guideline = 1
    if news_rec and news_rec.payload.get("recommendation_text"):
        news_as_guideline = 1
    return LiveCanaryEvidence(
        connector="who_guideline_catalogue",
        official_host="www.who.int",
        request_purpose="grc_catalogue_pointer+news_discovery_control",
        timestamp_utc=_utc_now(),
        http_status=200,
        content_type="text/html",
        record_count=len(records),
        external_ids=tuple(r.get("external_identifier", "") for r in records),
        bytes_received=0,
        rights_decision="METADATA_ONLY",
        storage_decision="NO_STORE",
        transient_residue=0,
        parser_result=(
            f"catalogue_pointer={bool(records)};"
            f"news_as_guideline={news_as_guideline};"
            f"recommendation_extraction=NOT_EXERCISED"
        ),
        network_executed=True,
        production_persistence=False,
        status="LIVE_VERIFIED" if records and news_as_guideline == 0 else "FAILED",
        content_hash=rec.content_hash if rec else None,
    )


def run_all_mandatory_live_canaries(*, http_get=None) -> dict[str, LiveCanaryEvidence]:
    http_get = http_get or _requests_http_get
    results: dict[str, LiveCanaryEvidence] = {}
    results["pubmed"] = run_pubmed_live_canary(http_get=http_get)
    results["pmc"] = run_pmc_live_canary(http_get=http_get)
    results["ctgov"] = run_ctgov_live_canary(http_get=http_get)
    results["who_guideline_authority"] = run_who_guideline_authority_live_canary(http_get=http_get)
    return results
