"""General-knowledge questions must not be blocked by an unresolved pronoun / 'for me' cue."""
from unittest.mock import MagicMock, patch

from backend.app.services.i5.runtime_knowledge_retrieval import (
    STATUS_INSUFFICIENT_CONTEXT, STATUS_OK, retrieve_knowledge_context,
)
from backend.tests.test_smart_rag_phase2a_query_intelligence import _item


def _run(query, lang="fa"):
    items = [_item(ku_id=1, canon="a", statement="ALS is a nervous system disease.", domain="neurology_als", topic="als")]
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, {"effective_mode": "lexical"}),
    ):
        return retrieve_knowledge_context(MagicMock(), query, language=lang)


def test_for_me_and_about_it_phrasings_still_retrieve():
    for q in ("در زمینه ALS دوباره بررسی کن تا در موردش برام توضیح بدی",
              "ALS را برای من توضیح بده",
              "درباره ALS برای من توضیح بده"):
        r = _run(q)
        assert r.status == STATUS_OK and r.items, q


def test_personal_referent_cues_still_block():
    for q in ("نتیجه قبلی آزمایشم چطور بود", "همان دارو چطور مصرف شود", "مادرم چطور بود"):
        r = _run(q)
        assert r.status == STATUS_INSUFFICIENT_CONTEXT and r.clarification_required, q
