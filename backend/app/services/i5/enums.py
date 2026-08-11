"""Section 15-I5-IMPL-W1-P01/W1-P02 — persisted-vocabulary enums for the I5 continuity schema.

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


# ---------------------------------------------------------------------------
# I5-IMPL-W1-P02 — Raw Retention / Knowledge Unit / Provenance vocabularies
# ---------------------------------------------------------------------------


class RawRetentionMode(str, Enum):
    """Canonical raw evidence retention mode (v531 Design Freeze literals)."""

    RAW_FULL_GOVERNED_RETENTION = "RAW_FULL_GOVERNED_RETENTION"
    RAW_TRANSIENT_PROCESSING = "RAW_TRANSIENT_PROCESSING"
    RAW_MINIMAL_EVIDENCE_ONLY = "RAW_MINIMAL_EVIDENCE_ONLY"
    RAW_LINK_AND_CITATION_ONLY = "RAW_LINK_AND_CITATION_ONLY"
    RAW_EXCLUDED_PROTECTED_ELEMENTS = "RAW_EXCLUDED_PROTECTED_ELEMENTS"


class RawStorageMode(str, Enum):
    """Where retained raw evidence bytes/metadata are stored."""

    OBJECT_STORE = "OBJECT_STORE"
    DATABASE_INLINE = "DATABASE_INLINE"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"
    NONE = "NONE"


class RightsTermsState(str, Enum):
    """Licence / rights / terms review state for retained evidence."""

    UNKNOWN = "UNKNOWN"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    RESTRICTED = "RESTRICTED"
    PROHIBITED = "PROHIBITED"
    EXPIRED = "EXPIRED"


class RobotsAccessState(str, Enum):
    """Robots / access-policy state for retained evidence."""

    UNKNOWN = "UNKNOWN"
    ALLOWED = "ALLOWED"
    DISALLOWED = "DISALLOWED"
    CONDITIONAL = "CONDITIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RedactionState(str, Enum):
    """Redaction state of retained evidence."""

    NONE = "NONE"
    PARTIAL = "PARTIAL"
    FULL = "FULL"
    REQUIRED = "REQUIRED"


class ProhibitedDataState(str, Enum):
    """Whether prohibited data classes are present or cleared."""

    CLEARED = "CLEARED"
    SUSPECTED = "SUSPECTED"
    CONFIRMED_PROHIBITED = "CONFIRMED_PROHIBITED"
    UNKNOWN = "UNKNOWN"


class ExpiryState(str, Enum):
    """Expiry / tombstone lifecycle for retained evidence."""

    ACTIVE = "ACTIVE"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"
    TOMBSTONED = "TOMBSTONED"
    SUPERSEDED = "SUPERSEDED"


class KnowledgeType(str, Enum):
    """Structured knowledge unit knowledge type."""

    FACT = "FACT"
    GUIDELINE = "GUIDELINE"
    RECOMMENDATION = "RECOMMENDATION"
    WARNING = "WARNING"
    DEFINITION = "DEFINITION"
    PROCEDURE = "PROCEDURE"
    OTHER = "OTHER"


class EvidenceStrength(str, Enum):
    """Evidence strength band for a knowledge unit."""

    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CONFLICTED = "CONFLICTED"


class MedicalSafetyState(str, Enum):
    """Medical safety review state for a knowledge unit."""

    UNKNOWN = "UNKNOWN"
    PENDING_REVIEW = "PENDING_REVIEW"
    CLEARED = "CLEARED"
    RESTRICTED = "RESTRICTED"
    BLOCKED = "BLOCKED"


class ConflictState(str, Enum):
    """Conflict state for a knowledge unit."""

    NONE = "NONE"
    SUSPECTED = "SUSPECTED"
    CONFIRMED = "CONFIRMED"
    RESOLVED = "RESOLVED"


class FreshnessState(str, Enum):
    """Freshness state for a knowledge unit."""

    UNKNOWN = "UNKNOWN"
    CURRENT = "CURRENT"
    STALE = "STALE"
    EXPIRED = "EXPIRED"


class ReviewState(str, Enum):
    """Review state for a knowledge unit."""

    NOT_REVIEWED = "NOT_REVIEWED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class PublicationState(str, Enum):
    """Publication state for a knowledge unit."""

    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"
    SUPERSEDED = "SUPERSEDED"


class KnowledgeUnitRuntimeEligibility(str, Enum):
    """Runtime eligibility for a structured knowledge unit (fail-closed default)."""

    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ELIGIBLE = "ELIGIBLE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


# ---------------------------------------------------------------------------
# I5-IMPL-W2-P01 — Knowledge Memory / Versioning / Diff / Supersession
# ---------------------------------------------------------------------------


class SupersessionState(str, Enum):
    """Supersession / currency state for a knowledge memory projection."""

    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"
    STALE = "STALE"
    WITHDRAWN = "WITHDRAWN"
    CONFLICTED = "CONFLICTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    REJECTED = "REJECTED"
    RETRACTED = "RETRACTED"


class MemoryChangeKind(str, Enum):
    """Material-change classification for a knowledge-unit revision."""

    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    CONTENT_CHANGE = "CONTENT_CHANGE"
    SOURCE_METADATA_CHANGE = "SOURCE_METADATA_CHANGE"
    PROVENANCE_CHANGE = "PROVENANCE_CHANGE"
    SAFETY_GOVERNANCE_CHANGE = "SAFETY_GOVERNANCE_CHANGE"
    RETRACTION_WITHDRAWAL = "RETRACTION_WITHDRAWAL"


class MemoryTransitionKind(str, Enum):
    """Kind of recorded knowledge-memory transition event."""

    CREATED = "CREATED"
    NO_CHANGE = "NO_CHANGE"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"
    WITHDRAWN = "WITHDRAWN"
    CURRENT_VERSION_CHANGED = "CURRENT_VERSION_CHANGED"


# ---------------------------------------------------------------------------
# I5-IMPL-W2-P02 — Evidence / Freshness / Conflict / Medical-Safety queue
# ---------------------------------------------------------------------------


class SafetyReviewQueueStatus(str, Enum):
    """Lifecycle status of a medical-safety review queue item."""

    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    CLOSED_CLEARED = "CLOSED_CLEARED"
    CLOSED_RESTRICTED = "CLOSED_RESTRICTED"
    CLOSED_BLOCKED = "CLOSED_BLOCKED"
    CLOSED_REJECTED = "CLOSED_REJECTED"


# ---------------------------------------------------------------------------
# I5-KNOW-01 — Trusted Source Registry / Rights / Books
# ---------------------------------------------------------------------------


class ProcessingPermissionMode(str, Enum):
    """Frozen KNOW-01 rights processing modes (map to RawRetentionMode)."""

    FULL_PROCESS_AND_RETAIN = "FULL_PROCESS_AND_RETAIN"
    TRANSIENT_PROCESS_ONLY = "TRANSIENT_PROCESS_ONLY"
    DERIVED_KNOWLEDGE_ONLY = "DERIVED_KNOWLEDGE_ONLY"
    METADATA_ABSTRACT_ONLY = "METADATA_ABSTRACT_ONLY"
    FULLTEXT_AUTOMATION_BLOCKED = "FULLTEXT_AUTOMATION_BLOCKED"
    LICENSED_CONNECTOR_ONLY = "LICENSED_CONNECTOR_ONLY"


class RightDecision(str, Enum):
    """Per-dimension rights decision (not a single boolean)."""

    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN = "UNKNOWN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class SourceUniverse(str, Enum):
    """Hard separation: global clinical knowledge vs Iran local directory."""

    GLOBAL_KNOWLEDGE = "GLOBAL_KNOWLEDGE"
    IRAN_LOCAL_DIRECTORY = "IRAN_LOCAL_DIRECTORY"
    REFERENCE_BOOK = "REFERENCE_BOOK"
    MIXED_EXPLICIT = "MIXED_EXPLICIT"


class SourceAuthorityClass(str, Enum):
    """Queryable authority classification for registry sources."""

    GLOBAL_INTERGOVERNMENTAL = "GLOBAL_INTERGOVERNMENTAL"
    NATIONAL_HEALTH_AUTHORITY = "NATIONAL_HEALTH_AUTHORITY"
    REGULATORY_AUTHORITY = "REGULATORY_AUTHORITY"
    OFFICIAL_PUBLIC_HEALTH = "OFFICIAL_PUBLIC_HEALTH"
    NATIONAL_MEDICAL_LIBRARY = "NATIONAL_MEDICAL_LIBRARY"
    PROFESSIONAL_MEDICAL_SOCIETY = "PROFESSIONAL_MEDICAL_SOCIETY"
    SPECIALTY_GUIDELINE_BODY = "SPECIALTY_GUIDELINE_BODY"
    SYSTEMATIC_REVIEW_AUTHORITY = "SYSTEMATIC_REVIEW_AUTHORITY"
    PEER_REVIEWED_JOURNAL = "PEER_REVIEWED_JOURNAL"
    CLINICAL_TRIAL_REGISTRY = "CLINICAL_TRIAL_REGISTRY"
    ACADEMIC_MEDICAL_CENTER = "ACADEMIC_MEDICAL_CENTER"
    REFERENCE_BOOK_PUBLISHER = "REFERENCE_BOOK_PUBLISHER"
    OPEN_ACCESS_REPOSITORY = "OPEN_ACCESS_REPOSITORY"
    IRAN_MINISTRY_HEALTH = "IRAN_MINISTRY_HEALTH"
    IRAN_MEDICAL_COUNCIL = "IRAN_MEDICAL_COUNCIL"
    IRAN_MEDICAL_UNIVERSITY = "IRAN_MEDICAL_UNIVERSITY"
    IRAN_REGULATORY_AUTHORITY = "IRAN_REGULATORY_AUTHORITY"
    IRAN_REFERENCE_LAB_AUTHORITY = "IRAN_REFERENCE_LAB_AUTHORITY"
    IRAN_HOSPITAL_AUTHORITY = "IRAN_HOSPITAL_AUTHORITY"
    IRAN_PROVIDER_LICENSING_AUTHORITY = "IRAN_PROVIDER_LICENSING_AUTHORITY"
    SECONDARY_CORROBORATION = "SECONDARY_CORROBORATION"
    COMMERCIAL_DIRECTORY = "COMMERCIAL_DIRECTORY"
    UNVERIFIED = "UNVERIFIED"


class SourceRole(str, Enum):
    """Explicit source roles — listing a role does not imply all roles."""

    CLINICAL_GUIDELINE = "CLINICAL_GUIDELINE"
    SYSTEMATIC_REVIEW = "SYSTEMATIC_REVIEW"
    SCIENTIFIC_LITERATURE = "SCIENTIFIC_LITERATURE"
    CLINICAL_TRIAL = "CLINICAL_TRIAL"
    REGULATORY = "REGULATORY"
    DRUG_INFORMATION = "DRUG_INFORMATION"
    PUBLIC_HEALTH = "PUBLIC_HEALTH"
    MENTAL_HEALTH = "MENTAL_HEALTH"
    PSYCHOLOGY = "PSYCHOLOGY"
    NUTRITION = "NUTRITION"
    EXERCISE = "EXERCISE"
    REHABILITATION = "REHABILITATION"
    LIFESTYLE = "LIFESTYLE"
    SLEEP = "SLEEP"
    PREVENTION = "PREVENTION"
    DAILY_ROUTINE = "DAILY_ROUTINE"
    MEDICAL_REFERENCE_BOOK = "MEDICAL_REFERENCE_BOOK"
    BIOMEDICAL_TERMINOLOGY = "BIOMEDICAL_TERMINOLOGY"
    IRAN_PHYSICIAN_DIRECTORY = "IRAN_PHYSICIAN_DIRECTORY"
    IRAN_HOSPITAL_DIRECTORY = "IRAN_HOSPITAL_DIRECTORY"
    IRAN_CLINIC_DIRECTORY = "IRAN_CLINIC_DIRECTORY"
    IRAN_LABORATORY_DIRECTORY = "IRAN_LABORATORY_DIRECTORY"
    LOCAL_SERVICE_METADATA = "LOCAL_SERVICE_METADATA"


class P0DiseaseRelevance(str, Enum):
    """ALS/MS/Diabetes tagging strength for a source."""

    PRIMARY = "PRIMARY"
    IMPORTANT = "IMPORTANT"
    SUPPORTING = "SUPPORTING"
    NOT_SPECIFIC = "NOT_SPECIFIC"


class BookRightsClass(str, Enum):
    """Reference book rights class (authority ≠ automation permission)."""

    OPEN_AUTOMATION_ALLOWED = "OPEN_AUTOMATION_ALLOWED"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    OPEN_LICENSE_RESTRICTED = "OPEN_LICENSE_RESTRICTED"
    LICENSED = "LICENSED"
    METADATA_ONLY = "METADATA_ONLY"
    FULLTEXT_TDM_PROHIBITED = "FULLTEXT_TDM_PROHIBITED"
    UNKNOWN_RIGHTS = "UNKNOWN_RIGHTS"


class SourceCoverageStatus(str, Enum):
    """Living source-coverage cell status (not 'all world complete')."""

    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    SOURCE_DISCOVERY_REQUIRED = "SOURCE_DISCOVERY_REQUIRED"
    RIGHTS_REVIEW_REQUIRED = "RIGHTS_REVIEW_REQUIRED"
    AUTHORITY_GAP = "AUTHORITY_GAP"
    STALE_SOURCE_SET = "STALE_SOURCE_SET"
    NO_AUTHORITATIVE_SOURCE_FOUND = "NO_AUTHORITATIVE_SOURCE_FOUND"


class RegistryReviewStage(str, Enum):
    """Sub-stage while GSP.registry_state remains UNDER_REVIEW / DISCOVERED."""

    IDENTITY_VERIFIED = "IDENTITY_VERIFIED"
    AUTHORITY_REVIEW = "AUTHORITY_REVIEW"
    RIGHTS_REVIEW = "RIGHTS_REVIEW"
    FORMAT_VERIFIED = "FORMAT_VERIFIED"
    NONE = "NONE"


# ---------------------------------------------------------------------------
# I5-KNOW-02 — Scientific artifacts / claims / universal taxonomy
# ---------------------------------------------------------------------------


class ArtifactType(str, Enum):
    ARTICLE = "ARTICLE"
    SYSTEMATIC_REVIEW = "SYSTEMATIC_REVIEW"
    META_ANALYSIS = "META_ANALYSIS"
    GUIDELINE = "GUIDELINE"
    CONSENSUS_STATEMENT = "CONSENSUS_STATEMENT"
    RCT = "RCT"
    OBSERVATIONAL_STUDY = "OBSERVATIONAL_STUDY"
    CASE_SERIES = "CASE_SERIES"
    CASE_REPORT = "CASE_REPORT"
    BOOK = "BOOK"
    BOOK_CHAPTER = "BOOK_CHAPTER"
    REGULATORY_DOCUMENT = "REGULATORY_DOCUMENT"
    DRUG_LABEL = "DRUG_LABEL"
    CLINICAL_TRIAL_RECORD = "CLINICAL_TRIAL_RECORD"
    DATASET = "DATASET"
    OTHER = "OTHER"


class ArtifactVersionState(str, Enum):
    PUBLISHED = "PUBLISHED"
    UPDATED = "UPDATED"
    CORRECTED = "CORRECTED"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"
    EXPRESSION_OF_CONCERN = "EXPRESSION_OF_CONCERN"
    WITHDRAWN = "WITHDRAWN"


class EvidenceSupportDirection(str, Enum):
    SUPPORTS = "SUPPORTS"
    WEAKLY_SUPPORTS = "WEAKLY_SUPPORTS"
    NEUTRAL = "NEUTRAL"
    CONTRADICTS = "CONTRADICTS"
    REFUTES = "REFUTES"
    INCONCLUSIVE = "INCONCLUSIVE"


class ClinicalConceptType(str, Enum):
    DISEASE = "DISEASE"
    SUBTYPE = "SUBTYPE"
    PHENOTYPE = "PHENOTYPE"
    SYMPTOM = "SYMPTOM"
    SIGN = "SIGN"
    BIOMARKER = "BIOMARKER"
    GENE = "GENE"
    VARIANT = "VARIANT"
    DRUG = "DRUG"
    INTERVENTION = "INTERVENTION"
    PROCEDURE = "PROCEDURE"
    DEVICE = "DEVICE"
    LAB_CLASS = "LAB_CLASS"
    IMAGING_FINDING = "IMAGING_FINDING"
    OUTCOME = "OUTCOME"
    COMPLICATION = "COMPLICATION"
    RISK_FACTOR = "RISK_FACTOR"
    ADVERSE_EVENT = "ADVERSE_EVENT"
    CONTRAINDICATION = "CONTRAINDICATION"
    HEALTHY_POPULATION = "HEALTHY_POPULATION"
    DISEASE_FAMILY = "DISEASE_FAMILY"
    OTHER = "OTHER"


class TerminologySystem(str, Enum):
    ICD11 = "ICD11"
    MESH = "MESH"
    RXNORM = "RXNORM"
    LOINC = "LOINC"
    UMLS = "UMLS"
    SNOMED_CT = "SNOMED_CT"
    ICF = "ICF"
    ICHI = "ICHI"
    SEDI_ROOT = "SEDI_ROOT"
    OTHER = "OTHER"


class SediRootCategory(str, Enum):
    """Sedi navigation/coverage families — map to canonical concepts; not competing ICD."""

    INFECTIOUS_PARASITIC = "INFECTIOUS_PARASITIC"
    NEOPLASMS_CANCER = "NEOPLASMS_CANCER"
    BLOOD_IMMUNE = "BLOOD_IMMUNE"
    ENDOCRINE_NUTRITIONAL_METABOLIC = "ENDOCRINE_NUTRITIONAL_METABOLIC"
    MENTAL_BEHAVIORAL_NEURODEVELOPMENTAL = "MENTAL_BEHAVIORAL_NEURODEVELOPMENTAL"
    SLEEP_WAKE = "SLEEP_WAKE"
    NERVOUS_SYSTEM = "NERVOUS_SYSTEM"
    VISUAL_SYSTEM = "VISUAL_SYSTEM"
    EAR_MASTOID = "EAR_MASTOID"
    CIRCULATORY_CARDIOVASCULAR = "CIRCULATORY_CARDIOVASCULAR"
    RESPIRATORY = "RESPIRATORY"
    DIGESTIVE = "DIGESTIVE"
    SKIN = "SKIN"
    MUSCULOSKELETAL = "MUSCULOSKELETAL"
    GENITOURINARY = "GENITOURINARY"
    SEXUAL_HEALTH = "SEXUAL_HEALTH"
    PREGNANCY_CHILDBIRTH = "PREGNANCY_CHILDBIRTH"
    PERINATAL = "PERINATAL"
    DEVELOPMENTAL_CONGENITAL = "DEVELOPMENTAL_CONGENITAL"
    SYMPTOMS_SIGNS_FINDINGS = "SYMPTOMS_SIGNS_FINDINGS"
    INJURY_POISONING = "INJURY_POISONING"
    RARE_DISEASES = "RARE_DISEASES"
    GENETIC_CONDITIONS = "GENETIC_CONDITIONS"
    MULTISYSTEM = "MULTISYSTEM"
    HEALTHY_POPULATION = "HEALTHY_POPULATION"
    OTHER = "OTHER"


class KnowledgeDimensionCode(str, Enum):
    DEFINITION = "DEFINITION"
    CLASSIFICATION = "CLASSIFICATION"
    EPIDEMIOLOGY = "EPIDEMIOLOGY"
    ETIOLOGY = "ETIOLOGY"
    RISK_FACTORS = "RISK_FACTORS"
    GENETICS = "GENETICS"
    PATHOPHYSIOLOGY = "PATHOPHYSIOLOGY"
    PREVENTION = "PREVENTION"
    SCREENING = "SCREENING"
    DIAGNOSIS = "DIAGNOSIS"
    DIAGNOSTIC_CRITERIA = "DIAGNOSTIC_CRITERIA"
    DIFFERENTIAL_DIAGNOSIS = "DIFFERENTIAL_DIAGNOSIS"
    SIGNS = "SIGNS"
    SYMPTOMS = "SYMPTOMS"
    PHENOTYPES = "PHENOTYPES"
    SUBTYPES = "SUBTYPES"
    STAGING = "STAGING"
    SEVERITY = "SEVERITY"
    BIOMARKERS = "BIOMARKERS"
    LABORATORY = "LABORATORY"
    IMAGING = "IMAGING"
    OTHER_DIAGNOSTICS = "OTHER_DIAGNOSTICS"
    PROGNOSIS = "PROGNOSIS"
    PROGRESSION = "PROGRESSION"
    PHARMACOLOGICAL_TREATMENT = "PHARMACOLOGICAL_TREATMENT"
    NON_PHARMACOLOGICAL_TREATMENT = "NON_PHARMACOLOGICAL_TREATMENT"
    SURGERY = "SURGERY"
    DEVICE = "DEVICE"
    GENE_THERAPY = "GENE_THERAPY"
    CELL_THERAPY = "CELL_THERAPY"
    OTHER_INTERVENTION = "OTHER_INTERVENTION"
    CARE = "CARE"
    SUPPORTIVE_CARE = "SUPPORTIVE_CARE"
    PALLIATIVE_CARE = "PALLIATIVE_CARE"
    REHABILITATION = "REHABILITATION"
    NUTRITION = "NUTRITION"
    DIET = "DIET"
    EXERCISE = "EXERCISE"
    PHYSICAL_ACTIVITY = "PHYSICAL_ACTIVITY"
    LIFESTYLE = "LIFESTYLE"
    SLEEP = "SLEEP"
    MENTAL_HEALTH = "MENTAL_HEALTH"
    SELF_CARE = "SELF_CARE"
    DAILY_ROUTINE = "DAILY_ROUTINE"
    MONITORING = "MONITORING"
    COMPLICATIONS = "COMPLICATIONS"
    ADVERSE_EFFECTS = "ADVERSE_EFFECTS"
    CONTRAINDICATIONS = "CONTRAINDICATIONS"
    INTERACTIONS = "INTERACTIONS"
    QUALITY_OF_LIFE = "QUALITY_OF_LIFE"
    CAREGIVER_SUPPORT = "CAREGIVER_SUPPORT"
    CLINICAL_TRIALS = "CLINICAL_TRIALS"
    EMERGING_RESEARCH = "EMERGING_RESEARCH"
    NEGATIVE_EVIDENCE = "NEGATIVE_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    RETRACTIONS = "RETRACTIONS"
    RESPIRATORY_CARE = "RESPIRATORY_CARE"
    DISEASE_MODIFYING_TREATMENT = "DISEASE_MODIFYING_TREATMENT"


class ClaimClass(str, Enum):
    FACT_DESCRIPTIVE = "FACT_DESCRIPTIVE"
    SCIENTIFIC_FINDING = "SCIENTIFIC_FINDING"
    ASSOCIATION = "ASSOCIATION"
    RISK_RELATION = "RISK_RELATION"
    DIAGNOSTIC_RELATION = "DIAGNOSTIC_RELATION"
    INTERVENTION_EFFECT = "INTERVENTION_EFFECT"
    CARE_RELATION = "CARE_RELATION"
    PREVENTION_RELATION = "PREVENTION_RELATION"
    NUTRITION_RELATION = "NUTRITION_RELATION"
    EXERCISE_RELATION = "EXERCISE_RELATION"
    LIFESTYLE_RELATION = "LIFESTYLE_RELATION"
    ROUTINE_RELATION = "ROUTINE_RELATION"
    SAFETY_RELATION = "SAFETY_RELATION"
    CLINICAL_RECOMMENDATION_REFERENCE = "CLINICAL_RECOMMENDATION_REFERENCE"
    EXPERIMENTAL_HYPOTHESIS = "EXPERIMENTAL_HYPOTHESIS"
    NEGATIVE_FINDING = "NEGATIVE_FINDING"


class CoverageCellState(str, Enum):
    COVERED_CURRENT = "COVERED_CURRENT"
    COVERED_STALE = "COVERED_STALE"
    PARTIAL = "PARTIAL"
    CONFLICTED = "CONFLICTED"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SediCoveragePriority(str, Enum):
    P0_CRITICAL = "P0_CRITICAL"
    P0_HIGH = "P0_HIGH"
    P1 = "P1"
    P2 = "P2"
    STANDARD = "STANDARD"
