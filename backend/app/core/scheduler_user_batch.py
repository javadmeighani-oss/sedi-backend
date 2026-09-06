"""Bounded same-tick keyset user scans for legacy scheduler jobs.

Preserves per-tick eligibility coverage at the 1000-user target by walking
keyset pages inside one job invocation (no cross-tick cursor for timed jobs).

In-process only — SAFE_ONLY_SINGLE_BACKGROUND_PROCESS.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Iterable, List, Optional, Sequence, TypeVar

from sqlalchemy.orm import Session

from backend.app.models import User

logger = logging.getLogger(__name__)

T = TypeVar("T")

_DEFAULT_BATCH = 200
_DEFAULT_MAX_PER_TICK = 1000


def user_scan_batch_size() -> int:
    raw = (os.getenv("SCHEDULER_USER_SCAN_BATCH_SIZE") or "").strip()
    if not raw:
        return _DEFAULT_BATCH
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_BATCH
    return max(1, min(500, n))


def user_scan_max_per_tick() -> int:
    raw = (os.getenv("SCHEDULER_USER_SCAN_MAX_PER_TICK") or "").strip()
    if not raw:
        return _DEFAULT_MAX_PER_TICK
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_MAX_PER_TICK
    return max(1, min(5000, n))


def fetch_users_keyset_page(
    db: Session,
    *,
    after_user_id: int,
    limit: int,
) -> List[User]:
    if limit < 1:
        return []
    return (
        db.query(User)
        .filter(User.id > int(after_user_id))
        .order_by(User.id.asc())
        .limit(int(limit))
        .all()
    )


def iter_users_bounded(
    db: Session,
    *,
    batch_size: Optional[int] = None,
    max_per_tick: Optional[int] = None,
) -> Iterable[User]:
    """Yield users via keyset pages; stop at max_per_tick (default 1000)."""
    size = int(batch_size) if batch_size is not None else user_scan_batch_size()
    cap = int(max_per_tick) if max_per_tick is not None else user_scan_max_per_tick()
    after = 0
    yielded = 0
    while yielded < cap:
        page_limit = min(size, cap - yielded)
        page = fetch_users_keyset_page(db, after_user_id=after, limit=page_limit)
        if not page:
            return
        for user in page:
            yield user
            yielded += 1
            if yielded >= cap:
                # If more users may exist beyond cap, log capacity risk (no PHI).
                nxt = fetch_users_keyset_page(db, after_user_id=user.id, limit=1)
                if nxt:
                    logger.warning(
                        "scheduler_user_scan_cap_hit cap=%s last_user_id=%s remaining=yes",
                        cap,
                        user.id,
                    )
                return
        after = page[-1].id
        if len(page) < page_limit:
            return


def run_per_user_isolated(
    users: Sequence[User],
    handler: Callable[[User], None],
    *,
    job_id: str,
) -> dict:
    """Apply handler per user; isolate failures so one user cannot stop the batch."""
    ok = 0
    failed = 0
    for user in users:
        try:
            handler(user)
            ok += 1
        except Exception:
            failed += 1
            logger.exception(
                "scheduler_user_isolated_failure job_id=%s user_id=%s",
                job_id,
                getattr(user, "id", None),
            )
    return {"ok": ok, "failed": failed, "scanned": len(users)}
