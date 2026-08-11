"""Bounded official live connector canaries — NF17 observed network evidence (no Production writes)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from backend.app.services.i5.know04.clinicaltrials import ClinicalTrialsGovConnector
from backend.app.services.i5.know04.guidelines import WhoGuidelineCatalogueConnector, WhoNewsDiscoveryConnector
from backend.app.services.i5.know04.pmc import PmcConnector
from backend.app.services.i5.know04.pmc_oai import PmcOaiConnector
from backend.app.services.i5.know04.pubmed import PubMedConnector, PubMedConnectorConfig
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity


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
    request_count: int = 0
    records_discovered: int = 0
    records_accepted: int = 0
    records_rejected: int = 0

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
            "request_count": self.request_count,
            "records_discovered": self.records_discovered,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
        }


@dataclass
class ObservingHttpGet:
    """Wrap http_get and record observed status/bytes/content-type (NF17)."""

    inner: Callable[..., Any]
    statuses: list[int] = field(default_factory=list)
    bytes_list: list[int] = field(default_factory=list)
    content_types: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)

    def __call__(self, url, headers=None, timeout=None):
        resp = self.inner(url, headers=headers, timeout=timeout)
        status = int(getattr(resp, "status_code", 0) or 0)
        content = getattr(resp, "content", b"") or b""
        if isinstance(content, str):
            content = content.encode("utf-8")
        hdrs = getattr(resp, "headers", {}) or {}
        ctype = ""
        try:
            ctype = str(hdrs.get("Content-Type") or hdrs.get("content-type") or "")
        except Exception:
            ctype = ""
        self.statuses.append(status)
        self.bytes_list.append(len(content))
        self.content_types.append(ctype.split(";")[0].strip() if ctype else "")
        self.urls.append(str(url))
        return resp

    @property
    def last_status(self) -> int:
        return self.statuses[-1] if self.statuses else 0

    @property
    def total_bytes(self) -> int:
        return sum(self.bytes_list)

    @property
    def last_content_type(self) -> str:
        return self.content_types[-1] if self.content_types else ""

    @property
    def request_count(self) -> int:
        return len(self.statuses)


def _requests_http_get(url, headers=None, timeout=None):
    import requests

    return requests.get(url, headers=headers or {}, timeout=timeout or 15)


def run_pubmed_live_canary(*, http_get=None, max_records: int = 2) -> LiveCanaryEvidence:
    identity = load_ncbi_operational_identity(require_for_weekly=True)
    if identity.weekly_operation_status != "LIVE_READY":
        return LiveCanaryEvidence(
            connector="pubmed_ncbi_eutils",
            official_host="eutils.ncbi.nlm.nih.gov",
            request_purpose="bounded_esearch_esummary",
            timestamp_utc=_utc_now(),
            http_status=0,
            content_type="",
            record_count=0,
            external_ids=(),
            bytes_received=0,
            rights_decision="NOT_EXECUTED",
            storage_decision="NO_STORE",
            transient_residue=0,
            parser_result=identity.weekly_operation_status,
            network_executed=False,
            production_persistence=False,
            status=identity.weekly_operation_status,
            request_count=0,
        )
    obs = ObservingHttpGet(http_get or _requests_http_get)
    cfg = PubMedConnectorConfig.from_env(allow_disallowed_email=False)
    conn = PubMedConnector(config=cfg, http_get=obs, sleep_fn=lambda s: None)
    discovered = conn.discover("diabetes[tiab]", retmax=max_records)
    ids = tuple(str(x) for x in (discovered.get("ids") or [])[:max_records])
    if ids:
        conn.fetch_metadata(list(ids))
    ok = bool(ids) and obs.last_status and 200 <= obs.last_status < 300 and obs.total_bytes > 0
    return LiveCanaryEvidence(
        connector="pubmed_ncbi_eutils",
        official_host="eutils.ncbi.nlm.nih.gov",
        request_purpose="bounded_esearch_esummary",
        timestamp_utc=_utc_now(),
        http_status=obs.last_status,
        content_type=obs.last_content_type or "application/json",
        record_count=len(ids),
        external_ids=ids,
        bytes_received=obs.total_bytes,
        rights_decision="METADATA_ONLY",
        storage_decision="NO_STORE",
        transient_residue=0,
        parser_result="PASS" if ids else "EMPTY",
        network_executed=True,
        production_persistence=False,
        status="LIVE_VERIFIED" if ok else "FAILED",
        content_hash=hashlib.sha256(",".join(ids).encode()).hexdigest() if ids else None,
        request_count=obs.request_count,
        records_discovered=len(ids),
        records_accepted=len(ids),
        records_rejected=0,
    )


def run_pmc_live_canary(*, http_get=None, max_records: int = 1) -> LiveCanaryEvidence:
    obs = ObservingHttpGet(http_get or _requests_http_get)
    oai = PmcOaiConnector(http_get=obs)
    records = oai.list_records(max_records=max_records)
    pmcid = records[0]["pmcid"] if records else ""
    license_obs = None
    if pmcid:
        pmc = PmcConnector(http_get=obs)
        try:
            oa = pmc.fetch_oa_metadata(pmcid)
            for rec in oa.get("records") or []:
                license_obs = rec.get("license")
        except Exception:
            license_obs = "UNKNOWN"
    ok = bool(records) and obs.last_status and 200 <= obs.last_status < 300 and obs.total_bytes > 0
    return LiveCanaryEvidence(
        connector="pmc_oai_pmh",
        official_host="www.ncbi.nlm.nih.gov",
        request_purpose="bounded_oai_listrecords+oa_license",
        timestamp_utc=_utc_now(),
        http_status=obs.last_status,
        content_type=obs.last_content_type or "application/xml",
        record_count=len(records),
        external_ids=tuple(r.get("pmcid", "") for r in records),
        bytes_received=obs.total_bytes,
        rights_decision="METADATA_ONLY",
        storage_decision="NO_STORE",
        transient_residue=0,
        parser_result=f"license={license_obs or 'N/A'}",
        network_executed=True,
        production_persistence=False,
        status="LIVE_VERIFIED" if ok else "FAILED",
        content_hash=records[0].get("content_hash") if records else None,
        request_count=obs.request_count,
        records_discovered=len(records),
        records_accepted=len(records),
        records_rejected=0,
    )


def run_ctgov_live_canary(*, http_get=None) -> LiveCanaryEvidence:
    obs = ObservingHttpGet(http_get or _requests_http_get)
    ct = ClinicalTrialsGovConnector(http_get=obs)
    version_resp = obs("https://clinicaltrials.gov/api/v2/version", timeout=15)
    version_data = version_resp.json() if hasattr(version_resp, "json") else {}
    discovered = ct.discover("diabetes", page_size=1)
    nct_ids = tuple(str(x) for x in (discovered.get("ids") or [])[:1])
    ok = bool(nct_ids) and obs.last_status and 200 <= obs.last_status < 300 and obs.total_bytes > 0
    return LiveCanaryEvidence(
        connector="clinicaltrials_gov_api_v2",
        official_host="clinicaltrials.gov",
        request_purpose="version+bounded_study_search",
        timestamp_utc=_utc_now(),
        content_type=obs.last_content_type or "application/json",
        http_status=obs.last_status,
        record_count=len(nct_ids),
        external_ids=nct_ids,
        bytes_received=obs.total_bytes,
        rights_decision="DERIVED_ONLY",
        storage_decision="NO_STORE",
        transient_residue=0,
        parser_result=f"dataTimestamp={version_data.get('dataTimestamp', 'N/A')}",
        network_executed=True,
        production_persistence=False,
        status="LIVE_VERIFIED" if ok else "FAILED",
        content_hash=hashlib.sha256(str(version_data).encode()).hexdigest()[:32],
        request_count=obs.request_count,
        records_discovered=len(nct_ids),
        records_accepted=len(nct_ids),
        records_rejected=0,
    )


def run_who_guideline_authority_live_canary(*, http_get=None) -> LiveCanaryEvidence:
    obs = ObservingHttpGet(http_get or _requests_http_get)
    cat = WhoGuidelineCatalogueConnector(http_get=obs)
    records = cat.discover(max_records=1)
    rec = cat.normalize(records[0]) if records else None
    news = WhoNewsDiscoveryConnector(http_get=obs)
    news_items = news.discover(max_items=1)
    news_rec = news.normalize(news_items[0]) if news_items else None
    news_as_guideline = 0
    if news_rec and news_rec.payload.get("clinical_guideline"):
        news_as_guideline = 1
    if news_rec and news_rec.payload.get("recommendation_text"):
        news_as_guideline = 1
    ok = (
        bool(records)
        and news_as_guideline == 0
        and obs.last_status
        and 200 <= obs.last_status < 300
        and obs.total_bytes > 0
    )
    return LiveCanaryEvidence(
        connector="who_guideline_catalogue",
        official_host="www.who.int",
        request_purpose="grc_catalogue_pointer+news_discovery_control",
        timestamp_utc=_utc_now(),
        http_status=obs.last_status,
        content_type=obs.last_content_type or "text/html",
        record_count=len(records),
        external_ids=tuple(r.get("external_identifier", "") for r in records),
        bytes_received=obs.total_bytes,
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
        status="LIVE_VERIFIED" if ok else "FAILED",
        content_hash=rec.content_hash if rec else None,
        request_count=obs.request_count,
        records_discovered=len(records),
        records_accepted=len(records),
        records_rejected=0,
    )


def run_all_mandatory_live_canaries(*, http_get=None) -> dict[str, LiveCanaryEvidence]:
    http_get = http_get or _requests_http_get
    return {
        "pubmed": run_pubmed_live_canary(http_get=http_get),
        "pmc": run_pmc_live_canary(http_get=http_get),
        "ctgov": run_ctgov_live_canary(http_get=http_get),
        "who_guideline_authority": run_who_guideline_authority_live_canary(http_get=http_get),
    }
