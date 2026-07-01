"""Orchestrate curated KB fetch, parse, review, approve (Gate 3G)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate3.content_parser import parse_content
from backend.app.services.gate3.fetch_security import FetchSecurityError
from backend.app.services.gate3.knowledge_ai_review_service import AIReviewResult, KnowledgeAIReviewService
from backend.app.services.gate3.knowledge_base_service import Gate3NotFoundError, _json_dump
from backend.app.services.gate3.knowledge_source_fetcher import KnowledgeSourceFetcher
from backend.app.services.gate3.robots_checker import RobotsBlockedError


PREVIEW_MAX = 50_000


def apply_ai_review_to_run(run: models.KnowledgeIngestionRun, review: AIReviewResult, *, findings_json: str) -> None:
    """Persist AI review outputs on an ingestion run."""
    run.ai_review_status = review.ai_review_status
    run.source_quality_score = review.source_quality_score
    run.parse_quality_score = review.parse_quality_score
    run.evidence_quality_score = review.evidence_quality_score
    run.medical_risk_level = review.medical_risk_level
    run.psychological_risk_level = review.psychological_risk_level
    run.advertising_risk_level = review.advertising_risk_level
    run.recommended_action = review.recommended_action
    run.requires_human_review = review.requires_human_review
    run.auto_approve_allowed = review.auto_approve_allowed
    run.review_findings_json = findings_json


def _chunk_text(content: str, chunk_size: int = 800) -> list[str]:
    content = re.sub(r"\s+", " ", (content or "").strip())
    if not content:
        return []
    chunks = []
    start = 0
    while start < len(content):
        chunks.append(content[start : start + chunk_size].strip())
        start += chunk_size
    return [c for c in chunks if c]


def _run_dict(row: models.KnowledgeIngestionRun) -> dict:
    return {
        "id": row.id,
        "source_id": row.source_id,
        "document_id": row.document_id,
        "status": row.status,
        "run_type": row.run_type,
        "review_status": row.review_status,
        "fetch_url": row.fetch_url,
        "fetched_content_hash": row.fetched_content_hash,
        "ai_review_status": row.ai_review_status,
        "medical_risk_level": row.medical_risk_level,
        "psychological_risk_level": row.psychological_risk_level,
        "recommended_action": row.recommended_action,
        "requires_human_review": row.requires_human_review,
        "auto_approve_allowed": row.auto_approve_allowed,
        "chunks_created": row.chunks_created,
        "extracted_text_preview": (row.extracted_text_preview or "")[:2000],
        "review_findings": json.loads(row.review_findings_json) if row.review_findings_json else [],
        "started_at": row.started_at.isoformat() + "Z" if row.started_at else None,
        "finished_at": row.finished_at.isoformat() + "Z" if row.finished_at else None,
    }


class KnowledgeUpdateService:
    def __init__(self) -> None:
        self.fetcher = KnowledgeSourceFetcher()
        self.reviewer = KnowledgeAIReviewService()

    def fetch_source(
        self,
        db: Session,
        source_id: int,
        *,
        run_by: str = "admin",
        fetch_url: Optional[str] = None,
    ) -> dict:
        src = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.id == source_id).first()
        if not src:
            raise Gate3NotFoundError()
        now = datetime.utcnow()
        run = models.KnowledgeIngestionRun(
            source_id=source_id,
            status="running",
            run_type="url_fetch",
            run_by=run_by,
            review_status="pending_review",
            started_at=now,
            previous_content_hash=src.content_hash,
        )
        db.add(run)
        db.flush()
        try:
            result = self.fetcher.fetch(src, fetch_url)
            run.fetch_url = result.final_url
            run.fetched_at = now
            parsed = parse_content(result.content, result.content_type)
            return self._finalize_staged_content(
                db, src, run, parsed.text, parsed.title, parsed.parser_type, parsed.content_hash,
            )
        except (FetchSecurityError, RobotsBlockedError, ValueError, TypeError) as exc:
            run.status = "failed"
            run.error_message = str(exc) if not isinstance(exc, TypeError) else "invalid_fetch_response"
            run.review_status = "rejected"
            run.finished_at = datetime.utcnow()
            db.commit()
            db.refresh(run)
            if isinstance(exc, TypeError):
                raise FetchSecurityError("invalid_fetch_response") from exc
            raise

    def stage_manual_content(
        self,
        db: Session,
        source_id: int,
        content: str,
        *,
        title: str,
        category: str,
        run_by: str = "admin",
        chunk_size: int = 800,
    ) -> dict:
        src = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.id == source_id).first()
        if not src:
            raise Gate3NotFoundError()
        now = datetime.utcnow()
        parsed = parse_content(content.encode("utf-8"), "text/plain", title_hint=title, min_text_length=1)
        run = models.KnowledgeIngestionRun(
            source_id=source_id,
            status="running",
            run_type="manual_upload",
            run_by=run_by,
            review_status="pending_review",
            started_at=now,
            previous_content_hash=src.content_hash,
        )
        db.add(run)
        db.flush()
        outcome = self._finalize_staged_content(
            db, src, run, parsed.text, title or parsed.title, parsed.parser_type, parsed.content_hash,
            category=category,
            chunk_size=chunk_size,
        )
        return outcome

    def _finalize_staged_content(
        self,
        db: Session,
        src: models.KnowledgeSource,
        run: models.KnowledgeIngestionRun,
        text: str,
        title: str,
        parser_type: str,
        content_hash: str,
        *,
        category: Optional[str] = None,
        chunk_size: int = 800,
    ) -> dict:
        now = datetime.utcnow()
        run.fetched_content_hash = content_hash
        run.parser_type = parser_type
        run.extracted_text_preview = text[:PREVIEW_MAX]
        run.source_snapshot_json = _json_dump({"title": title, "category": category or src.category})

        if src.content_hash and src.content_hash == content_hash:
            run.status = "success"
            run.review_status = "no_change"
            run.finished_at = now
            src.last_fetched_at = now
            db.commit()
            db.refresh(run)
            return _run_dict(run)

        review = self.reviewer.review(src, text, parser_type=parser_type, title=title)
        apply_ai_review_to_run(run, review, findings_json=self.reviewer.findings_json(review))

        src.last_fetched_at = now
        src.last_changed_at = now
        src.content_hash = content_hash

        if review.recommended_action == "reject":
            run.status = "failed"
            run.review_status = "rejected"
            run.finished_at = now
            db.commit()
            db.refresh(run)
            return _run_dict(run)

        if review.recommended_action == "auto_approve":
            return self._activate_run(db, src, run, text, title, category or src.category, chunk_size, approved_by="auto")

        run.status = "success"
        run.review_status = "pending_review"
        run.finished_at = now
        db.commit()
        db.refresh(run)
        return _run_dict(run)

    def approve_run(self, db: Session, run_id: int, *, approved_by: str = "admin") -> dict:
        run = db.query(models.KnowledgeIngestionRun).filter(models.KnowledgeIngestionRun.id == run_id).first()
        if not run:
            raise Gate3NotFoundError()
        if run.review_status not in ("pending_review",):
            raise ValueError("run_not_pending_review")
        src = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.id == run.source_id).first()
        if not src:
            raise Gate3NotFoundError()
        text = run.extracted_text_preview or ""
        snap = json.loads(run.source_snapshot_json) if run.source_snapshot_json else {}
        return self._activate_run(
            db, src, run, text, snap.get("title", "Approved document"),
            snap.get("category", src.category), 800, approved_by=approved_by,
        )

    def reject_run(self, db: Session, run_id: int, *, reason: str, rejected_by: str = "admin") -> dict:
        run = db.query(models.KnowledgeIngestionRun).filter(models.KnowledgeIngestionRun.id == run_id).first()
        if not run:
            raise Gate3NotFoundError()
        run.review_status = "rejected"
        run.rejected_reason = reason
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        run.approved_by = rejected_by
        db.commit()
        db.refresh(run)
        return _run_dict(run)

    def _activate_run(
        self,
        db: Session,
        src: models.KnowledgeSource,
        run: models.KnowledgeIngestionRun,
        text: str,
        title: str,
        category: str,
        chunk_size: int,
        *,
        approved_by: str,
    ) -> dict:
        now = datetime.utcnow()
        doc = models.KnowledgeDocument(
            source_id=src.id,
            title=title[:512],
            category=category,
            locale=src.locale,
            status="active",
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(doc)
        db.flush()
        parts = _chunk_text(text, chunk_size)
        created = 0
        for idx, part in enumerate(parts):
            label = f"{src.name}: {doc.title}"[:256]
            chunk = models.KnowledgeChunk(
                document_id=doc.id,
                chunk_index=idx,
                content=part,
                citation_label=label,
                token_count=len(part.split()),
                metadata_json=_json_dump({"source_slug": src.slug, "category": doc.category, "ingestion_run_id": run.id}),
                created_at=now,
            )
            db.add(chunk)
            created += 1

        if src.ingestion_status == "draft":
            src.ingestion_status = "active"
            src.last_checked_at = now
        elif run.run_type in ("url_fetch", "scheduled_fetch"):
            src.last_checked_at = now
        src.last_approved_at = now
        src.updated_at = now

        run.document_id = doc.id
        run.chunks_created = created
        run.review_status = "auto_approved" if approved_by == "auto" else "approved"
        run.approved_at = now
        run.approved_by = approved_by
        run.status = "success"
        run.finished_at = now
        db.commit()
        db.refresh(run)
        return _run_dict(run)

    def list_runs(self, db: Session, *, source_id: Optional[int] = None, review_status: Optional[str] = None) -> list[dict]:
        q = db.query(models.KnowledgeIngestionRun).order_by(models.KnowledgeIngestionRun.id.desc())
        if source_id is not None:
            q = q.filter(models.KnowledgeIngestionRun.source_id == source_id)
        if review_status:
            q = q.filter(models.KnowledgeIngestionRun.review_status == review_status)
        return [_run_dict(r) for r in q.limit(100).all()]

    def get_run(self, db: Session, run_id: int) -> dict:
        run = db.query(models.KnowledgeIngestionRun).filter(models.KnowledgeIngestionRun.id == run_id).first()
        if not run:
            raise Gate3NotFoundError()
        return _run_dict(run)
