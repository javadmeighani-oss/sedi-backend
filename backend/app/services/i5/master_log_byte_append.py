"""Byte-preserving Master Log append. Never rewrite historical prefix bytes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def read_exact(path: PathLike) -> bytes:
    return Path(path).read_bytes()


def append_bytes(path: PathLike, suffix: bytes) -> dict[str, object]:
    """Append suffix bytes to path. Prefix must be preserved byte-for-byte."""
    target = Path(path)
    pre = target.read_bytes()
    pre_sha = sha256_hex(pre)
    if not suffix:
        raise ValueError("EMPTY_SUFFIX")
    if suffix.startswith(b"\xef\xbb\xbf"):
        raise ValueError("BOM_FORBIDDEN")
    new = pre + suffix
    if not new.startswith(pre):
        raise RuntimeError("PREFIX_NOT_PRESERVED")
    target.write_bytes(new)
    post = target.read_bytes()
    if post != new or not post.startswith(pre):
        raise RuntimeError("POST_WRITE_PREFIX_MISMATCH")
    return {
        "path": str(target),
        "pre_size": len(pre),
        "pre_sha256": pre_sha,
        "suffix_size": len(suffix),
        "suffix_sha256": sha256_hex(suffix),
        "post_size": len(post),
        "post_sha256": sha256_hex(post),
        "startswith_pre": True,
        "strict_append_only": True,
        "prefix_preserved_byte_for_byte": True,
    }


def classify_prefix_mutation(parent: bytes, closure: bytes) -> dict[str, object]:
    """Classify parent→closure Master Log mutation (forensic, no rewrite)."""
    n = min(len(parent), len(closure))
    i = 0
    while i < n and parent[i] == closure[i]:
        i += 1
    strip_p = parent.replace(b"\r", b"")
    strip_c = closure.replace(b"\r", b"")
    eol_norm_p = parent.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    eol_norm_c = closure.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    strict = closure.startswith(parent)
    eol_only_prefix = (not strict) and eol_norm_c.startswith(eol_norm_p) and strip_c.startswith(strip_p)
    if strict:
        incident_class = "STRICT_APPEND"
        information_loss = False
    elif eol_only_prefix:
        incident_class = "EOL_NORMALIZATION_ONLY"
        information_loss = False
    else:
        incident_class = "SEMANTIC_PREFIX_MUTATION"
        information_loss = True
        ws_p = b" ".join(eol_norm_p.split())
        ws_c = b" ".join(eol_norm_c.split())
        if ws_c.startswith(ws_p):
            incident_class = "MIXED"
            information_loss = False
    return {
        "strict_append_only": strict,
        "longest_common_prefix_bytes": i,
        "first_changed_byte_offset": (-1 if strict and len(parent) <= len(closure) else i),
        "parent_size": len(parent),
        "closure_size": len(closure),
        "parent_sha256": sha256_hex(parent),
        "closure_sha256": sha256_hex(closure),
        "parent_prefix_sha256": sha256_hex(parent[:i]),
        "closure_prefix_sha256": sha256_hex(closure[:i]),
        "eol_norm_startswith": eol_norm_c.startswith(eol_norm_p),
        "strip_cr_startswith": strip_c.startswith(strip_p),
        "incident_class": incident_class,
        "information_loss": information_loss,
    }
