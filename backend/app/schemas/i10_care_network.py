"""I10 care network identity/access/grant API schemas."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.i10.policy_types import I10NotificationScope


class CaregiverAccountLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_account_user_id: int = Field(..., ge=1)
    replace_existing: bool = False


class CaregiverPhoneCandidateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: Optional[str] = Field(None, max_length=32)


class CaregiverPhoneConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_account_user_id: int = Field(..., ge=1)


class CaregiverHealthSubjectAssociateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health_subject_id: int = Field(..., ge=1)


class SubjectCaregiverAccessGrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_account_user_id: int = Field(..., ge=1)
    access_role: Literal["CAREGIVER", "MANAGER"] = "CAREGIVER"


class SubjectNotificationGrantCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_user_id: int = Field(..., ge=1)
    notification_scope: I10NotificationScope
    user_caregiver_id: Optional[int] = Field(None, ge=1)
    authorization_source: Literal["MANUAL", "CAREGIVER_PROFILE_LINK"] = "MANUAL"


class SubjectNotificationGrantRevokeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_user_id: int = Field(..., ge=1)
    notification_scope: I10NotificationScope
