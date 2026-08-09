"""Section 30 / I5-IMPL-W6-P01 — CI evidence-pack app-mutation sentinel (pure, no GH deps).

Regression coverage for the scope-aware `backend/app/**` mutation sentinel used
by the `i5-w6p02-offline-e2e` evidence-pack step in
`.github/workflows/ci-backend-tests.yml`. The sentinel logic itself is a pure
function (`unexpected_app_mutations`) so it can be exercised here without a
GitHub Actions runner or a real git repository.
"""
from __future__ import annotations

from backend.tests.helpers.w6p01_evidence_app_mutation import unexpected_app_mutations

ALLOWED_APP_PATH_PREFIXES = [
    "backend/app/services/i5/metrics.py",
    "backend/app/services/i5/weekly_orchestrator.py",
    "backend/app/services/i5/governed_weekly_runtime.py",
    "backend/app/services/i5/adapters/**",
    "backend/app/services/i5/source_discovery.py",
    "backend/app/core/scheduler.py",
    # CAP-OPEN-17 personalization surface (post-W6-P02 GATE_START_SHA; keep allowlisted).
    "backend/app/services/i5/runtime_knowledge_retrieval.py",
    "backend/app/services/gate3/care_intelligence.py",
    # CAP23-25 Iran directory acquisition/import + router mount.
    "backend/app/services/i5/iran_directory_source_manifest.py",
    "backend/app/services/i5/iran_directory_acquisition.py",
    "backend/app/services/i5/iran_directory_normalization.py",
    "backend/app/services/i5/iran_directory_import.py",
    "backend/app/services/i5/iran_directory_federation.py",
    "backend/app/services/i5/source_governance_decisions.py",
    "backend/app/services/i5/multisource_activation.py",
    "backend/app/services/i5/coverage_manifest_loader.py",
    "backend/app/main.py",
]


def test_W6P01_CI01_authorized_paths_pass() -> None:
    lines = [
        "M\tbackend/app/services/i5/metrics.py",
        "M\tbackend/app/services/i5/weekly_orchestrator.py",
        "A\tbackend/app/services/i5/adapters/live_transport.py",
        "M\tbackend/app/services/i5/adapters/public_web_fetch.py",
        "M\tbackend/app/services/i5/source_discovery.py",
    ]
    assert unexpected_app_mutations(lines, ALLOWED_APP_PATH_PREFIXES) == []


def test_W6P01_CI02_unauthorized_app_path_fails() -> None:
    lines = ["M\tbackend/app/main.py"]
    unexpected = unexpected_app_mutations(lines, ALLOWED_APP_PATH_PREFIXES)
    assert unexpected == ["backend/app/main.py"]


def test_W6P01_CI03_mixed_authorized_and_unauthorized() -> None:
    lines = [
        "M\tbackend/app/services/i5/weekly_orchestrator.py",
        "M\tbackend/app/services/gate3/knowledge_source_fetcher.py",
        "A\tbackend/app/services/i5/adapters/live_transport.py",
    ]
    unexpected = unexpected_app_mutations(lines, ALLOWED_APP_PATH_PREFIXES)
    assert unexpected == ["backend/app/services/gate3/knowledge_source_fetcher.py"]


def test_W6P01_CI04_non_app_paths_ignored() -> None:
    lines = [
        "A\tbackend/tests/test_section30_i5_w6_p01_ci_sentinel.py",
        "A\talembic/versions/999_some_migration.py",
        "M\tdocs/evidence/section30/w6p01_prereq_real_e2e_20260808T053706Z/00_preflight/preflight.txt",
    ]
    assert unexpected_app_mutations(lines, ALLOWED_APP_PATH_PREFIXES) == []


def test_W6P01_CI05_rename_line_uses_new_path() -> None:
    lines = ["R100\tbackend/app/services/i5/old_name.py\tbackend/app/services/i5/weekly_orchestrator.py"]
    assert unexpected_app_mutations(lines, ALLOWED_APP_PATH_PREFIXES) == []
    lines_bad = ["R100\tbackend/app/services/i5/weekly_orchestrator.py\tbackend/app/unrelated.py"]
    assert unexpected_app_mutations(lines_bad, ALLOWED_APP_PATH_PREFIXES) == ["backend/app/unrelated.py"]


def test_W6P01_CI06_blank_and_malformed_lines_ignored() -> None:
    lines = ["", "   ", "not_a_valid_name_status_line"]
    assert unexpected_app_mutations(lines, ALLOWED_APP_PATH_PREFIXES) == []


def test_W6P01_CI07_directory_prefix_without_glob_suffix() -> None:
    lines = ["M\tbackend/app/services/i5/adapters/base.py"]
    # "**" suffix matches the whole subtree, including the directory itself as a file boundary.
    assert unexpected_app_mutations(lines, ["backend/app/services/i5/adapters/**"]) == []
    assert unexpected_app_mutations(lines, ["backend/app/services/i5/adapters/"]) == []


def test_W6P01_CI08_cap17_personalization_paths_pass() -> None:
    lines = [
        "M\tbackend/app/services/i5/runtime_knowledge_retrieval.py",
        "M\tbackend/app/services/gate3/care_intelligence.py",
        "M\tbackend/app/services/i5/metrics.py",
    ]
    assert unexpected_app_mutations(lines, ALLOWED_APP_PATH_PREFIXES) == []
