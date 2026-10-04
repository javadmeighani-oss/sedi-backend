"""Q1 — gpt-6-luna model defaults + generation-contract regressions (no network)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")


def test_chat_model_defaults_to_gpt_6_luna(monkeypatch):
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    from backend.app.core.conversation.prompts import (
        DEFAULT_OPENAI_CHAT_MODEL,
        resolve_openai_chat_model,
    )

    assert DEFAULT_OPENAI_CHAT_MODEL == "gpt-6-luna"
    assert resolve_openai_chat_model() == "gpt-6-luna"


def test_chat_model_env_override(monkeypatch):
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-custom-chat")
    from backend.app.core.conversation.prompts import resolve_openai_chat_model

    assert resolve_openai_chat_model() == "gpt-custom-chat"


def test_chat_request_uses_low_reasoning_and_no_temperature(monkeypatch):
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_text="ok")

    from backend.app.core.conversation import prompts as prompts_mod

    with patch.object(prompts_mod.client.responses, "create", side_effect=fake_create):
        prompts_mod.create_primary_chat_response(
            [{"role": "user", "content": "hi"}]
        )

    assert captured["model"] == "gpt-6-luna"
    assert captured["reasoning"] == {"effort": "low"}
    assert "temperature" not in captured
    assert "top_p" not in captured


def test_notification_model_defaults_to_gpt_6_luna(monkeypatch):
    monkeypatch.delenv("OPENAI_NOTIFICATION_MODEL", raising=False)
    from backend.app.core.ai_text_engine import (
        DEFAULT_OPENAI_NOTIFICATION_MODEL,
        resolve_openai_notification_model,
    )

    assert DEFAULT_OPENAI_NOTIFICATION_MODEL == "gpt-6-luna"
    assert resolve_openai_notification_model() == "gpt-6-luna"


def test_notification_model_env_override(monkeypatch):
    monkeypatch.setenv("OPENAI_NOTIFICATION_MODEL", "gpt-custom-notif")
    from backend.app.core.ai_text_engine import resolve_openai_notification_model

    assert resolve_openai_notification_model() == "gpt-custom-notif"


def test_notification_uses_none_reasoning_and_compatible_params(monkeypatch):
    monkeypatch.delenv("OPENAI_NOTIFICATION_MODEL", raising=False)
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hey there"))]
        )

    import backend.app.core.ai_text_engine as notif_mod

    with patch.object(notif_mod.client.chat.completions, "create", side_effect=fake_create):
        text = notif_mod.generate_notification_text(
            language="en",
            notification_type=notif_mod.NOTIF_TYPE_MORNING,
            user_name="Alex",
        )

    assert text == "Hey there"
    assert captured["model"] == "gpt-6-luna"
    assert captured["reasoning_effort"] == "none"
    assert captured.get("temperature") == 0.8
    assert "reasoning" not in captured


def test_generation_contract_forbids_autonomous_memory_discovery_action():
    from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
    from backend.app.core.conversation.prompts import ConversationPrompts
    from backend.app.core.conversation.stages import ConversationStage

    for lang in ("en", "fa", "ar"):
        persona = PersonaPolicyV1.system_prompt(lang, None).lower()
        assert "current need" in persona or "نیاز فعلی" in persona or "الحاجة الحالية" in persona
        assert "do not independently" in persona or "مستقلاً" in persona or "بشكل مستقل" in persona
        assert "profiling" in persona or "پروفایل" in persona or "تنميط" in persona
        assert "store all collected information" not in persona
        assert "self-training" not in persona
        assert "reminders" in persona or "یادآوری" in persona or "تذكيرات" in persona

        legacy = ConversationPrompts(lang)._build_system_prompt(
            ConversationStage.DAILY_RELATION,
            "friend",
            3,
            "normal",
            context={"conversation_count": 3},
        ).lower()
        assert "store all collected information" not in legacy
        assert "self-training" not in legacy
        assert "becoming smarter" not in legacy
        assert "generation contract" in legacy or "قرارداد تولید" in legacy or "عقد التوليد" in legacy


def test_current_need_first_and_one_nbq_preserved():
    from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1

    base = PersonaPolicyV1.relationship_guidance_block("decide", "en")
    assert "Current need: DECIDE" in base
    assert "Serve the current need first" in base

    with_nbq = PersonaPolicyV1.relationship_guidance_block(
        "general", "en", nbq_scheduled=True
    )
    assert "discovery" in with_nbq.lower()
    assert "do not ask an additional discovery" in with_nbq.lower()

    persona = PersonaPolicyV1.system_prompt("en", None).lower()
    assert "at most one soft discovery question" in persona
    assert "do not add your own" in persona


def _conversation_source_files() -> list[str]:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "core" / "conversation"
    return [
        str(root / "prompts.py"),
        str(root / "brain.py"),
    ]


def test_no_hardcoded_legacy_chat_models_in_conversation_paths():
    """User-visible conversation generation must not hardcode gpt-4o-mini / gpt-4.1-mini."""
    banned = ("gpt-4o-mini", "gpt-4.1-mini")
    for path in _conversation_source_files():
        text = open(path, encoding="utf-8").read()
        for model in banned:
            assert model not in text, f"{path} still hardcodes/mentions {model}"


def test_all_conversation_callsites_resolve_openai_chat_model():
    """Every conversation OpenAI create callsite resolves OPENAI_CHAT_MODEL."""
    import ast
    from pathlib import Path

    prompts_path = Path(_conversation_source_files()[0])
    brain_path = Path(_conversation_source_files()[1])

    prompts_src = prompts_path.read_text(encoding="utf-8")
    brain_src = brain_path.read_text(encoding="utf-8")

    # Responses API conversation path(s) go through the shared helper.
    assert "def create_primary_chat_response" in prompts_src
    assert "resolve_openai_chat_model()" in prompts_src
    assert "create_primary_chat_response(" in prompts_src
    assert "create_primary_chat_response(" in brain_src

    # Chat Completions conversation paths must resolve model (no bare string literals).
    for label, src in (("prompts.py", prompts_src), ("brain.py", brain_src)):
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # *.chat.completions.create(...) or *.responses.create(...)
            if not isinstance(func, ast.Attribute) or func.attr != "create":
                continue
            value = func.value
            is_completions = (
                isinstance(value, ast.Attribute)
                and value.attr == "completions"
                and isinstance(value.value, ast.Attribute)
                and value.value.attr == "chat"
            )
            is_responses = isinstance(value, ast.Attribute) and value.value is not None and (
                (isinstance(value.value, ast.Name) and value.value.id == "responses")
                or (isinstance(value, ast.Attribute) and value.attr == "create")
            )
            # Narrow: attribute chain ending in responses.create
            is_responses_create = False
            cur = func
            if isinstance(cur, ast.Attribute) and cur.attr == "create":
                if isinstance(cur.value, ast.Attribute) and cur.value.attr == "responses":
                    is_responses_create = True
                elif isinstance(cur.value, ast.Name) and cur.value.id == "responses":
                    is_responses_create = True

            if not (is_completions or is_responses_create):
                continue

            model_kw = next((kw for kw in node.keywords if kw.arg == "model"), None)
            assert model_kw is not None, f"{label}: create() missing model="
            # Must not be a constant string model id.
            assert not isinstance(model_kw.value, ast.Constant), (
                f"{label}: create() hardcodes model literal"
            )
            # Accept resolve_openai_chat_model() or a name bound from it (chat_model / model / _chat_model).
            ok = False
            val = model_kw.value
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Name):
                ok = val.func.id == "resolve_openai_chat_model"
            elif isinstance(val, ast.Name):
                ok = val.id in {"model", "chat_model", "_chat_model"}
            assert ok, f"{label}: create() model does not resolve OPENAI_CHAT_MODEL"

    # create_primary_chat_response itself must call resolve_openai_chat_model.
    assert "model = resolve_openai_chat_model()" in prompts_src
    assert 'reasoning={"effort": DEFAULT_OPENAI_CHAT_REASONING_EFFORT}' in prompts_src or (
        "reasoning=" in prompts_src and "DEFAULT_OPENAI_CHAT_REASONING_EFFORT" in prompts_src
    )
