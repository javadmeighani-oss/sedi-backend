"""Section 15-I5-IMPL-W1-P01 — persisted-vocabulary enums for the I5 continuity schema.

Pure, stdlib-only. Members are `str, Enum` with SCREAMING_SNAKE_CASE names whose
value equals the member name (the persisted database literal). No `auto()`,
no `sqlalchemy.Enum`, no ORM/model imports, no service/governance imports.

Do not import `ReviewStatus` or anything from
`backend.app.services.governance.contracts` here. This module must remain
importable with zero application side effects.
"""

from __future__ import annotations

from enum import Enum


class RegistryState(str, Enum):
    """Lifecycle state of a governed source profile within the I5 registry."""

    DISCOVERED = "DISCOVERED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    DEFERRED = "DEFERRED"
    BLOCKED = "BLOCKED"
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class RuntimeEligibility(str, Enum):
    """Whether a governed source profile may be used at runtime retrieval time."""

    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ELIGIBLE = "ELIGIBLE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class KnowledgeGapType(str, Enum):
    """Category of a detected knowledge gap."""

    MISSING = "MISSING"
    STALE = "STALE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONFLICTING = "CONFLICTING"
    RETRACTED = "RETRACTED"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    MISSING_RIGHTS_REVIEW = "MISSING_RIGHTS_REVIEW"
    MISSING_SAFETY_REVIEW = "MISSING_SAFETY_REVIEW"
    RUNTIME_RETRIEVAL_FAILURE = "RUNTIME_RETRIEVAL_FAILURE"


class KnowledgeGapStatus(str, Enum):
    """Lifecycle status of a knowledge gap ticket."""

    OPEN = "OPEN"
    TRIAGED = "TRIAGED"
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DEFERRED = "DEFERRED"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    REOPENED = "REOPENED"


class KnowledgeGapPriority(str, Enum):
    """Priority band of a knowledge gap ticket."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class KnowledgeGapSeverity(str, Enum):
    """Severity band of a knowledge gap ticket."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class KnowledgeGapUrgency(str, Enum):
    """Urgency band of a knowledge gap ticket."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    IMMEDIATE = "IMMEDIATE"


class WeeklyRunStatus(str, Enum):
    """Terminal/non-terminal status of a weekly governed knowledge run."""

    PLANNED = "PLANNED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    DEFERRED = "DEFERRED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class WeeklyRunAttemptStatus(str, Enum):
    """Terminal/non-terminal status of a single attempt of a weekly run."""

    CREATED = "CREATED"
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    DEFERRED = "DEFERRED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class WeeklyRunApprovalState(str, Enum):
    """Approval state of a weekly governed knowledge run."""

    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class WeeklyRunType(str, Enum):
    """Kind of weekly run. Only the governed weekly kind exists in W1-P01."""

    WEEKLY_GOVERNED = "WEEKLY_GOVERNED"


class WeeklyRunTriggerType(str, Enum):
    """What triggered creation of a weekly run."""

    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"
    RETRY_PARENT = "RETRY_PARENT"
    AD_HOC = "AD_HOC"


class RunSourceResultStatus(str, Enum):
    """Outcome recorded for a single source within a run attempt."""

    CHECKED = "CHECKED"
    FETCHED = "FETCHED"
    EXTRACTED = "EXTRACTED"
    PUBLISHED = "PUBLISHED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    WARNING = "WARNING"


class RunGapResultType(str, Enum):
    """Effect a run attempt had on a specific knowledge gap."""

    DISCOVERED = "DISCOVERED"
    UPDATED = "UPDATED"
    TRIAGED = "TRIAGED"
    PLANNED = "PLANNED"
    BLOCKED = "BLOCKED"
    DEFERRED = "DEFERRED"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"
    REJECTED = "REJECTED"
    UNCHANGED = "UNCHANGED"


class GovernanceEntityType(str, Enum):
    """Entity kinds that an I5 governance decision may target."""

    SOURCE_PROFILE = "SOURCE_PROFILE"
    SOURCE_PROFILE_VERSION = "SOURCE_PROFILE_VERSION"
    KNOWLEDGE_GAP = "KNOWLEDGE_GAP"
    WEEKLY_RUN = "WEEKLY_RUN"
    WEEKLY_RUN_ATTEMPT = "WEEKLY_RUN_ATTEMPT"
    RUN_SOURCE_RESULT = "RUN_SOURCE_RESULT"
    RUN_GAP_RESULT = "RUN_GAP_RESULT"


class GovernanceDecisionFamily(str, Enum):
    """Governance decision family (review/approval domain grouping)."""

    RIGHTS = "RIGHTS"
    AUTOMATION = "AUTOMATION"
    QUALITY = "QUALITY"
    MEDICAL_SAFETY = "MEDICAL_SAFETY"
    SECURITY = "SECURITY"
    LIFECYCLE = "LIFECYCLE"
    GAP_LIFECYCLE = "GAP_LIFECYCLE"
    RUN_APPROVAL = "RUN_APPROVAL"
    RUN_TERMINALIZATION = "RUN_TERMINALIZATION"


class GovernanceDecisionType(str, Enum):
    """Concrete governance decision type recorded for an entity."""

    RIGHTS_REVIEW = "RIGHTS_REVIEW"
    AUTOMATION_REVIEW = "AUTOMATION_REVIEW"
    QUALITY_REVIEW = "QUALITY_REVIEW"
    MEDICAL_SAFETY_REVIEW = "MEDICAL_SAFETY_REVIEW"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"
    ACTIVATION = "ACTIVATION"
    SUSPENSION = "SUSPENSION"
    REVOCATION = "REVOCATION"
    SUPERSESSION = "SUPERSESSION"
    GAP_RESOLUTION = "GAP_RESOLUTION"
    GAP_REOPEN = "GAP_REOPEN"
    RUN_APPROVAL = "RUN_APPROVAL"
    RUN_TERMINALIZATION = "RUN_TERMINALIZATION"


class GovernanceDecisionOutcome(str, Enum):
    """Outcome of a recorded governance decision."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"
    RECORDED = "RECORDED"


class GovernanceActorType(str, Enum):
    """Kind of actor that recorded a governance decision."""

    SYSTEM = "SYSTEM"
    HUMAN = "HUMAN"
    SERVICE = "SERVICE"
    JAVAD = "JAVAD"
    UNKNOWN = "UNKNOWN"
