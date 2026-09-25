"""Presentation-only SSE word pacing contract. No OpenAI/network calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.routers.interact import (
    _PRESENTATION_WORD_PACE_S,
    presentation_word_deltas,
)

_INTERACT_SRC = Path("backend/app/routers/interact.py").read_text(encoding="utf-8")


def test_presentation_word_pace_is_133ms():
    assert _PRESENTATION_WORD_PACE_S == pytest.approx(0.133)


@pytest.mark.parametrize(
    "text",
    [
        "Hello there, Sedi.",
        "سلام صدی  خوب هستی؟",
        "مرحبا سدي،  كيف حالك؟",
        "line one\n\nline two\t  spaced",
        "  leading and trailing  \n",
    ],
)
def test_presentation_word_deltas_reconstruct_exact_text(text):
    assert "".join(presentation_word_deltas(text)) == text


def test_stream_sleeps_only_on_presentation_pace_constant():
    assert "_PRESENTATION_WORD_PACE_S = 0.133" in _INTERACT_SRC
    assert "await asyncio.sleep(_PRESENTATION_WORD_PACE_S)" in _INTERACT_SRC
    assert _INTERACT_SRC.count("asyncio.sleep(") == 1
    assert _INTERACT_SRC.count("_PRESENTATION_WORD_PACE_S") == 2
    assert "0.080" not in _INTERACT_SRC
    assert "adaptive" not in _INTERACT_SRC.lower()
    assert '_WORD_DELTA_RE = re.compile(r"\\S+|\\s+")' in _INTERACT_SRC
