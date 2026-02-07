"""
Sanity check: ensure Release D acceptance test file compiles.
Prevents broken test files (e.g. concatenated imports) from being committed.
Runs on Linux/CI with: pytest -q backend/tests/test_compile_acceptance.py
"""

import py_compile
from pathlib import Path


def test_acceptance_release_d_compiles():
    """Compile backend/tests/acceptance/test_release_d.py; fail if invalid Python."""
    # Path relative to this test file: tests/acceptance/test_release_d.py
    here = Path(__file__).resolve().parent
    target = here / "acceptance" / "test_release_d.py"
    py_compile.compile(str(target), doraise=True)
