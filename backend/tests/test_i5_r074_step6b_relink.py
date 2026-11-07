"""R-074 step 6b: the relink applies the SAME governed rule (catalog URL needle -> concept) to units already in the library.

Pure-logic tests with a scripted session (no production rows): dry run writes nothing, apply links only matching, not-yet-linked
units, nothing else, and is idempotent."""
from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.i5.know02 import relink_concepts as rc


class _Q:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def all(self):
        return list(self._rows)


class _DB:
    def __init__(self, units, concepts, existing):
        self._script = [units, concepts, existing]
        self.committed = self.rolled_back = False

    def query(self, *cols):
        return _Q(self._script.pop(0))

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


UNITS = [
    (1, "https://medlineplus.gov/dementia.html"),          # concept dementia, not linked yet
    (2, "https://www.nhs.uk/conditions/dementia/"),         # concept dementia, already linked
    (3, "https://medlineplus.gov/cholesterol.html"),        # no concept for this page
    (4, "https://medlineplus.gov/alzheimersdisease.html"),  # concept alzheimers, not linked yet
    (5, "https://example.org/unrelated"),                   # no needle
]
CONCEPTS = [SimpleNamespace(concept_key="disease:dementia", id=10), SimpleNamespace(concept_key="disease:alzheimers", id=11)]
EXISTING = [(2, 10)]


def _run(monkeypatch, apply):
    calls = []
    monkeypatch.setattr(rc, "link_ku_concept", lambda db, **kw: calls.append((kw["knowledge_unit_id"], kw["concept_id"])))
    db = _DB(list(UNITS), list(CONCEPTS), list(EXISTING))
    out = rc.relink_catalog_concepts(db, apply=apply)
    return out, calls, db


def test_dry_run_counts_the_links_it_would_make_and_writes_nothing(monkeypatch):
    out, calls, db = _run(monkeypatch, apply=False)
    assert out == {"eligible_units_seen": 5, "new_links": 2, "per_concept": {"disease:dementia": 1, "disease:alzheimers": 1}, "applied": False}
    assert calls == [] and db.rolled_back and not db.committed


def test_apply_links_only_matching_unlinked_units_and_commits(monkeypatch):
    out, calls, db = _run(monkeypatch, apply=True)
    assert sorted(calls) == [(1, 10), (4, 11)]  # not 2 (already linked), not 3/5 (no governed needle)
    assert out["applied"] is True and out["new_links"] == 2 and db.committed and not db.rolled_back


def test_a_unit_whose_concept_row_is_missing_is_skipped(monkeypatch):
    calls = []
    monkeypatch.setattr(rc, "link_ku_concept", lambda db, **kw: calls.append(kw))
    db = _DB([(1, "https://medlineplus.gov/dementia.html")], [], [])
    out = rc.relink_catalog_concepts(db, apply=True)
    assert calls == [] and out["new_links"] == 0


def test_the_workflow_is_dispatch_only_and_dumps_the_table_before_apply():
    import pathlib

    wf = (pathlib.Path(__file__).resolve().parents[2] / ".github/workflows/i5-concept-relink.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in wf and "push:" not in wf and "pull_request" not in wf
    assert "CONCEPT_RELINK_APPLY" in wf and "pg_dump" in wf and "-t i5_knowledge_unit_concepts" in wf
    dump = wf.index("docker exec sedi-postgres pg_dump")
    assert dump < wf.index("relink_concepts --apply")
    assert "org.opencontainers.image.revision" in wf and wf.index("oci_revision_guard") < dump  # Codex P2 (PR 161)
