"""Chat answers are shown as plain text in the app: strip markdown emphasis so users never see raw ** or #."""
from __future__ import annotations

import re

_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.S)
_CODE = re.compile(r"`([^`\n]+)`")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_STAR_BULLET = re.compile(r"^(\s*)\*\s+", re.M)


def to_plain_chat_text(text: str) -> str:
    if not text:
        return text
    out = _BOLD.sub(r"\2", text)
    out = _CODE.sub(r"\1", out)
    out = _HEADING.sub("", out)
    out = _STAR_BULLET.sub(r"\1- ", out)
    return out.replace("**", "")
