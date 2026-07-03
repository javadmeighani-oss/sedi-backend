"""Gate 5-C/D — Orchestration for raw signal batch technical feature extraction."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app.models import RawSignalBatch, RawSignalBatchFeature
from backend.app.services.gate5.raw_signal_feature_compute import (
    RawSignalFeatureComputeError,
    compute_raw_signal_features,
)
from backend.app.services.gate5.raw_signal_ingestion import STORAGE_BACKEND_POSTGRES_JSON
from backend.app.services.gate5.raw_signal_processing_flags import raw_signal_processing_max_limit

logger = logging.getLogger(__name__)

DEFAULT_PROCESSING_VERSION = "gate5c_v1"
PERMANENT_FAILURE_CODES = frozenset({"OBJECT_STORAGE_NOT_SUPPORTED"})
CANDIDATE_IDS_LOG_LIMIT = 20

STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


class RawSignalFeatureExtractionError(Exception):
    """Controlled extraction error."""

    def __init__(self, code: str, message: str, status_code: int = 404) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class ProcessBatchResult:
    batch_id: int
    feature_id: int
    processing_status: str
    processing_version: str
    skipped: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class ProcessPendingSummary:
    processed: int
    completed: int
    failed: int
    skipped: int
    processing_version: str
    effective_limit: int
    dry_run: bool = False
    duration_ms: int = 0
    candidate_batch_ids: List[int] = field(default_factory=list)
    source: str = "manual_ops"


@dataclass
class RawSignalBatchStatus:
    batch_id: int
    has_batch: bool
    processing_version: str
    feature_id: Optional[int] = None
    processing_status: Optional[str] = None
    error_code: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


def _now() -> datetime:
    return datetime.utcnow()


def _resolve_effective_limit(request_limit: int, max_limit: Optional[int] = None) -> int:
    effective = max_limit if max_limit is not None else raw_signal_processing_max_limit()
    if request_limit > effective:
        raise RawSignalFeatureExtractionError(
            "LIMIT_EXCEEDS_MAX",
            f"requested limit {request_limit} exceeds effective max {effective}",
            status_code=400,
        )
    return request_limit


def _query_pending_batches(
    db: Session,
    *,
    processing_version: str,
    limit: int,
) -> List[RawSignalBatch]:
    return (
        db.query(RawSignalBatch)
        .outerjoin(
            RawSignalBatchFeature,
            (RawSignalBatchFeature.raw_signal_batch_id == RawSignalBatch.id)
            & (RawSignalBatchFeature.processing_version == processing_version),
        )
        .filter(RawSignalBatchFeature.id.is_(None))
        .order_by(RawSignalBatch.id.asc())
        .limit(limit)
        .all()
    )


def _get_existing_feature(
    db: Session,
    *,
    batch_id: int,
    processing_version: str,
) -> Optional[RawSignalBatchFeature]:
    return (
        db.query(RawSignalBatchFeature)
        .filter(
            RawSignalBatchFeature.raw_signal_batch_id == batch_id,
            RawSignalBatchFeature.processing_version == processing_version,
        )
        .first()
    )


def _create_feature_row(
    db: Session,
    *,
    batch: RawSignalBatch,
    processing_version: str,
    processing_status: str,
    now: datetime,
    features_json=None,
    quality_json=None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    processed_at: Optional[datetime] = None,
) -> RawSignalBatchFeature:
    row = RawSignalBatchFeature(
        raw_signal_batch_id=batch.id,
        user_id=batch.user_id,
        hub_device_id=batch.hub_device_id,
        sensor_id=batch.sensor_id,
        signal_type=batch.signal_type,
        processing_version=processing_version,
        processing_status=processing_status,
        features_json=features_json,
        quality_json=quality_json,
        error_code=error_code,
        error_message=error_message,
        processed_at=processed_at,
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _finalize_failed(
    db: Session,
    row: RawSignalBatchFeature,
    *,
    error_code: str,
    error_message: str,
    now: datetime,
) -> RawSignalBatchFeature:
    row.processing_status = STATUS_FAILED
    row.error_code = error_code
    row.error_message = error_message
    row.processed_at = now
    row.features_json = None
    row.quality_json = None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _to_result(row: RawSignalBatchFeature, *, skipped: bool = False) -> ProcessBatchResult:
    return ProcessBatchResult(
        batch_id=row.raw_signal_batch_id,
        feature_id=row.id,
        processing_status=row.processing_status,
        processing_version=row.processing_version,
        skipped=skipped,
        error_code=row.error_code,
        error_message=row.error_message,
    )


def get_raw_signal_batch_processing_status(
    db: Session,
    batch_id: int,
    *,
    processing_version: str = DEFAULT_PROCESSING_VERSION,
) -> RawSignalBatchStatus:
    """Metadata-only status for one batch; no samples or feature payloads."""
    batch = db.query(RawSignalBatch).filter(RawSignalBatch.id == batch_id).first()
    if batch is None:
        return RawSignalBatchStatus(
            batch_id=batch_id,
            has_batch=False,
            processing_version=processing_version,
        )

    feature = _get_existing_feature(db, batch_id=batch_id, processing_version=processing_version)
    if feature is None:
        return RawSignalBatchStatus(
            batch_id=batch_id,
            has_batch=True,
            processing_version=processing_version,
        )

    return RawSignalBatchStatus(
        batch_id=batch_id,
        has_batch=True,
        processing_version=processing_version,
        feature_id=feature.id,
        processing_status=feature.processing_status,
        error_code=feature.error_code,
        processed_at=feature.processed_at,
        created_at=feature.created_at,
    )


def process_raw_signal_batch(
    db: Session,
    batch_id: int,
    *,
    processing_version: str = DEFAULT_PROCESSING_VERSION,
    force: bool = False,
    allow_retry: bool = False,
    source: str = "manual_ops",
) -> ProcessBatchResult:
    """
    Extract technical features for one raw signal batch.
    Idempotent for completed rows at the same processing_version.
    Failed rows are skipped unless allow_retry=True (except permanent failures).
    """
    if force:
        raise RawSignalFeatureExtractionError(
            "FORCE_NOT_SUPPORTED",
            "force reprocessing is not supported in Gate 5.3",
            status_code=400,
        )

    batch = db.query(RawSignalBatch).filter(RawSignalBatch.id == batch_id).first()
    if batch is None:
        raise RawSignalFeatureExtractionError(
            "BATCH_NOT_FOUND",
            f"raw signal batch {batch_id} not found",
            status_code=404,
        )

    now = _now()
    existing = _get_existing_feature(db, batch_id=batch_id, processing_version=processing_version)
    if existing is not None and existing.processing_status == STATUS_COMPLETED:
        logger.info(
            "[RAW_SIGNAL_FEATURE] SKIP source=%s batch_id=%s version=%s feature_id=%s",
            source,
            batch_id,
            processing_version,
            existing.id,
        )
        return _to_result(existing, skipped=True)

    if existing is not None and existing.processing_status == STATUS_FAILED:
        if existing.error_code in PERMANENT_FAILURE_CODES or not allow_retry:
            logger.info(
                "[RAW_SIGNAL_FEATURE] SKIP source=%s batch_id=%s version=%s status=failed "
                "allow_retry=%s error=%s",
                source,
                batch_id,
                processing_version,
                allow_retry,
                existing.error_code,
            )
            return _to_result(existing, skipped=True)

    if batch.storage_backend != STORAGE_BACKEND_POSTGRES_JSON:
        if existing is not None and existing.processing_status == STATUS_FAILED:
            if existing.error_code in PERMANENT_FAILURE_CODES:
                return _to_result(existing, skipped=True)
        row = existing
        if row is None:
            row = _create_feature_row(
                db,
                batch=batch,
                processing_version=processing_version,
                processing_status=STATUS_PROCESSING,
                now=now,
            )
        row = _finalize_failed(
            db,
            row,
            error_code="OBJECT_STORAGE_NOT_SUPPORTED",
            error_message=f"storage backend {batch.storage_backend!r} is not supported in Gate 5.3",
            now=now,
        )
        logger.info(
            "[RAW_SIGNAL_FEATURE] FAILED source=%s batch_id=%s version=%s error=%s",
            source,
            batch_id,
            processing_version,
            row.error_code,
        )
        return _to_result(row)

    row = existing
    if row is None:
        row = _create_feature_row(
            db,
            batch=batch,
            processing_version=processing_version,
            processing_status=STATUS_PROCESSING,
            now=now,
        )
    else:
        row.processing_status = STATUS_PROCESSING
        row.error_code = None
        row.error_message = None
        row.processed_at = None
        db.add(row)
        db.commit()
        db.refresh(row)

    try:
        if not isinstance(batch.samples_json, list):
            raise RawSignalFeatureComputeError("SAMPLES_INVALID", "samples_json must be a list")

        computed = compute_raw_signal_features(
            samples=batch.samples_json,
            started_at=batch.started_at,
            ended_at=batch.ended_at,
            declared_sample_rate_hz=batch.sample_rate_hz,
            declared_sample_count=batch.sample_count,
            metadata=batch.metadata_json,
            quality_metadata=batch.quality_metadata_json,
            storage_backend=batch.storage_backend,
            processing_version=processing_version,
        )
    except RawSignalFeatureComputeError as exc:
        row = _finalize_failed(
            db,
            row,
            error_code=exc.code,
            error_message=exc.message,
            now=_now(),
        )
        logger.info(
            "[RAW_SIGNAL_FEATURE] FAILED source=%s batch_id=%s version=%s error=%s",
            source,
            batch_id,
            processing_version,
            exc.code,
        )
        return _to_result(row)

    row.processing_status = STATUS_COMPLETED
    row.features_json = computed.features
    row.quality_json = computed.quality
    row.error_code = None
    row.error_message = None
    row.processed_at = _now()
    db.add(row)
    db.commit()
    db.refresh(row)

    logger.info(
        "[RAW_SIGNAL_FEATURE] COMPLETED source=%s batch_id=%s version=%s feature_id=%s",
        source,
        batch_id,
        processing_version,
        row.id,
    )
    return _to_result(row)


def process_pending_raw_signal_batches(
    db: Session,
    *,
    limit: int = 10,
    processing_version: str = DEFAULT_PROCESSING_VERSION,
    dry_run: bool = False,
    source: str = "manual_ops",
    max_limit: Optional[int] = None,
) -> ProcessPendingSummary:
    """
    Process batches that do not yet have a feature row for the version.
    Never retries failed batches (they already have a feature row).
    """
    t0 = time.perf_counter()
    effective_limit = _resolve_effective_limit(limit, max_limit=max_limit)
    pending_batches = _query_pending_batches(
        db,
        processing_version=processing_version,
        limit=effective_limit,
    )
    candidate_ids = [b.id for b in pending_batches]

    if dry_run:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "[RAW_SIGNAL_FEATURE] DRY_RUN source=%s dry_run=True limit=%s effective_limit=%s "
            "version=%s candidates=%s candidate_ids=%s duration_ms=%s",
            source,
            limit,
            effective_limit,
            processing_version,
            len(candidate_ids),
            candidate_ids[:CANDIDATE_IDS_LOG_LIMIT],
            duration_ms,
        )
        return ProcessPendingSummary(
            processed=0,
            completed=0,
            failed=0,
            skipped=0,
            processing_version=processing_version,
            effective_limit=effective_limit,
            dry_run=True,
            duration_ms=duration_ms,
            candidate_batch_ids=candidate_ids,
            source=source,
        )

    processed = 0
    completed = 0
    failed = 0
    skipped = 0
    processed_ids: List[int] = []

    for batch in pending_batches:
        result = process_raw_signal_batch(
            db,
            batch.id,
            processing_version=processing_version,
            allow_retry=False,
            source=source,
        )
        processed += 1
        processed_ids.append(batch.id)
        if result.skipped:
            skipped += 1
        elif result.processing_status == STATUS_COMPLETED:
            completed += 1
        elif result.processing_status == STATUS_FAILED:
            failed += 1

    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "[RAW_SIGNAL_FEATURE] PENDING source=%s dry_run=False limit=%s effective_limit=%s "
        "version=%s processed=%s completed=%s failed=%s skipped=%s "
        "batch_ids=%s duration_ms=%s",
        source,
        limit,
        effective_limit,
        processing_version,
        processed,
        completed,
        failed,
        skipped,
        processed_ids[:CANDIDATE_IDS_LOG_LIMIT],
        duration_ms,
    )

    return ProcessPendingSummary(
        processed=processed,
        completed=completed,
        failed=failed,
        skipped=skipped,
        processing_version=processing_version,
        effective_limit=effective_limit,
        dry_run=False,
        duration_ms=duration_ms,
        candidate_batch_ids=processed_ids,
        source=source,
    )
