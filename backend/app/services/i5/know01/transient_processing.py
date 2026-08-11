"""Transient processing lifecycle — durable raw residue must be zero when prohibited."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

from backend.app.services.i5.enums import ProcessingPermissionMode
from backend.app.services.i5.know01.rights_engine import assert_no_unauthorized_raw_retention


@dataclass
class TransientProcessResult:
    content_hash: str
    derived_text: str
    durable_raw_path: Optional[str]
    temp_raw_residue: int


def transient_process_bytes(
    raw: bytes,
    *,
    processing_mode: ProcessingPermissionMode,
    extract_fn: Callable[[bytes], str],
    allow_durable_raw: bool = False,
) -> TransientProcessResult:
    """Ephemeral acquire → parse → derived → destroy temp raw.

    Controlled fixtures only in CI. Never writes durable raw unless explicitly allowed
    AND mode is FULL_PROCESS_AND_RETAIN.
    """
    if processing_mode != ProcessingPermissionMode.FULL_PROCESS_AND_RETAIN and allow_durable_raw:
        raise PermissionError("UNAUTHORIZED_RAW_RETENTION")

    content_hash = hashlib.sha256(raw).hexdigest()
    tmp_path = None
    durable_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="sedi_i5_transient_", suffix=".bin")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(raw)
        with open(tmp_path, "rb") as f:
            data = f.read()
        derived = extract_fn(data)
        if allow_durable_raw and processing_mode == ProcessingPermissionMode.FULL_PROCESS_AND_RETAIN:
            durable_path = tmp_path + ".durable"
            with open(durable_path, "wb") as f:
                f.write(data)
        assert_no_unauthorized_raw_retention(
            processing_mode=processing_mode, durable_raw_written=bool(durable_path)
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
    residue = 1 if (tmp_path and os.path.exists(tmp_path)) else 0
    return TransientProcessResult(
        content_hash=content_hash,
        derived_text=derived,
        durable_raw_path=durable_path,
        temp_raw_residue=residue,
    )
