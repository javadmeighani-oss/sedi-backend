"""Merge competing fact stacks into canonical user_memory_facts (§270.R)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models


@dataclass
class MergeCounts:
    source_rows_expected: int = 0
    target_rows_before: int = 0
    mapped_rows: int = 0
    conflict_rows: int = 0
    unmapped_rows: int = 0
    target_rows_after: int = 0
    details: list[str] = field(default_factory=list)

    @property
    def unexplained_data_loss(self) -> int:
        accounted = self.mapped_rows + self.conflict_rows + self.unmapped_rows
        missing = self.source_rows_expected - accounted
        return max(0, missing)


def _domain_key_effective(
    user_id: int,
    domain: str,
    key: str,
    effective: Optional[datetime],
) -> tuple:
    return (user_id, domain, key, effective.isoformat() if effective else None)


def _as_json_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        # Preserve already-serialized JSON strings.
        try:
            json.loads(value)
            return value
        except Exception:
            return json.dumps(value)
    return json.dumps(value)


def merge_legacy_facts_into_user_memory_facts(db: Session) -> MergeCounts:
    """Backfill user_facts / kc_user_facts / user_profile_facts → user_memory_facts.

    Dedupe by (user, domain, key, effective). Conflict → lower confidence becomes superseded.
    Never silently discard conflicting historical facts.
    """
    counts = MergeCounts()
    counts.target_rows_before = db.query(models.UserMemoryFact).count()

    sources: list[tuple[str, list[Any]]] = []
    user_facts = db.query(models.UserFact).all()
    kc_facts = db.query(models.KcUserFact).all()
    profile_facts = db.query(models.UserProfileFact).all()
    sources.append(("user_facts", user_facts))
    sources.append(("kc_user_facts", kc_facts))
    sources.append(("user_profile_facts", profile_facts))
    counts.source_rows_expected = len(user_facts) + len(kc_facts) + len(profile_facts)

    index: dict[tuple, models.UserMemoryFact] = {}
    for existing in db.query(models.UserMemoryFact).all():
        index[_domain_key_effective(existing.user_id, existing.domain, existing.key, existing.valid_from)] = existing

    for source_name, rows in sources:
        for row in rows:
            try:
                if source_name == "user_facts":
                    domain = "legacy_user_facts"
                    key = row.key
                    value_json = _as_json_text(row.value_json)
                    confidence = float(row.confidence if row.confidence is not None else 0.7)
                    source = row.source or "manual"
                    effective = None
                    provenance_class = "SYSTEM_DERIVED"
                elif source_name == "kc_user_facts":
                    domain = "kc"
                    key = row.fact_type
                    value_json = _as_json_text(row.value_json)
                    confidence = 0.85
                    source = "manual"
                    effective = row.valid_from
                    provenance_class = "USER_CONFIRMED"
                else:
                    domain = "profile"
                    key = row.fact_type
                    value_json = _as_json_text(row.value_json)
                    confidence = float(row.confidence if row.confidence is not None else 0.7)
                    source = row.source or "manual"
                    effective = row.valid_from
                    provenance_class = "USER_STATED"

                dk = _domain_key_effective(row.user_id, domain, key, effective)
                provenance = f"db03_merge:{source_name}:{row.id}"

                if dk in index:
                    existing = index[dk]
                    if existing.value_json == value_json:
                        counts.mapped_rows += 1
                        continue
                    # Conflict: keep higher confidence active; supersede lower.
                    counts.conflict_rows += 1
                    if confidence > float(existing.confidence or 0):
                        existing.fact_status = "superseded"
                        existing.soft_invalidated_at = datetime.utcnow()
                        existing.invalidation_reason = f"superseded_by_merge:{provenance}"
                        new_fact = models.UserMemoryFact(
                            user_id=row.user_id,
                            domain=domain,
                            key=key,
                            value_json=value_json,
                            confidence=confidence,
                            source=source,
                            provenance=provenance,
                            provenance_class=provenance_class,
                            valid_from=effective,
                            supersedes_fact_id=existing.id,
                            fact_status="active",
                        )
                        db.add(new_fact)
                        db.flush()
                        index[dk] = new_fact
                    else:
                        new_fact = models.UserMemoryFact(
                            user_id=row.user_id,
                            domain=domain,
                            key=key,
                            value_json=value_json,
                            confidence=confidence,
                            source=source,
                            provenance=provenance,
                            provenance_class=provenance_class,
                            valid_from=effective,
                            fact_status="superseded",
                            soft_invalidated_at=datetime.utcnow(),
                            invalidation_reason=f"lower_confidence_vs:{existing.id}",
                            supersedes_fact_id=None,
                        )
                        db.add(new_fact)
                        db.flush()
                    continue

                new_fact = models.UserMemoryFact(
                    user_id=row.user_id,
                    domain=domain,
                    key=key,
                    value_json=value_json,
                    confidence=confidence,
                    source=source,
                    provenance=provenance,
                    provenance_class=provenance_class,
                    valid_from=effective,
                    fact_status="active",
                )
                db.add(new_fact)
                db.flush()
                index[dk] = new_fact
                counts.mapped_rows += 1
            except Exception as exc:  # noqa: BLE001 — retain evidence, do not fake merge
                counts.unmapped_rows += 1
                counts.details.append(f"{source_name}:{getattr(row, 'id', '?')}:{type(exc).__name__}")

    db.flush()
    counts.target_rows_after = db.query(models.UserMemoryFact).count()
    return counts
