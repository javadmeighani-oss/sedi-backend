"""I5-KNOW-01 Reference Book Registry foundation."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import BookRightsClass, RightDecision


def upsert_reference_book(
    db: Session,
    *,
    book_key: str,
    title: str,
    rights_class: str,
    publisher: Optional[str] = None,
    publisher_source_profile_id: Optional[int] = None,
    authors_editors: Optional[str] = None,
    isbn: Optional[str] = None,
    specialty: Optional[str] = None,
    disease_coverage: Optional[str] = None,
    medical_authority_note: Optional[str] = None,
    automation_tdm_permission: str = RightDecision.UNKNOWN.value,
    fulltext_automation_permission: str = RightDecision.DENIED.value,
    retention_policy: Optional[str] = None,
    canonical_access_route: Optional[str] = None,
) -> models.I5ReferenceBook:
    BookRightsClass(rights_class)
    RightDecision(automation_tdm_permission)
    RightDecision(fulltext_automation_permission)

    row = db.query(models.I5ReferenceBook).filter_by(book_key=book_key).first()
    if row is None:
        row = models.I5ReferenceBook(book_key=book_key, title=title, rights_class=rights_class)
        db.add(row)
    row.title = title
    row.rights_class = rights_class
    row.publisher = publisher
    row.publisher_source_profile_id = publisher_source_profile_id
    row.authors_editors = authors_editors
    row.isbn = isbn
    row.specialty = specialty
    row.disease_coverage = disease_coverage
    row.medical_authority_note = medical_authority_note
    row.automation_tdm_permission = automation_tdm_permission
    row.fulltext_automation_permission = fulltext_automation_permission
    row.retention_policy = retention_policy
    row.canonical_access_route = canonical_access_route
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def add_edition(
    db: Session,
    *,
    book_id: int,
    edition_label: str,
    publication_year: Optional[int] = None,
    volume: Optional[str] = None,
    is_current: bool = False,
    access_route: Optional[str] = None,
    superseded_by_edition_id: Optional[int] = None,
) -> models.I5ReferenceBookEdition:
    if is_current:
        db.query(models.I5ReferenceBookEdition).filter_by(book_id=book_id, is_current=True).update(
            {"is_current": False}
        )
    existing = (
        db.query(models.I5ReferenceBookEdition)
        .filter_by(book_id=book_id, edition_label=edition_label)
        .first()
    )
    if existing:
        existing.publication_year = publication_year
        existing.volume = volume
        existing.is_current = is_current
        existing.access_route = access_route
        existing.superseded_by_edition_id = superseded_by_edition_id
        db.flush()
        return existing
    ed = models.I5ReferenceBookEdition(
        book_id=book_id,
        edition_label=edition_label,
        publication_year=publication_year,
        volume=volume,
        is_current=is_current,
        access_route=access_route,
        superseded_by_edition_id=superseded_by_edition_id,
    )
    db.add(ed)
    db.flush()
    return ed


def list_books(db: Session) -> List[models.I5ReferenceBook]:
    return db.query(models.I5ReferenceBook).order_by(models.I5ReferenceBook.book_key).all()


def assert_authority_does_not_imply_automation(book: models.I5ReferenceBook) -> None:
    """High medical authority may remain fulltext-blocked."""
    if book.fulltext_automation_permission == RightDecision.ALLOWED.value:
        return
    if (book.medical_authority_note or "").upper().find("HIGH") >= 0:
        if book.fulltext_automation_permission not in {
            RightDecision.DENIED.value,
            RightDecision.UNKNOWN.value,
            RightDecision.REVIEW_REQUIRED.value,
            RightDecision.CONDITIONAL.value,
        }:
            raise AssertionError("INVALID_FULLTEXT_STATE")
