"""Unit proofs for KNOW-01 activation guard (positive + negative control)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.tests.helpers.know01_activation_guard import main, run_guard, scan_text


def test_know01_activation_guard_clean_text_has_no_hits():
    assert scan_text("PRODUCTION_CRAWLER_ACTIVATED = False\nRAG_ACTIVATED = NO\n") == []


def test_know01_activation_guard_detects_forbidden_markers():
    hits = scan_text("PRODUCTION_CRAWLER_ACTIVATED = True\n")
    assert hits
    hits2 = scan_text("RAG_ACTIVATED = True\n")
    assert hits2


def test_know01_activation_guard_positive_control_on_package(tmp_path: Path):
    # Clean package roots must pass when scanned as-is
    code = run_guard(roots=["backend/app/services/i5/know01"], label="unit_clean")
    assert code == 0


def test_know01_activation_guard_negative_control_fixture(tmp_path: Path):
    bad = tmp_path / "forbidden_activation_fixture.py"
    bad.write_text("PRODUCTION_CRAWLER_ACTIVATED = True\n", encoding="utf-8")
    code = run_guard(roots=[str(bad)], label="unit_negative")
    assert code == 2
    # CLI expect-fail mode must succeed only when forbidden content is present
    assert main(["--root", str(bad), "--label", "cli_neg", "--expect-fail"]) == 0
    clean = tmp_path / "clean.py"
    clean.write_text("x = 1\n", encoding="utf-8")
    assert main(["--root", str(clean), "--label", "cli_neg_miss", "--expect-fail"]) == 1
