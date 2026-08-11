"""Fail-closed production-activation scanner for I5-KNOW-01 CI integrity.

Three states:
  SCANNER_AVAILABLE + NO_FORBIDDEN_MATCH → PASS (exit 0)
  SCANNER_AVAILABLE + FORBIDDEN_MATCH → FAIL (exit 2)
  SCANNER_UNAVAILABLE / SCAN_ERROR → FAIL (exit 1)

Never interpret a missing tool as PASS.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

# Patterns match intentional activation-true markers (not documentation of NO/False).
FORBIDDEN_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"PRODUCTION_CRAWLER_ACTIVATED\s*=\s*True\b"),
    re.compile(r"\bRAG_ACTIVATED\s*=\s*True\b"),
    re.compile(r"\bCRAWLER_ACTIVATED\s*=\s*True\b"),
    re.compile(r"SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED\s*=\s*[\"']?true[\"']?", re.I),
    re.compile(r"SEDI_I5_SOURCE_ACTIVATION_ENABLED\s*=\s*[\"']?true[\"']?", re.I),
)

DEFAULT_SCAN_ROOTS: Tuple[str, ...] = (
    "backend/app/services/i5/know01",
)

TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".toml", ".ini", ".txt", ".md", ".cfg", ".env"}


def iter_scan_files(roots: Sequence[str]) -> Iterable[Path]:
    for root in roots:
        path = Path(root)
        if not path.exists():
            raise FileNotFoundError(f"SCAN_ROOT_MISSING:{root}")
        if path.is_file():
            yield path
            continue
        for child in path.rglob("*"):
            if child.is_file() and child.suffix.lower() in TEXT_SUFFIXES:
                yield child


def scan_text(text: str) -> List[str]:
    hits: List[str] = []
    for pat in FORBIDDEN_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def scan_paths(roots: Sequence[str]) -> List[Tuple[str, str]]:
    findings: List[Tuple[str, str]] = []
    for file_path in iter_scan_files(roots):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"SCAN_READ_ERROR:{file_path}:{exc}") from exc
        for pattern in scan_text(text):
            findings.append((str(file_path).replace("\\", "/"), pattern))
    return findings


def run_guard(*, roots: Sequence[str], label: str) -> int:
    try:
        findings = scan_paths(roots)
    except Exception as exc:  # noqa: BLE001 — fail-closed on any scan error
        print(f"ACTIVATION_GUARD_SCAN_ERROR label={label} error={exc}")
        print("ACTIVATION_GUARD_RESULT=FAIL_SCANNER_ERROR")
        return 1
    if findings:
        for path, pattern in findings:
            print(f"FORBIDDEN_PRODUCTION_ACTIVATION path={path} pattern={pattern}")
        print(f"ACTIVATION_GUARD_RESULT=FAIL_FORBIDDEN label={label}")
        return 2
    print(f"ACTIVATION_GUARD_RESULT=PASS label={label}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="I5-KNOW-01 activation guard")
    parser.add_argument(
        "--root",
        action="append",
        dest="roots",
        default=None,
        help="Scan root (repeatable). Defaults to KNOW-01 package.",
    )
    parser.add_argument("--label", default="clean", help="Evidence label")
    parser.add_argument(
        "--expect-fail",
        action="store_true",
        help="Negative control: require forbidden match (exit 0 only if scan finds hits).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    roots = args.roots or list(DEFAULT_SCAN_ROOTS)
    code = run_guard(roots=roots, label=args.label)
    if args.expect_fail:
        if code == 2:
            print("ACTIVATION_GUARD_NEGATIVE_CONTROL=PASS")
            return 0
        print("ACTIVATION_GUARD_NEGATIVE_CONTROL=FAIL (forbidden marker not detected)")
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
