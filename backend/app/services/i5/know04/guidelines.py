"""Guideline / feed / syndication connector framework.

Do NOT invent APIs. Classify access mechanism honestly.
At least one official syndication/API path implemented end-to-end where usable.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Optional, Sequence

from backend.app.services.i5.enums import ProcessingPermissionMode, RightDecision
from backend.app.services.i5.know04.contract import ConnectorCapabilities, ConnectorRecord
from backend.app.services.i5.know04.http_client import HardenedHttpClient
from backend.app.services.i5.know04.rate_limit import TokenBucketRateLimiter
from backend.app.services.i5.know04.rights_gate import assert_no_phi_in_request, evaluate_connector_rights
from backend.app.services.i5.know04.xml_safety import safe_parse_xml

# WHO IRIS / news feed is a stable official public syndication surface.
WHO_NEWS_FEED = "https://www.who.int/rss-feeds/news-english.xml"
WHO_ALLOWED = ("www.who.int", "who.int")


GUIDELINE_SOURCE_CLASSIFICATIONS: dict[str, dict[str, str]] = {
    "who_guidelines": {
        "access_mechanism": "OFFICIAL_FEED",
        "authority": "World Health Organization",
        "blocker": "",
        "canary_feed": WHO_NEWS_FEED,
    },
    "nice_guidelines": {
        "access_mechanism": "OFFICIAL_API",
        "authority": "NICE (UK)",
        "blocker": "AUTH_OR_TERMS_REVIEW_REQUIRED",
        "canary_feed": "",
    },
    "aan_guidelines": {
        "access_mechanism": "OFFICIAL_HTML_ONLY",
        "authority": "American Academy of Neurology",
        "blocker": "NO_STABLE_PUBLIC_MACHINE_FEED_VERIFIED",
        "canary_feed": "",
    },
    "ean_guidelines": {
        "access_mechanism": "MANUAL_REVIEW_REQUIRED",
        "authority": "European Academy of Neurology",
        "blocker": "NO_SUPPORTED_AUTOMATION_VERIFIED",
        "canary_feed": "",
    },
    "ectrims_guidelines": {
        "access_mechanism": "MANUAL_REVIEW_REQUIRED",
        "authority": "ECTRIMS",
        "blocker": "NO_SUPPORTED_AUTOMATION_VERIFIED",
        "canary_feed": "",
    },
    "ada_standards": {
        "access_mechanism": "OFFICIAL_HTML_ONLY",
        "authority": "American Diabetes Association",
        "blocker": "RIGHTS_REVIEW_REQUIRED_FOR_AUTOMATION",
        "canary_feed": "",
    },
    "cdc_guidelines": {
        "access_mechanism": "OFFICIAL_FEED",
        "authority": "CDC",
        "blocker": "SOURCE_SPECIFIC_FEED_BINDING_PENDING",
        "canary_feed": "",
    },
    "nhs_guidelines": {
        "access_mechanism": "OFFICIAL_HTML_ONLY",
        "authority": "NHS",
        "blocker": "RIGHTS_REVIEW_REQUIRED_FOR_AUTOMATION",
        "canary_feed": "",
    },
}


@dataclass
class GuidelineFeedConnector:
    connector_key: str = "who_guidelines_feed"
    source_key: str = "who_guidelines"
    feed_url: str = WHO_NEWS_FEED
    http_get: Optional[Callable[..., Any]] = None
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            discover=True, fetch_metadata=True, fetch_record=True, fetch_changes=True
        )
    )

    def classify_rights(self, record: Optional[ConnectorRecord] = None) -> Mapping[str, Any]:
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
        )
        return decision.__dict__

    def access_mechanism_for(self, source_key: str) -> Mapping[str, str]:
        return GUIDELINE_SOURCE_CLASSIFICATIONS.get(
            source_key,
            {
                "access_mechanism": "NO_SUPPORTED_AUTOMATION",
                "authority": "UNKNOWN",
                "blocker": "UNREGISTERED_SOURCE",
                "canary_feed": "",
            },
        )

    def discover(self) -> list[dict[str, Any]]:
        meta = self.access_mechanism_for(self.source_key)
        if meta["access_mechanism"] in {"MANUAL_REVIEW_REQUIRED", "NO_SUPPORTED_AUTOMATION"}:
            raise PermissionError(f"AUTOMATION_BLOCKED:{meta.get('blocker')}")
        client = HardenedHttpClient(
            allowed_domains=WHO_ALLOWED,
            rate_limiter=TokenBucketRateLimiter(max_per_second=1.0),
            http_get=self.http_get,
        )
        assert_no_phi_in_request({})
        resp = client.get(self.feed_url, expect_content_types={"application/rss+xml", "application/xml", "text/xml", "text/html", "text/plain"})
        return self.parse_rss(resp.content)

    def parse_rss(self, content: bytes) -> list[dict[str, Any]]:
        root = safe_parse_xml(content)
        items = []
        for item in root.findall(".//item"):
            items.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "guid": (item.findtext("guid") or item.findtext("link") or "").strip(),
                    "pubDate": (item.findtext("pubDate") or "").strip(),
                    "description": (item.findtext("description") or "").strip(),
                    "synthetic_fixture": False,
                }
            )
        return items

    def normalize(self, raw: Mapping[str, Any]) -> ConnectorRecord:
        rights = self.classify_rights()
        guid = str(raw.get("guid") or raw.get("link") or "")
        blob = repr(sorted(raw.items())).encode("utf-8")
        return ConnectorRecord(
            source_identity=self.source_key,
            source_role="CLINICAL_GUIDELINE",
            official_authority=self.access_mechanism_for(self.source_key)["authority"],
            resource_type="GUIDELINE_FEED_ITEM",
            external_identifier=guid,
            canonical_locator=raw.get("link"),
            version_revision=str(raw.get("pubDate") or ""),
            retrieved_at=datetime.utcnow(),
            content_hash=hashlib.sha256(blob).hexdigest(),
            processing_decision=rights["processing_decision"],
            storage_decision=rights["storage_decision"],
            provenance={"connector": self.connector_key, "preserve_original_grading": True},
            payload={
                **dict(raw),
                # Recommendation import fields preserved when present — do not invent grades
                "publisher": self.access_mechanism_for(self.source_key)["authority"],
                "guideline_identity": guid,
                "guideline_version": raw.get("pubDate"),
                "recommendation_text": raw.get("description") or raw.get("title"),
                "original_grade": raw.get("original_grade"),
                "original_certainty": raw.get("original_certainty"),
                "direction": raw.get("direction"),
                "target_population": raw.get("target_population"),
                "benefits": raw.get("benefits"),
                "harms": raw.get("harms"),
                "exceptions": raw.get("exceptions"),
                "contraindications": raw.get("contraindications"),
                "monitoring": raw.get("monitoring"),
                "effective_from": raw.get("effective_from"),
                "effective_until": raw.get("effective_until"),
                "supersession": raw.get("supersession"),
            },
            synthetic_fixture=bool(raw.get("synthetic_fixture")),
        )
