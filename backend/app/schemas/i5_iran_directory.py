"""I5-IMPL-W5-P01 — schemas for Iran directory search (not KnowledgeUnit)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class IranDoctorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(..., pattern="^DOCTOR$")
    id: int = Field(..., gt=0)
    canonical_directory_key: str
    full_name: str
    specialty: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    record_state: str
    source_system_label: Optional[str] = None
    last_verified_at: Optional[str] = None
    last_observed_at: Optional[str] = None
    endorsement_disclaimer: str
    is_clinical_authority: bool = False
    is_knowledge_unit: bool = False


class IranLaboratoryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(..., pattern="^LABORATORY$")
    id: int = Field(..., gt=0)
    canonical_directory_key: str
    name: str
    city: Optional[str] = None
    province: Optional[str] = None
    services_text: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    record_state: str
    source_system_label: Optional[str] = None
    last_verified_at: Optional[str] = None
    last_observed_at: Optional[str] = None
    endorsement_disclaimer: str
    is_clinical_authority: bool = False
    is_knowledge_unit: bool = False


class IranHospitalView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(..., pattern="^(HOSPITAL|MEDICAL_CENTER)$")
    id: int = Field(..., gt=0)
    canonical_directory_key: str
    name: str
    facility_type: str
    city: Optional[str] = None
    province: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    record_state: str
    source_system_label: Optional[str] = None
    last_verified_at: Optional[str] = None
    last_observed_at: Optional[str] = None
    endorsement_disclaimer: str
    is_clinical_authority: bool = False
    is_knowledge_unit: bool = False


class DirectorySearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_id: str
    management_alias: str
    entity_family: str
    count: int = Field(..., ge=0)
    items: list[dict[str, Any]]
    endorsement_disclaimer: str
    is_clinical_knowledge: bool = False
    no_ir_to_ku: bool = True
