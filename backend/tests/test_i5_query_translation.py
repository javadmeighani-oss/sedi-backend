"""D-017: English search-query fallback for fa/ar governed retrieval (offline)."""
from types import SimpleNamespace

import pytest

from backend.app.services.i5 import query_translation as qt
from backend.app.services.scis import governed_runtime_adapter as adapter


class _Client:
    def __init__(self, out):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self._out = out

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._out))])


def setup_function(_):
    qt._CACHE.clear()


def test_translates_persian_and_caches():
    c = _Client('"ALS amyotrophic lateral sclerosis care and prevention"')
    q = "در مورد بیماری ALS و شیوه‌ی مراقبتی و پیشگیری آن توضیح بده"
    assert qt.translate_query_to_english(q, "fa", c) == "ALS amyotrophic lateral sclerosis care and prevention"
    assert qt.translate_query_to_english(q, "fa", c) is not None and len(c.calls) == 1
    assert c.calls[0]["messages"][1]["content"] == "Question: " + q + " ->"  # only the question text, nothing else


def test_not_needed_for_english_or_latin_only_and_kill_switch(monkeypatch):
    c = _Client("x y z")
    assert qt.translate_query_to_english("tell me about ALS", "en", c) is None
    assert qt.translate_query_to_english("ALS care", "fa", c) is None  # no Arabic-script letters
    assert c.calls == []
    monkeypatch.setenv(qt.DISABLE_ENV, "true")
    assert qt.translate_query_to_english("سلام ALS", "fa", c) is None


def test_rejects_non_english_or_failed_output():
    assert qt.translate_query_to_english("بیماری ALS", "fa", _Client("بیماری")) is None
    bad = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError()))))
    assert qt.translate_query_to_english("بیماری ALS", "fa", bad) is None


def test_adapter_retries_with_english_and_marks_meta(monkeypatch):
    monkeypatch.setattr(qt, "translate_query_alternatives", lambda q, l, client=None: ["amyotrophic lateral sclerosis care"])
    seen = {}

    def fake(db, query, **kw):
        seen.update(query=query, **kw)
        return ["ITEM"], {"language": "en"}

    monkeypatch.setattr(adapter, "retrieve_scis_governed_runtime_items", fake)
    items, meta = adapter._retry_via_english_query(None, "بیماری ALS", "fa", domain=None, limit=3)
    assert items == ["ITEM"] and seen["query"] == "amyotrophic lateral sclerosis care"
    assert seen["language"] == "en" and seen["_via_translation"] is True
    assert meta["cross_language_via_translation"] and meta["language"] == "fa"


def test_adapter_falls_through_when_no_translation_or_no_items(monkeypatch):
    monkeypatch.setattr(qt, "translate_query_alternatives", lambda *a, **k: [])
    assert adapter._retry_via_english_query(None, "q", "fa") is None
    monkeypatch.setattr(qt, "translate_query_alternatives", lambda *a, **k: ["english query"])
    monkeypatch.setattr(adapter, "retrieve_scis_governed_runtime_items", lambda *a, **k: ([], {}))
    assert adapter._retry_via_english_query(None, "q", "fa") is None


def test_alternatives_are_parsed_deduped_and_limited():
    c = _Client("1. multiple sclerosis" + chr(10) + "- Multiple Sclerosis" + chr(10) + "neurological disease" + chr(10) + "extra query four")
    alts = qt.translate_query_alternatives("علائم ام اس چیست؟", "fa", c)
    assert alts == ["multiple sclerosis", "neurological disease", "extra query four"]


def test_adapter_merges_distinct_kus_across_alternatives(monkeypatch):
    monkeypatch.setattr(qt, "translate_query_alternatives", lambda *a, **k: ["mnd treatment", "als treatment", "als"])
    A = SimpleNamespace(knowledge_unit_id=1)
    B = SimpleNamespace(knowledge_unit_id=2)
    C = SimpleNamespace(knowledge_unit_id=3)
    results = {"mnd treatment": [A, B], "als treatment": [B, C], "als": [C]}
    calls = []

    def fake(db, query, **kw):
        calls.append(query)
        return list(results[query]), {"language": "en"}

    monkeypatch.setattr(adapter, "retrieve_scis_governed_runtime_items", fake)
    items, meta = adapter._retry_via_english_query(None, "q", "fa", limit=5)
    assert [i.knowledge_unit_id for i in items] == [1, 2, 3]  # deduped, alternative order
    assert calls == ["mnd treatment", "als treatment", "als"]
    assert meta["translated_queries_hit"] == ["mnd treatment", "als treatment"]  # "als" added nothing new


def test_adapter_stops_when_enough_items_and_skips_empty(monkeypatch):
    monkeypatch.setattr(qt, "translate_query_alternatives", lambda *a, **k: ["x", "y", "z"])
    many = [SimpleNamespace(knowledge_unit_id=i) for i in range(5)]
    calls = []

    def fake(db, query, **kw):
        calls.append(query)
        return ([], {}) if query == "x" else (list(many), {})

    monkeypatch.setattr(adapter, "retrieve_scis_governed_runtime_items", fake)
    items, _ = adapter._retry_via_english_query(None, "q", "fa", limit=5)
    assert len(items) == 5 and calls == ["x", "y"]


def test_prompt_mentions_alternative_official_names():
    assert "motor neurone disease" in qt._INSTRUCTIONS and "different names" in qt._INSTRUCTIONS
