"""CR-02 — Relationship guidance wording contracts."""

from __future__ import annotations

from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1


def test_be_heard_listen_before_advice():
    block = PersonaPolicyV1.relationship_guidance_block("be_heard", "en")
    low = block.lower()
    assert "be_heard" in low or "listen" in low
    assert "before advice" in low or "listen before" in low


def test_autonomy_no_dependency_exclusivity_wording():
    for need in ("motivate", "be_heard", "general", "decide"):
        for lang in ("en", "fa", "ar"):
            block = PersonaPolicyV1.relationship_guidance_block(need, lang)
            low = block.lower()
            assert "can't live without you" not in low
            assert "you need me" not in low
            assert "only friend" not in low
            if need == "motivate" and lang == "en":
                assert "shame" in low or "pressure" in low
                assert "autonomy" in low
            if lang == "en":
                assert "do not claim exclusive" in low or "fabricated intimacy" in low


def test_no_diagnosis_or_personality_labels_in_guidance():
    for need in (
        "be_heard",
        "understand",
        "decide",
        "act",
        "motivate",
        "explore",
        "general",
    ):
        block = PersonaPolicyV1.relationship_guidance_block(need, "en")
        low = block.lower()
        assert "personality type" not in low
        assert "you are depressed" not in low
        assert "bipolar" not in low
        assert "do not diagnose" in low


def test_nbq_scheduled_forbids_extra_discovery_question():
    with_nbq = PersonaPolicyV1.relationship_guidance_block(
        "general", "en", nbq_scheduled=True
    )
    without = PersonaPolicyV1.relationship_guidance_block(
        "general", "en", nbq_scheduled=False
    )
    assert "discovery" in with_nbq.lower()
    assert "additional" in with_nbq.lower() or "do not ask" in with_nbq.lower()
    assert with_nbq != without
