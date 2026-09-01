"""I10-B12 contextual follow-up vocabulary — CareFollowUpTask authority."""

from __future__ import annotations

from enum import Enum


class FollowUpTaskSource(str, Enum):
    MANUAL = "manual"
    GENERAL_CONTEXTUAL = "general_ctx"
    POST_EVENT = "post_event"


class FollowUpTaskStatus(str, Enum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"
    NOTIFIED = "notified"


BOUNDED_META_PREFIX = "@@SEDI_B12@@"
