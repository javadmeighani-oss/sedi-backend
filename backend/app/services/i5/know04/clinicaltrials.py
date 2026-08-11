"""ClinicalTrials.gov API v2 official connector.

CLINICALTRIALS_REGISTRY_ENTRY != PEER_REVIEWED_EVIDENCE
TRIAL_REGISTRATION != PROVEN_TREATMENT
TRIAL_STATUS != CLINICAL_RECOMMENDATION
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping, Optional, Sequence

from backend.app.services.i5.enums import ProcessingPermissionMode, RightDecision
from backend.app.services.i5.know04.contract import ConnectorCapabilities, ConnectorRecord
from backend.app.services.i5.know04.http_client import HardenedHttpClient
from backend.app.services.i5.know04.rate_limit import TokenBucketRateLimiter
from backend.app.services.i5.know04.rights_gate import assert_no_phi_in_request, evaluate_connector_rights

API_BASE = "https://clinicaltrials.gov/api/v2"
ALLOWED = ("clinicaltrials.gov",)


@dataclass
class ClinicalTrialsGovConnector:
    connector_key: str = "clinicaltrials_gov_api_v2"
    http_get: Optional[Callable[..., Any]] = None
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            discover=True, fetch_metadata=True, fetch_record=True, fetch_changes=True
        )
    )

    def classify_rights(self, record: Optional[ConnectorRecord] = None) -> Mapping[str, Any]:
        decision = evaluate_connector_rights(
            processing_mode=ProcessingPermissionMode.DERIVED_KNOWLEDGE_ONLY.value,
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

    def _client(self) -> HardenedHttpClient:
        return HardenedHttpClient(
            allowed_domains=ALLOWED,
            rate_limiter=TokenBucketRateLimiter(max_per_second=3.0),
            http_get=self.http_get,
        )

    def discover(self, query: str, *, page_size: int = 10, page_token: Optional[str] = None) -> Mapping[str, Any]:
        if page_size > 20:
            raise ValueError("BOUNDED_CTGOV_PAGE_SIZE")
        client = self._client()
        params: dict[str, Any] = {
            "query.term": query,
            "pageSize": str(page_size),
            "format": "json",
            "countTotal": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        assert_no_phi_in_request(params)
        resp = client.get(f"{API_BASE}/studies", params=params, expect_content_types={"application/json", "text/plain"})
        data = resp.json()
        studies = data.get("studies") or []
        ids = []
        for s in studies:
            proto = (s.get("protocolSection") or {})
            ident = (proto.get("identificationModule") or {})
            nct = ident.get("nctId")
            if nct:
                ids.append(nct)
        return {
            "totalCount": data.get("totalCount"),
            "nextPageToken": data.get("nextPageToken"),
            "ids": ids,
            "studies": studies,
        }

    def fetch_record(self, nct_id: str) -> ConnectorRecord:
        client = self._client()
        params = {"format": "json"}
        assert_no_phi_in_request(params)
        resp = client.get(
            f"{API_BASE}/studies/{nct_id}",
            params=params,
            expect_content_types={"application/json", "text/plain"},
        )
        return self.normalize(resp.json())

    def normalize(self, raw: Mapping[str, Any]) -> ConnectorRecord:
        proto = raw.get("protocolSection") or raw
        ident = proto.get("identificationModule") or {}
        status = (proto.get("statusModule") or {})
        design = (proto.get("designModule") or {})
        conditions = (proto.get("conditionsModule") or {}).get("conditions") or []
        eligibility = (proto.get("eligibilityModule") or {})
        arms = (proto.get("armsInterventionsModule") or {})
        outcomes = (proto.get("outcomesModule") or {})
        contacts = (proto.get("contactsLocationsModule") or {})
        nct = ident.get("nctId") or raw.get("nct_id") or ""
        rights = self.classify_rights()
        derived = {
            "nct_id": nct,
            "brief_title": ident.get("briefTitle"),
            "official_title": ident.get("officialTitle"),
            "study_type": design.get("studyType"),
            "phases": design.get("phases"),
            "overall_status": status.get("overallStatus"),
            "start_date": (status.get("startDateStruct") or {}).get("date"),
            "completion_date": (status.get("completionDateStruct") or {}).get("date"),
            "last_update_post_date": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
            "conditions": conditions,
            "eligibility": {
                "sex": eligibility.get("sex"),
                "minimum_age": eligibility.get("minimumAge"),
                "maximum_age": eligibility.get("maximumAge"),
                "healthy_volunteers": eligibility.get("healthyVolunteers"),
                "criteria": eligibility.get("eligibilityCriteria"),
            },
            "interventions": arms.get("interventions") or [],
            "arm_groups": arms.get("armGroups") or [],
            "primary_outcomes": outcomes.get("primaryOutcomes") or [],
            "secondary_outcomes": outcomes.get("secondaryOutcomes") or [],
            "locations_as_source_data_not_medical_truth": contacts.get("locations") or [],
            "references": (proto.get("referencesModule") or {}).get("references") or [],
            # Hard invariants
            "is_peer_reviewed_evidence": False,
            "is_proven_treatment": False,
            "is_clinical_recommendation": False,
            "trial_as_recommendation_without_guideline_evidence": 0,
            "experimental_as_established_treatment": 0,
        }
        blob = repr(sorted(derived.items())).encode("utf-8")
        return ConnectorRecord(
            source_identity="clinicaltrials_gov",
            source_role="CLINICAL_TRIAL",
            official_authority="ClinicalTrials.gov / NLM",
            resource_type="CLINICAL_TRIAL_RECORD",
            external_identifier=f"NCT:{nct}",
            canonical_locator=f"https://clinicaltrials.gov/study/{nct}" if nct else None,
            version_revision=str(derived.get("last_update_post_date") or ""),
            updated_at=None,
            retrieved_at=datetime.utcnow(),
            content_hash=hashlib.sha256(blob).hexdigest(),
            processing_decision=rights["processing_decision"],
            storage_decision=rights["storage_decision"],
            provenance={"connector": self.connector_key},
            payload=derived,
            synthetic_fixture=bool(raw.get("synthetic_fixture")),
        )

    def emit_artifact_candidate(self, record: ConnectorRecord) -> Mapping[str, Any]:
        """Map into KNOW-03 study identity fields — never into recommendation."""
        p = record.payload
        return {
            "registry_identifier": p.get("nct_id"),
            "title": p.get("brief_title") or p.get("official_title"),
            "study_design": p.get("study_type"),
            "status": p.get("overall_status"),
            "artifact_type": "CLINICAL_TRIAL_RECORD",
            "must_not_become_recommendation": True,
            "must_not_become_established_treatment": True,
        }
