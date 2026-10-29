"""R-039 (Javad 2026-10-29): no Like button; Dislike asks WHY inside the same notification with answers like
"I'm busy now / it is rest time / no mood"; every answer means "not now" and moves the next send to another time."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import TypeAdapter

from backend.app.schemas.notification import FeedbackReasonV1
from backend.app.services.gate4.push_payload import MOBILE_INTERACTION_ACTIONS
from backend.app.services.i10.interaction_vocabulary import BOUNDED_DISLIKE_REASONS, resolve_interaction_verb
from backend.app.services.i10.plan_progress import state_from_feedback
from backend.app.services.notifications import adaptive_policy_v1 as ap

NEW = ("busy_now", "rest_time", "not_in_mood")


def test_the_tray_offers_talk_and_dislike_only():
    assert MOBILE_INTERACTION_ACTIONS == ("open_chat", "dislike")


def test_the_new_answers_are_accepted_everywhere():
    adapter = TypeAdapter(FeedbackReasonV1)
    for reason in NEW:
        assert reason in BOUNDED_DISLIKE_REASONS
        assert adapter.validate_python(reason) == reason
        resolved = resolve_interaction_verb({"action_id": "dislike", "reason": reason})
        assert resolved.dislike_reason_bounded and resolved.feedback_action == "dislike"


def test_each_answer_moves_the_digest_time_and_never_stops_it():
    now = datetime.now(timezone.utc)
    for reason in NEW:
        row = SimpleNamespace(action="dislike", meta_json=json.dumps({"reason": reason}))
        state = state_from_feedback([row], now)
        assert state["shift_time"] is True and state["skip"] is False


def test_each_answer_is_a_timing_reason_for_the_adaptive_policy():
    for reason in NEW:
        assert reason in ap.TIMING_REASONS and reason in ap.SKIP_REASONS
