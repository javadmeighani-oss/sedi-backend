"""B4A — canonical_unit_id+v1 idempotency when dedupe_key drifts (same content)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

import pytest

from backend.app import models
from backend.app.services.i5.governed_weekly_runtime import (
    GovernedWeeklyRuntimeError,
    execute_governed_persistence,
)


def _bind_value(expr: Any) -> Any:
    right = getattr(expr, "right", None)
    if right is None:
        return None
    if hasattr(right, "value"):
        return right.value
    return right


def _col_key(expr: Any) -> str:
    left = getattr(expr, "left", None)
    if left is None:
        return ""
    return str(getattr(left, "key", None) or getattr(left, "name", None) or "")


class _FakeQuery:
    def __init__(self, session: "_FakeSession", model: Any) -> None:
        self._session = session
        self._model = model
        self._filters: dict[str, Any] = {}

    def filter(self, *exprs: Any) -> "_FakeQuery":
        for expr in exprs:
            self._filters[_col_key(expr)] = _bind_value(expr)
        return self

    def one_or_none(self) -> Optional[Any]:
        if self._model is not models.KnowledgeUnit:
            return None
        if "deduplication_key" in self._filters and "canonical_unit_id" not in self._filters:
            return self._session.by_dedupe.get(self._filters["deduplication_key"])
        if "canonical_unit_id" in self._filters:
            key = (
                self._filters["canonical_unit_id"],
                self._filters.get("immutable_version_id", "v1"),
            )
            return self._session.by_cuid_v1.get(key)
        return None


class _FakeSession:
    def __init__(
        self,
        *,
        by_dedupe: Optional[dict[str, Any]] = None,
        by_cuid_v1: Optional[dict[tuple[str, str], Any]] = None,
    ) -> None:
        self.by_dedupe = dict(by_dedupe or {})
        self.by_cuid_v1 = dict(by_cuid_v1 or {})
        self.added: list[Any] = []
        self._next_id = 5000

    def query(self, model: Any) -> _FakeQuery:
        return _FakeQuery(self, model)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1
            cuid = getattr(obj, "canonical_unit_id", None)
            ver = getattr(obj, "immutable_version_id", None)
            dedupe = getattr(obj, "deduplication_key", None)
            if cuid and ver:
                self.by_cuid_v1[(cuid, ver)] = obj
            if dedupe:
                self.by_dedupe[dedupe] = obj


def _candidate_handoff(
    *,
    fingerprint: str,
    statement: str,
    dedupe_key: str,
    canonical_hash: str,
    domain: str,
    topic: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        handoff_kind="CANDIDATE",
        request_key="cand-1",
        payload={
            "candidate_fingerprint": fingerprint,
            "normalized_statement": statement,
            "dedupe_key": dedupe_key,
            "canonical_hash": canonical_hash,
            "domain": domain,
            "topic": topic,
            "jurisdiction": "US",
            "language": "en",
            "manifest_entity_id": "D01",
            "manifest_track_id": "D01-TRACK",
            "disease_or_health_condition": "oncology and supportive cancer care",
        },
    )


def test_b4a_same_content_dedupe_drift_reuses_existing_cuid_v1() -> None:
    fingerprint = "5f82bc8cab1c9e9d" + ("0" * 48)
    cuid = f"ku-w6p01-{fingerprint[:16]}"
    canon = "5f82bc8cab1c9e9d776f3c4eb93809a790426a57a70bb7e9eaf65f8728fdf74d"
    statement = "cancer acute lymphoblastic leukemia see acute lymphocytic leukemia"
    existing = SimpleNamespace(
        id=176,
        canonical_unit_id=cuid,
        immutable_version_id="v1",
        canonical_hash=canon,
        deduplication_key="old-dedupe-key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        runtime_eligibility="REVIEW_REQUIRED",
        review_state="NOT_REVIEWED",
        publication_state="DRAFT",
        freshness_state="UNKNOWN",
        provenance_complete=False,
    )
    db = _FakeSession(by_cuid_v1={(cuid, "v1"): existing})
    handoff = _candidate_handoff(
        fingerprint=fingerprint,
        statement=statement,
        dedupe_key="new-dedupe-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        canonical_hash=canon,
        domain="oncology",
        topic="cancer",
    )

    result = execute_governed_persistence(
        db, models, handoffs=[handoff], run_id=1, attempt_id=1
    )

    assert result.knowledge_unit_ids == [176]
    assert result.new_knowledge_count == 0
    assert db.added == []
    assert len(db.by_cuid_v1) == 1


def test_b4a_dedupe_key_hit_still_reuses_without_cuid_lookup_insert() -> None:
    fingerprint = "aaaaaaaaaaaaaaaa" + ("1" * 48)
    cuid = f"ku-w6p01-{fingerprint[:16]}"
    canon = "a" * 64
    existing = SimpleNamespace(
        id=42,
        canonical_unit_id=cuid,
        immutable_version_id="v1",
        canonical_hash=canon,
        deduplication_key="same-dedupe",
    )
    db = _FakeSession(by_dedupe={"same-dedupe": existing}, by_cuid_v1={(cuid, "v1"): existing})
    handoff = _candidate_handoff(
        fingerprint=fingerprint,
        statement="enough sleep tips for adults from trusted guidance pages.",
        dedupe_key="same-dedupe",
        canonical_hash=canon,
        domain="lifestyle",
        topic="sleep",
    )

    result = execute_governed_persistence(
        db, models, handoffs=[handoff], run_id=1, attempt_id=1
    )

    assert result.knowledge_unit_ids == [42]
    assert result.new_knowledge_count == 0
    assert db.added == []


def test_b4a_new_canonical_unit_id_still_inserts() -> None:
    fingerprint = "bbbbbbbbbbbbbbbb" + ("2" * 48)
    cuid = f"ku-w6p01-{fingerprint[:16]}"
    canon = "b" * 64
    db = _FakeSession()
    handoff = _candidate_handoff(
        fingerprint=fingerprint,
        statement="enough sleep tips for adults from trusted guidance pages.",
        dedupe_key="brand-new-dedupe",
        canonical_hash=canon,
        domain="lifestyle",
        topic="sleep",
    )

    result = execute_governed_persistence(
        db, models, handoffs=[handoff], run_id=1, attempt_id=1
    )

    assert result.new_knowledge_count == 1
    assert len(db.added) == 1
    assert db.added[0].canonical_unit_id == cuid
    assert db.added[0].immutable_version_id == "v1"
    assert result.knowledge_unit_ids == [db.added[0].id]


def test_b4a_incompatible_canonical_hash_fail_closed() -> None:
    fingerprint = "cccccccccccccccc" + ("3" * 48)
    cuid = f"ku-w6p01-{fingerprint[:16]}"
    existing = SimpleNamespace(
        id=99,
        canonical_unit_id=cuid,
        immutable_version_id="v1",
        canonical_hash="d" * 64,
        deduplication_key="old-dedupe",
    )
    db = _FakeSession(by_cuid_v1={(cuid, "v1"): existing})
    handoff = _candidate_handoff(
        fingerprint=fingerprint,
        statement="different material content that must not overwrite history.",
        dedupe_key="new-dedupe",
        canonical_hash="e" * 64,
        domain="oncology",
        topic="cancer",
    )

    with pytest.raises(GovernedWeeklyRuntimeError) as exc:
        execute_governed_persistence(db, models, handoffs=[handoff], run_id=1, attempt_id=1)

    assert exc.value.code == "KU_CANONICAL_VERSION_CONTENT_MISMATCH"
    assert db.added == []
