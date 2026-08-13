"""Master Log byte-append helper + §304 historical prefix classification."""

from __future__ import annotations

import subprocess
from pathlib import Path

from backend.app.services.i5.master_log_byte_append import append_bytes, classify_prefix_mutation, sha256_hex

PARENT = "d902b2edd1cf5cf60cfddeb5eb268544ebc1da0d"
CLOSURE = "3838866ea14a52fe8b768909aeaeeb3eb4ebbd88"
MASTER = "docs/SEDI_SECTION15_MASTER_EXECUTION_LOG_FA.md"


def test_append_helper_preserves_prefix_including_crlf(tmp_path: Path):
    path = tmp_path / "log.md"
    prefix = b"AAA\r\nBBB\r\n"
    path.write_bytes(prefix)
    result = append_bytes(path, b"\r\nCCC\r\n")
    post = path.read_bytes()
    assert post.startswith(prefix)
    assert post == b"AAA\r\nBBB\r\n\r\nCCC\r\n"
    assert result["strict_append_only"] is True
    assert result["prefix_preserved_byte_for_byte"] is True
    assert result["pre_sha256"] == sha256_hex(prefix)
    assert result["post_sha256"] == sha256_hex(post)


def test_classify_eol_only_vs_semantic():
    parent = b"hello\nworld\n"
    closure_eol = b"hello\r\nworld\r\n\r\nNEW\r\n"
    closure_sem = b"hello\nWORLD\n\nNEW\n"
    eol = classify_prefix_mutation(parent, closure_eol)
    assert eol["strict_append_only"] is False
    assert eol["incident_class"] == "EOL_NORMALIZATION_ONLY"
    assert eol["information_loss"] is False
    sem = classify_prefix_mutation(parent, closure_sem)
    assert sem["incident_class"] == "SEMANTIC_PREFIX_MUTATION"
    assert sem["information_loss"] is True
    strict = classify_prefix_mutation(parent, parent + b"TAIL")
    assert strict["strict_append_only"] is True
    assert strict["incident_class"] == "STRICT_APPEND"


def test_section304_historical_prefix_is_eol_only_when_git_blobs_available():
    root = Path(__file__).resolve().parents[2]
    try:
        parent = subprocess.check_output(["git", "show", f"{PARENT}:{MASTER}"], cwd=root)
        closure = subprocess.check_output(["git", "show", f"{CLOSURE}:{MASTER}"], cwd=root)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    result = classify_prefix_mutation(parent, closure)
    assert result["strict_append_only"] is False
    assert result["incident_class"] == "EOL_NORMALIZATION_ONLY"
    assert result["information_loss"] is False
    assert result["strip_cr_startswith"] is True
    assert result["eol_norm_startswith"] is True
    assert result["parent_sha256"] == "A468C192CDA4F4DF9DDBA036C811A690E98C9C067BB9D56B46BA9A5E4A364994"
    assert result["closure_sha256"] == "79AAEC8FE1FF57752F4988AB9AA5C89F97820E17D58C9AA6744F1AAA099566B2"
    assert result["longest_common_prefix_bytes"] == 3104513
    assert result["first_changed_byte_offset"] == 3104513
