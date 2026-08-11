"""Master Log append-only byte-prefix guard (NF11).

Never rewrite historical Master Log bytes. Prove NEW.startswith(PRE) before/after append.
Prohibit whole-file EOL normalization.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class MasterLogPrefixMutationError(RuntimeError):
    pass


class MasterLogEolPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class MasterLogSnapshot:
    path: Path
    size: int
    sha256: str
    crlf_count: int
    lf_only_count: int
    bytes: bytes

    @property
    def eol_policy_ok(self) -> bool:
        return self.lf_only_count == 0


def snapshot_master_log(path: Path | str) -> MasterLogSnapshot:
    p = Path(path)
    data = p.read_bytes()
    crlf = data.count(b"\r\n")
    lf_only = data.count(b"\n") - crlf
    return MasterLogSnapshot(
        path=p,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest().upper(),
        crlf_count=crlf,
        lf_only_count=lf_only,
        bytes=data,
    )


def assert_byte_prefix(pre: bytes, post: bytes) -> None:
    if not post.startswith(pre):
        raise MasterLogPrefixMutationError("MASTER_LOG_PREFIX_MUTATION")


def assert_crlf_policy(data: bytes) -> None:
    if data.count(b"\n") - data.count(b"\r\n") != 0:
        raise MasterLogEolPolicyError("MASTER_LOG_EOL_POLICY")


def append_master_log_section(
    path: Path | str,
    section_text: str,
    *,
    baseline: MasterLogSnapshot | None = None,
) -> MasterLogSnapshot:
    """Append CRLF-normalized section; prove byte-prefix append-only."""
    p = Path(path)
    pre = snapshot_master_log(p)
    if baseline is not None:
        assert_byte_prefix(baseline.bytes, pre.bytes)
        if pre.sha256 != baseline.sha256 or pre.size != baseline.size:
            # Allow only if baseline was earlier and current still prefixes baseline
            assert_byte_prefix(baseline.bytes, pre.bytes)
    assert_crlf_policy(pre.bytes)

    # Normalize incoming section to CRLF; never rewrite historical prefix.
    body = section_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    if not body.startswith("\r\n"):
        body = "\r\n" + body
    if not body.endswith("\r\n"):
        body += "\r\n"

    new_bytes = pre.bytes + body.encode("utf-8")
    assert_byte_prefix(pre.bytes, new_bytes)
    assert_crlf_policy(new_bytes)

    # Write via open+write of full content only after prefix proof; content = prefix + append.
    p.write_bytes(new_bytes)

    post = snapshot_master_log(p)
    assert_byte_prefix(pre.bytes, post.bytes)
    assert_crlf_policy(post.bytes)
    if baseline is not None:
        assert_byte_prefix(baseline.bytes, post.bytes)
    return post
