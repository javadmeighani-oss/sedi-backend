# GATE=SEDI-V1-BE-1000U-100CC-CAPACITY-HARDENING-01
#
# Single-process scheduler/background role.
# Run exactly ONE of these. API workers must set SEDI_DISABLE_SCHEDULER=1
# (or SEDI_PROCESS_ROLE=api) so APScheduler is not multiplied.

from __future__ import annotations

import os
import time

# Ensure this process is the scheduler role (do not disable).
os.environ.pop("SEDI_DISABLE_SCHEDULER", None)
os.environ["SEDI_PROCESS_ROLE"] = "scheduler"

from backend.app.core.capacity_observability import log_event
from backend.app.core.process_role import resolve_process_role, should_start_scheduler
from backend.app.core.scheduler import start_scheduler, scheduler


def main() -> None:
    assert resolve_process_role() == "scheduler"
    assert should_start_scheduler() is True
    start_scheduler()
    log_event(
        "scheduler_role_started",
        role="scheduler",
        running=bool(getattr(scheduler, "running", False)),
        job_count=len(scheduler.get_jobs()) if getattr(scheduler, "running", False) else 0,
    )
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
