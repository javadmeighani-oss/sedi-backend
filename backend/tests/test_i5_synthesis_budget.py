"""Grounded synthesis keeps retrieval rank order and fits all items in the chat budget."""
from backend.app.services.i5.reference_renderer import _clip_statement, synthesize_grounded_text
from backend.app.services.i5.reference_renderer import EvidenceHandoff
import dataclasses


def _ev(i, text, label):
    fields = {f.name for f in dataclasses.fields(EvidenceHandoff)}
    base = dict(knowledge_unit_id=i, canonical_unit_id=f"c{i}", immutable_version_id="v1", memory_item_id=f"m{i}",
                provenance_id=i, source_profile_id=1, raw_evidence_id=i,
                normalized_statement=text, label=label, domain="neurology_als",
                evidence_strength="MODERATE", medical_safety_state="CLEARED", freshness_state="CURRENT",
                conflict_state="NONE", language="en")
    return EvidenceHandoff(**{k: v for k, v in base.items() if k in fields})


def test_rank_order_is_preserved_not_alphabetical():
    ev = [_ev(1, "Treatment: riluzole may slow progression.", "ZZZ-nhs"), _ev(2, "Description: ALS is progressive.", "AAA-medline")]
    text, _ = synthesize_grounded_text(ev, language="en")
    assert text.index("Treatment") < text.index("Description")


def test_long_statements_are_clipped_at_a_boundary_so_every_item_fits():
    long = ("Mutations in several genes can cause familial ALS. " * 40).strip()
    ev = [_ev(i, long, f"L{i}") for i in range(1, 6)]
    text, _ = synthesize_grounded_text(ev, language="en")
    assert len(text) < 3300
    assert text.count(" …") == 5 and all(f"{i}. " in text for i in range(1, 6))


def test_clip_keeps_short_text_intact():
    assert _clip_statement("Short sentence.") == "Short sentence."


def test_psychology_domain_adds_support_style_and_other_domains_do_not():
    from backend.app.services.i5.reference_renderer import format_care_context_block, render_grounded_answer

    def block(domain):
        ev = {"status": "OK", "knowledge_snippets": [{
            "knowledge_unit_id": 1, "canonical_unit_id": "c1", "immutable_version_id": "v1", "content": "Tip: slow breathing helps stress.",
            "normalized_statement": "Tip: slow breathing helps stress.", "domain": domain, "evidence_strength": "MODERATE",
            "freshness_state": "CURRENT", "conflict_state": "NONE", "medical_safety_state": "CLEARED", "language": "en"}]}
        return format_care_context_block(render_grounded_answer(ev, language="fa", user_requested_sources=True))

    assert "PSYCHOLOGICAL SUPPORT STYLE" in block("mental_health_psychology")
    assert "PSYCHOLOGICAL SUPPORT STYLE" in block("wellbeing")
    assert "PSYCHOLOGICAL SUPPORT STYLE" not in block("neurology_als")
