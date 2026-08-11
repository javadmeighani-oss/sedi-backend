"""Terminology mapping reassignment integrity (NF10) — never silent remap."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models


class TerminologyRemapConflict(ValueError):
    """Same terminology key cannot silently move to a different target."""

    def __init__(
        self,
        *,
        mapping_kind: str,
        terminology_system: str,
        external_code: str,
        release_version: Optional[str],
        existing_target_id: int,
        incoming_target_id: int,
        event_id: Optional[int] = None,
    ):
        self.mapping_kind = mapping_kind
        self.terminology_system = terminology_system
        self.external_code = external_code
        self.release_version = release_version
        self.existing_target_id = existing_target_id
        self.incoming_target_id = incoming_target_id
        self.event_id = event_id
        super().__init__(
            "TERMINOLOGY_REMAP_CONFLICT:"
            f" kind={mapping_kind} system={terminology_system} code={external_code}"
            f" existing={existing_target_id} incoming={incoming_target_id}"
        )


def record_mapping_conflict(
    db: Session,
    *,
    mapping_kind: str,
    terminology_system: str,
    external_code: str,
    release_version: Optional[str],
    existing_target_id: int,
    incoming_target_id: int,
    existing_mapping_id: Optional[int] = None,
) -> TerminologyRemapConflict:
    row = models.I5TerminologyMappingConflictEvent(
        mapping_kind=mapping_kind,
        terminology_system=terminology_system,
        external_code=external_code,
        release_version=release_version,
        existing_target_id=existing_target_id,
        incoming_target_id=incoming_target_id,
        existing_mapping_id=existing_mapping_id,
        conflict_code="SILENT_REMAP_BLOCKED",
        details="SAME_MAPPING_DIFFERENT_TARGET",
    )
    db.add(row)
    db.flush()
    return TerminologyRemapConflict(
        mapping_kind=mapping_kind,
        terminology_system=terminology_system,
        external_code=external_code,
        release_version=release_version,
        existing_target_id=existing_target_id,
        incoming_target_id=incoming_target_id,
        event_id=row.id,
    )
