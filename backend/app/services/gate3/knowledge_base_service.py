"""Gate 3 curated knowledge base admin service."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.gate3 import (
    KnowledgeDocumentCreateIn,
    KnowledgeDocumentUpdateIn,
    KnowledgeIngestIn,
    KnowledgeSourceCreateIn,
    KnowledgeSourceUpdateIn,
)


class Gate3NotFoundError(Exception):
    pass


def _json_load(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _json_dump(val: Any) -> Optional[str]:
    if val is None:
        return None
    return json.dumps(val, ensure_ascii=False)


def _source_dict(row: models.KnowledgeSource) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "category": row.category,
        "trust_level": row.trust_level,
        "source_url": row.source_url,
        "locale": row.locale,
        "last_checked_at": row.last_checked_at.isoformat() + "Z" if row.last_checked_at else None,
        "freshness_policy_days": row.freshness_policy_days,
        "ingestion_status": row.ingestion_status,
        "license_notes": row.license_notes,
        "metadata": _json_load(row.metadata_json),
        "created_at": row.created_at.isoformat() + "Z",
        "updated_at": row.updated_at.isoformat() + "Z",
    }


def _document_dict(row: models.KnowledgeDocument) -> dict:
    return {
        "id": row.id,
        "source_id": row.source_id,
        "title": row.title,
        "summary": row.summary,
        "category": row.category,
        "locale": row.locale,
        "region": row.region,
        "city": row.city,
        "specialty": row.specialty,
        "tags": _json_load(row.tags_json) if row.tags_json else [],
        "status": row.status,
        "published_at": row.published_at.isoformat() + "Z" if row.published_at else None,
        "metadata": _json_load(row.metadata_json),
        "created_at": row.created_at.isoformat() + "Z",
        "updated_at": row.updated_at.isoformat() + "Z",
    }


def list_sources(db: Session) -> List[dict]:
    rows = db.query(models.KnowledgeSource).order_by(models.KnowledgeSource.id.desc()).all()
    return [_source_dict(r) for r in rows]


def create_source(db: Session, body: KnowledgeSourceCreateIn) -> dict:
    now = datetime.utcnow()
    row = models.KnowledgeSource(
        slug=body.slug.strip(),
        name=body.name.strip(),
        category=body.category,
        trust_level=body.trust_level,
        source_url=body.source_url,
        locale=body.locale,
        last_checked_at=body.last_checked_at,
        freshness_policy_days=body.freshness_policy_days,
        ingestion_status=body.ingestion_status,
        license_notes=body.license_notes,
        metadata_json=_json_dump(body.metadata),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _source_dict(row)


def update_source(db: Session, source_id: int, body: KnowledgeSourceUpdateIn) -> dict:
    row = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.id == source_id).first()
    if not row:
        raise Gate3NotFoundError()
    for field, attr in [
        ("name", "name"), ("category", "category"), ("trust_level", "trust_level"),
        ("source_url", "source_url"), ("locale", "locale"), ("last_checked_at", "last_checked_at"),
        ("freshness_policy_days", "freshness_policy_days"), ("ingestion_status", "ingestion_status"),
        ("license_notes", "license_notes"),
    ]:
        val = getattr(body, field)
        if val is not None:
            setattr(row, attr, val)
    if body.metadata is not None:
        row.metadata_json = _json_dump(body.metadata)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _source_dict(row)


def list_documents(db: Session, source_id: Optional[int] = None) -> List[dict]:
    q = db.query(models.KnowledgeDocument)
    if source_id is not None:
        q = q.filter(models.KnowledgeDocument.source_id == source_id)
    rows = q.order_by(models.KnowledgeDocument.id.desc()).all()
    return [_document_dict(r) for r in rows]


def create_document(db: Session, body: KnowledgeDocumentCreateIn) -> dict:
    src = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.id == body.source_id).first()
    if not src:
        raise Gate3NotFoundError()
    now = datetime.utcnow()
    row = models.KnowledgeDocument(
        source_id=body.source_id,
        title=body.title.strip(),
        summary=body.summary,
        category=body.category,
        locale=body.locale,
        region=body.region,
        city=body.city,
        specialty=body.specialty,
        tags_json=_json_dump(body.tags or []),
        status=body.status,
        published_at=body.published_at,
        metadata_json=_json_dump(body.metadata),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _document_dict(row)


def update_document(db: Session, document_id: int, body: KnowledgeDocumentUpdateIn) -> dict:
    row = db.query(models.KnowledgeDocument).filter(models.KnowledgeDocument.id == document_id).first()
    if not row:
        raise Gate3NotFoundError()
    for field in ("title", "summary", "category", "locale", "region", "city", "specialty", "status", "published_at"):
        val = getattr(body, field)
        if val is not None:
            setattr(row, field, val.strip() if field == "title" and isinstance(val, str) else val)
    if body.tags is not None:
        row.tags_json = _json_dump(body.tags)
    if body.metadata is not None:
        row.metadata_json = _json_dump(body.metadata)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _document_dict(row)


def _chunk_text(content: str, chunk_size: int) -> List[str]:
    content = re.sub(r"\s+", " ", (content or "").strip())
    if not content:
        return []
    chunks = []
    start = 0
    while start < len(content):
        chunks.append(content[start : start + chunk_size].strip())
        start += chunk_size
    return [c for c in chunks if c]


def ingest_content(db: Session, body: KnowledgeIngestIn, run_by: str = "admin") -> dict:
    src = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.id == body.source_id).first()
    if not src:
        raise Gate3NotFoundError()
    now = datetime.utcnow()
    run = models.KnowledgeIngestionRun(
        source_id=body.source_id,
        status="running",
        run_by=run_by,
        started_at=now,
    )
    db.add(run)
    db.flush()

    doc = None
    if body.document_id:
        doc = db.query(models.KnowledgeDocument).filter(models.KnowledgeDocument.id == body.document_id).first()
    if doc is None:
        doc = models.KnowledgeDocument(
            source_id=body.source_id,
            title=(body.title or "Ingested document")[:512],
            category=body.category,
            locale=body.locale,
            region=body.region,
            city=body.city,
            specialty=body.specialty,
            status="active",
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(doc)
        db.flush()
    run.document_id = doc.id

    parts = _chunk_text(body.content, body.chunk_size)
    created = 0
    for idx, part in enumerate(parts):
        label = f"{src.name}: {doc.title}"[:256]
        chunk = models.KnowledgeChunk(
            document_id=doc.id,
            chunk_index=idx,
            content=part,
            citation_label=label,
            token_count=len(part.split()),
            metadata_json=_json_dump({"source_slug": src.slug, "category": doc.category}),
            created_at=now,
        )
        db.add(chunk)
        created += 1

    src.updated_at = now
    # Freshness verification is explicit admin responsibility (PATCH source last_checked_at).
    # Ingest must not refresh stale sources; only first draft->active promotion sets checked time.
    if src.ingestion_status == "draft":
        src.last_checked_at = now
        src.ingestion_status = "active"
    run.chunks_created = created
    run.status = "success"
    run.finished_at = datetime.utcnow()
    db.commit()
    return {
        "ingestion_run_id": run.id,
        "document_id": doc.id,
        "chunks_created": created,
        "status": run.status,
    }
