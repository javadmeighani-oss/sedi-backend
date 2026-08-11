"""Guideline / discovery connector framework — NF14 authority semantics.

NEWS != GUIDELINE. DISCOVERY_SIGNAL != MEDICAL_AUTHORITY.
WHO news RSS is discovery-only; WHO GRC/publications catalogue is guideline authority pointer.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from backend.app.services.i5.enums import ProcessingPermissionMode, RightDecision
from backend.app.services.i5.know04.authority_promotion import (
    STAGE_DISCOVERED,
    STAGE_VERIFIED_ARTIFACT_POINTER,
    assert_catalogue_not_recommendation,
    assert_news_not_guideline_authority,
)
from backend.app.services.i5.know04.contract import ConnectorCapabilities, ConnectorRecord
from backend.app.services.i5.know04.http_client import HardenedHttpClient
from backend.app.services.i5.know04.rate_limit import TokenBucketRateLimiter
from backend.app.services.i5.know04.rights_gate import assert_no_phi_in_request, evaluate_connector_rights
from backend.app.services.i5.know04.xml_safety import safe_parse_xml

WHO_NEWS_FEED = "https://www.who.int/rss-feeds/news-english.xml"
WHO_GUIDELINE_CATALOGUE_URL = "https://www.who.int/publications/who-guidelines"
WHO_ALLOWED = ("www.who.int", "who.int")

# GRC-approved guideline publication item pattern (official WHO publications portal).
_GUIDELINE_PUBLICATION_HREF = re.compile(
    r"https?://(?:www\.)?who\.int/publications/i/item/[^\s\"'<>]+",
    re.I,
)


GUIDELINE_SOURCE_CLASSIFICATIONS: dict[str, dict[str, str]] = {
    "who_news": {
        "access_mechanism": "OFFICIAL_FEED",
        "authority": "World Health Organization",
        "who_artifact_kind": "WHO_NEWS",
        "blocker": "",
        "canary_url": WHO_NEWS_FEED,
    },
    "who_guideline_catalogue": {
        "access_mechanism": "OFFICIAL_HTML_CATALOGUE",
        "authority": "World Health Organization / GRC",
        "who_artifact_kind": "WHO_GUIDELINE_CATALOGUE",
        "blocker": "",
        "canary_url": WHO_GUIDELINE_CATALOGUE_URL,
    },
    "nice_guidelines": {
        "access_mechanism": "OFFICIAL_API",
        "authority": "NICE (UK)",
        "who_artifact_kind": "",
        "blocker": "AUTH_OR_TERMS_REVIEW_REQUIRED",
        "canary_url": "",
    },
    "aan_guidelines": {
        "access_mechanism": "OFFICIAL_HTML_ONLY",
        "authority": "American Academy of Neurology",
        "who_artifact_kind": "",
        "blocker": "NO_STABLE_PUBLIC_MACHINE_FEED_VERIFIED",
        "canary_url": "",
    },
    "ean_guidelines": {
        "access_mechanism": "MANUAL_REVIEW_REQUIRED",
        "authority": "European Academy of Neurology",
        "who_artifact_kind": "",
        "blocker": "NO_SUPPORTED_AUTOMATION_VERIFIED",
        "canary_url": "",
    },
    "ectrims_guidelines": {
        "access_mechanism": "MANUAL_REVIEW_REQUIRED",
        "authority": "ECTRIMS",
        "who_artifact_kind": "",
        "blocker": "NO_SUPPORTED_AUTOMATION_VERIFIED",
        "canary_url": "",
    },
    "ada_standards": {
        "access_mechanism": "OFFICIAL_HTML_ONLY",
        "authority": "American Diabetes Association",
        "who_artifact_kind": "",
        "blocker": "RIGHTS_REVIEW_REQUIRED_FOR_AUTOMATION",
        "canary_url": "",
    },
    "cdc_guidelines": {
        "access_mechanism": "OFFICIAL_FEED",
        "authority": "CDC",
        "who_artifact_kind": "",
        "blocker": "SOURCE_SPECIFIC_FEED_BINDING_PENDING",
        "canary_url": "",
    },
    "nhs_guidelines": {
        "access_mechanism": "OFFICIAL_HTML_ONLY",
        "authority": "NHS",
        "who_artifact_kind": "",
        "blocker": "RIGHTS_REVIEW_REQUIRED_FOR_AUTOMATION",
        "canary_url": "",
    },
}


def _discovery_rights() -> Mapping[str, Any]:
    return evaluate_connector_rights(
        processing_mode=ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
        access_right=RightDecision.ALLOWED.value,
        automation_right=RightDecision.ALLOWED.value,
        tdm_right=RightDecision.ALLOWED.value,
        transform_right=RightDecision.ALLOWED.value,
        retain_raw_right=RightDecision.DENIED.value,
        retain_derived_right=RightDecision.ALLOWED.value,
        redistribute_right=RightDecision.DENIED.value,
        robots_state="ALLOWED",
    ).__dict__


@dataclass
class WhoNewsDiscoveryConnector:
    """Official WHO news RSS — discovery/update signal only (NOT guideline authority)."""

    connector_key: str = "who_news_discovery"
    source_key: str = "who_news"
    feed_url: str = WHO_NEWS_FEED
    http_get: Optional[Callable[..., Any]] = None
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(discover=True, fetch_metadata=True)
    )

    def discover(self, *, max_items: int = 5) -> list[dict[str, Any]]:
        client = HardenedHttpClient(
            allowed_domains=WHO_ALLOWED,
            rate_limiter=TokenBucketRateLimiter(max_per_second=1.0),
            http_get=self.http_get,
        )
        assert_no_phi_in_request({})
        resp = client.get(
            self.feed_url,
            expect_content_types={
                "application/rss+xml",
                "application/xml",
                "text/xml",
                "text/html",
                "text/plain",
            },
        )
        return self.parse_rss(resp.content, max_items=max_items)

    def parse_rss(self, content: bytes, *, max_items: int = 50) -> list[dict[str, Any]]:
        root = safe_parse_xml(content)
        items: list[dict[str, Any]] = []
        for item in root.findall(".//item")[:max_items]:
            items.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "guid": (item.findtext("guid") or item.findtext("link") or "").strip(),
                    "pubDate": (item.findtext("pubDate") or "").strip(),
                    "description": (item.findtext("description") or "").strip(),
                    "who_artifact_kind": "WHO_NEWS",
                    "synthetic_fixture": False,
                }
            )
        return items

    def normalize(self, raw: Mapping[str, Any]) -> ConnectorRecord:
        rights = _discovery_rights()
        guid = str(raw.get("guid") or raw.get("link") or "")
        blob = repr(sorted((k, raw[k]) for k in sorted(raw.keys()))).encode("utf-8")
        payload = {
            **dict(raw),
            "publisher": "World Health Organization",
            "who_artifact_kind": "WHO_NEWS",
            "authority_stage": STAGE_DISCOVERED,
            "clinical_guideline": False,
            "clinical_recommendation": False,
            "runtime_medical_authority": False,
            "discovery_signal": True,
            "recommendation_text": None,
            "recommendation_extraction": "NOT_EXERCISED",
            "headline": raw.get("title"),
            "discovery_note": raw.get("description"),
        }
        assert_news_not_guideline_authority(
            source_role="NEWS_OR_DISCOVERY_SIGNAL",
            resource_type="NEWS_ITEM",
            clinical_guideline=False,
            clinical_recommendation=False,
            runtime_medical_authority=False,
            recommendation_text=None,
        )
        return ConnectorRecord(
            source_identity="who",
            source_role="NEWS_OR_DISCOVERY_SIGNAL",
            official_authority="World Health Organization",
            resource_type="NEWS_ITEM",
            external_identifier=guid or f"who-news:{hashlib.sha256(blob).hexdigest()[:16]}",
            canonical_locator=raw.get("link"),
            version_revision=str(raw.get("pubDate") or ""),
            retrieved_at=datetime.utcnow(),
            content_hash=hashlib.sha256(blob).hexdigest(),
            processing_decision=rights["processing_decision"],
            storage_decision=rights["storage_decision"],
            provenance={
                "connector": self.connector_key,
                "discovery_only": True,
                "promotion_required": "NEWS->ARTIFACT->GUIDELINE->RECOMMENDATION",
            },
            payload=payload,
            synthetic_fixture=bool(raw.get("synthetic_fixture")),
        )


@dataclass
class WhoGuidelineCatalogueConnector:
    """Official WHO GRC/publications catalogue — bounded HTML discovery (NOT recommendation parser)."""

    connector_key: str = "who_guideline_catalogue"
    source_key: str = "who_guideline_catalogue"
    catalogue_url: str = WHO_GUIDELINE_CATALOGUE_URL
    http_get: Optional[Callable[..., Any]] = None
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(discover=True, fetch_metadata=True)
    )

    def discover(self, *, max_records: int = 3) -> list[dict[str, Any]]:
        client = HardenedHttpClient(
            allowed_domains=WHO_ALLOWED,
            rate_limiter=TokenBucketRateLimiter(max_per_second=1.0),
            http_get=self.http_get,
        )
        assert_no_phi_in_request({})
        resp = client.get(
            self.catalogue_url,
            expect_content_types={"text/html", "application/xhtml+xml", "text/plain"},
        )
        return self.parse_catalogue_html(resp.content, max_records=max_records)

    def parse_catalogue_html(self, content: bytes, *, max_records: int = 10) -> list[dict[str, Any]]:
        text = content.decode("utf-8", errors="replace")
        hrefs = _GUIDELINE_PUBLICATION_HREF.findall(text)
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for href in hrefs:
            if href in seen:
                continue
            seen.add(href)
            records.append(
                {
                    "canonical_locator": href,
                    "external_identifier": href.rsplit("/", 1)[-1],
                    "who_artifact_kind": "WHO_GUIDELINE_CATALOGUE_ENTRY",
                    "synthetic_fixture": False,
                }
            )
            if len(records) >= max_records:
                break
        return records

    def normalize(self, raw: Mapping[str, Any]) -> ConnectorRecord:
        rights = _discovery_rights()
        locator = str(raw.get("canonical_locator") or raw.get("link") or "")
        ext_id = str(raw.get("external_identifier") or locator.rsplit("/", 1)[-1])
        blob = repr(sorted((k, raw[k]) for k in sorted(raw.keys()))).encode("utf-8")
        payload = {
            **dict(raw),
            "publisher": "World Health Organization / GRC",
            "who_artifact_kind": "WHO_GUIDELINE_CATALOGUE_ENTRY",
            "authority_stage": STAGE_VERIFIED_ARTIFACT_POINTER,
            "clinical_guideline": False,
            "clinical_recommendation": False,
            "runtime_medical_authority": False,
            "guideline_catalogue_pointer": True,
            "recommendation_text": None,
            "recommendation_extraction": "NOT_EXERCISED",
        }
        assert_catalogue_not_recommendation(
            who_artifact_kind="WHO_GUIDELINE_CATALOGUE_ENTRY",
            clinical_recommendation=False,
            recommendation_text=None,
        )
        return ConnectorRecord(
            source_identity="who",
            source_role="CLINICAL_GUIDELINE",
            official_authority="World Health Organization / GRC",
            resource_type="WHO_GUIDELINE_CATALOGUE_ENTRY",
            external_identifier=f"WHO-GRC:{ext_id}",
            canonical_locator=locator or None,
            retrieved_at=datetime.utcnow(),
            content_hash=hashlib.sha256(blob).hexdigest(),
            processing_decision=rights["processing_decision"],
            storage_decision=rights["storage_decision"],
            provenance={
                "connector": self.connector_key,
                "catalogue_pointer_only": True,
                "verified_guideline_requires_artifact_fetch": True,
            },
            payload=payload,
            synthetic_fixture=bool(raw.get("synthetic_fixture")),
        )


# Backward-compatible alias — semantics corrected to WHO news discovery (NF14).
GuidelineFeedConnector = WhoNewsDiscoveryConnector
