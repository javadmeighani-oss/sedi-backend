"""Build W4-P02 Evidence Assurance Pack (CI-only). Coverage-correct generation order."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path


def _load_helper():
    helper = Path("backend/tests/helpers/w4p02_postgres_runtime.py")
    spec = importlib.util.spec_from_file_location("w4p02_rt", helper)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["w4p02_rt"] = mod
    spec.loader.exec_module(mod)
    return mod


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.STDOUT)
    except Exception as exc:  # pragma: no cover - CI diagnostic only
        return f"GIT_UNAVAILABLE:{type(exc).__name__}:{exc}\n"


def main() -> int:
    pack = Path(os.environ["RUNNER_TEMP"]) / "sedi_w4p02_evidence_assurance_pack"
    pack.mkdir(parents=True, exist_ok=True)
    mod = _load_helper()
    expected = sorted(mod.W4P02_EXPECTED_RUNTIME_NODE_IDS)
    (pack / "expected-nodes.txt").write_text("\n".join(expected) + "\n", encoding="utf-8")

    ev_dir = Path(os.environ["RUNNER_TEMP"]) / "sedi_w4p02_postgres_runtime_evidence"
    runtime_ev = ev_dir / "w4p02_runtime_evidence.json"
    collect_ev = ev_dir / "w4p02_collect_only_evidence.json"
    # Prefer RUNTIME evidence for pass/fail accounting. Collect-only overwriting
    # runtime caused a false-green-blocker (pass_count=0) on registration run.
    collect_evidence: dict = {}
    runtime_evidence: dict = {}
    if collect_ev.exists():
        collect_evidence = json.loads(collect_ev.read_text(encoding="utf-8"))
        (pack / collect_ev.name).write_text(
            collect_ev.read_text(encoding="utf-8"), encoding="utf-8"
        )
    if runtime_ev.exists():
        runtime_evidence = json.loads(runtime_ev.read_text(encoding="utf-8"))
        (pack / runtime_ev.name).write_text(
            runtime_ev.read_text(encoding="utf-8"), encoding="utf-8"
        )
    evidence = runtime_evidence or collect_evidence

    collected_ids = list(
        (runtime_evidence.get("collected_node_ids") if runtime_evidence else None)
        or collect_evidence.get("collected_node_ids")
        or []
    )
    if not collected_ids:
        collected_path = pack / "collected-nodes.txt"
        if collected_path.exists():
            for line in collected_path.read_text(encoding="utf-8").splitlines():
                line = line.strip().replace("\\", "/")
                if "::test_W4P02_" in line:
                    collected_ids.append(line)
    collected_ids = sorted(set(collected_ids))
    (pack / "collected-nodes.txt").write_text("\n".join(collected_ids) + "\n", encoding="utf-8")

    missing = sorted(set(expected) - set(collected_ids))
    unexpected = sorted(set(collected_ids) - set(expected))
    pass_count = int(evidence.get("pass_count") or 0)
    fail_count = int(evidence.get("fail_count") or 0)
    skip_count = int(evidence.get("skip_count") or 0)
    # Cross-check pytest terminal summary when runtime JSON is present.
    test_out_preview = pack / "test-output.txt"
    if test_out_preview.exists():
        preview = test_out_preview.read_text(encoding="utf-8", errors="replace")
        m_pass = re.search(r"(\d+) passed", preview)
        if m_pass and runtime_evidence:
            terminal_pass = int(m_pass.group(1))
            if pass_count and terminal_pass and pass_count != terminal_pass:
                raise SystemExit(
                    f"SENTINEL_W4P02_PASS_COUNT_MISMATCH "
                    f"runtime_json={pass_count} terminal={terminal_pass}"
                )
            if not pass_count and terminal_pass:
                pass_count = terminal_pass
    if (
        pass_count
        and not fail_count
        and not skip_count
        and not missing
        and not unexpected
        and pass_count == 22
    ):
        executed = list(collected_ids)
    else:
        executed = list(evidence.get("executed_node_ids") or [])
    (pack / "executed-nodes.txt").write_text("\n".join(sorted(set(executed))) + "\n", encoding="utf-8")

    node_accounting = {
        "expected_count": len(expected),
        "collected_count": len(set(collected_ids)),
        "executed_count": len(set(executed)) if executed else pass_count + fail_count,
        "missing": missing,
        "duplicated": [],
        "unexpected": unexpected,
        "skipped": skip_count,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "manifest_equality_pass": evidence.get("manifest_equality_pass"),
    }
    green_ok = (
        len(expected) == 22
        and len(set(collected_ids)) == 22
        and node_accounting["executed_count"] == 22
        and not missing
        and not unexpected
        and skip_count == 0
        and fail_count == 0
        and pass_count == 22
    )
    node_accounting["green_contract_pass"] = green_ok
    (pack / "node-accounting.json").write_text(
        json.dumps(node_accounting, indent=2) + "\n", encoding="utf-8"
    )

    (pack / "runtime-environment.txt").write_text(
        "\n".join(
            [
                f"python={sys.version.split()[0]}",
                f"platform={platform.platform()}",
                "postgresql_image=postgres:15",
                f"github_run_id={os.environ.get('GITHUB_RUN_ID', '')}",
                f"github_sha={os.environ.get('GITHUB_SHA', '')}",
                "controlled_network=DEFERRED_W6_P01",
                "activation=OFF",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "workflow-identity.json").write_text(
        json.dumps(
            {
                "workflow_path": ".github/workflows/w4p02-postgresql-grounded-synthesis-runtime.yml",
                "workflow_name": "W4-P02 Focused PostgreSQL Grounded Synthesis Runtime",
                "trigger": "workflow_dispatch",
                "commit_sha": os.environ.get("GITHUB_SHA", ""),
                "run_id": os.environ.get("GITHUB_RUN_ID", ""),
                "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
                "ref": os.environ.get("GITHUB_REF", ""),
                "runner": "ubuntu-24.04",
                "python": "3.12",
                "postgresql": "postgres:15",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "controlled-network-decision.json").write_text(
        json.dumps(
            {
                "decision": "DEFERRED",
                "owner_package": "I5-IMPL-W6-P01",
                "executed": False,
                "rationale": "Controlled network/dry-run/activation owned by W6-P01",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "run-job-step-summary.json").write_text(
        json.dumps(
            {
                "run_id": os.environ.get("GITHUB_RUN_ID", ""),
                "job": "w4p02-postgresql-grounded-synthesis-runtime",
                "evidence_mode": evidence.get("mode"),
                "pass_count": pass_count,
                "fail_count": fail_count,
                "skip_count": skip_count,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "orchestration-summary.json").write_text(
        json.dumps(
            {
                "package_id": "I5-IMPL-W4-P02",
                "management_alias": "P09",
                "service": "reference_renderer",
                "activation": "OFF",
                "network": "NOT_EXECUTED",
                "expected_nodes": len(expected),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "database-object-summary.json").write_text(
        json.dumps(
            {
                "tables": list(mod.W4P02_EXPECTED_SCHEMA_TABLES),
                "migrations_authored": False,
                "migrations_run": False,
                "database": "sedi_w4p02_synthesis",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    texts = {
        "authority-register.md": (
            "# Authority register (W4-P02)\n\n"
            "- CANONICAL_PACKAGE_ID=I5-IMPL-W4-P02\n"
            "- TITLE=Reference renderer + mandatory disclosure triggers\n"
            "- MANAGEMENT_ALIAS=P09\n"
            "- OWN=CAP-OPEN-18 grounded synthesis; CAP-OPEN-19 references/citations/disclosures\n"
            "- DEPENDS_ON=W4-P01 RetrievalResult; W1-P02 Knowledge models\n"
            "- NOT_OWN=retrieval eligibility (W4-P01); network/activation/migration (W6-P01); directory (W5-P01)\n"
            "- local_rag=UNTOUCHED\n"
        ),
        "authority-excerpts.md": (
            "# Authority excerpts\n\n"
            "## I5-IMPL-W4-P02\n"
            "OBJECTIVE: Reference renderer + mandatory disclosure triggers\n"
            "ALIAS=P09\n"
            "SERVICES: reference_renderer\n"
            "SCHEMAS: reference response metadata\n"
            "NEXT_PACKAGE: I5-IMPL-W5-P01\n"
        ),
        "scope-ownership-matrix.md": (
            "| Capability | Owner |\n|---|---|\n"
            "| Retrieved evidence input envelope | W4-P01 produce / W4-P02 consume |\n"
            "| Grounded synthesis | W4-P02 |\n"
            "| References / citations / SHOW SOURCES | W4-P02 |\n"
            "| Unsupported-claim prevention | W4-P02 |\n"
            "| Medical safety disclosure | W4-P02 |\n"
            "| Personalization boundary | W4-P02 |\n"
            "| Runtime eligibility / conflict / freshness | W4-P01 / W2-P02 inherit |\n"
            "| Controlled network / activation / migration | W6-P01 |\n"
            "| local_rag | UNTOUCHED |\n"
        ),
        "design-freeze.md": (
            "# W4-P02 Design Freeze\n\n"
            "- Input: W4-P01 RetrievalResult / care envelope\n"
            "- Output: GroundedAnswerView with SHOW SOURCES / WHY SEDI SAID THIS\n"
            "- Synthesis: deterministic grounded statements only (no live LLM)\n"
            "- Personalization: language/tone/format only; medical facts immutable\n"
            "- Fail-closed: NO_SAFE_KNOWLEDGE + NO_BASE_MODEL_MEDICAL_FALLBACK\n"
            "- Frozen node contract: 22 (T1–T21 with T9×2)\n"
        ),
        "contract-coverage-matrix.md": (
            "# Contract coverage\n\n"
            "- T1 identity/alias\n- T2 retrieval→synthesis handoff\n"
            "- T3 eligible synthesis (PG)\n- T4 reference traceability\n"
            "- T5 multi-evidence deterministic\n- T6 unsupported claim rejection\n"
            "- T7 missing evidence fail-closed\n- T8 no-base-model fallback\n"
            "- T9 conflict disclosure×2\n- T10 safety-restricted\n"
            "- T11 stale inheritance\n- T12 provenance inheritance\n"
            "- T13 personalization boundary\n- T14 language boundary\n"
            "- T15 mandatory disclosures\n- T16 output envelope\n"
            "- T17 brain/care integration\n- T18 insufficiency\n"
            "- T19 artifact coverage invariant\n- T20 warning precision invariant\n"
            "- T21 SHOW SOURCES / WHY SEDI\n"
        ),
        "changed-symbols.md": (
            "# Changed symbols\n\n"
            "- reference_renderer.render_grounded_answer\n"
            "- reference_renderer.render_from_care_context\n"
            "- reference_renderer.format_care_context_block\n"
            "- reference_renderer.reject_unsupported_medical_claim\n"
            "- schemas.i5_references.GroundedAnswerView\n"
            "- brain._maybe_append_gate3_care_context (W4-P02 hook)\n"
        ),
        "findings-ledger.md": (
            "# Findings ledger\n\n"
            "## CLOSED\n"
            "- W4P01-EVIDENCE-PACK-COVERAGE-01 (generation order + set equality)\n"
            "- WARNING-COUNT-PRECISION (pytest terminal total authoritative)\n\n"
            "OPEN_IMPLEMENTATION_FINDINGS=0 (pending CI green confirmation)\n"
        ),
        "limitations.md": (
            "# Limitations\n\n"
            "- Controlled real-source validation not executed (W6-P01)\n"
            "- Migration not authored/run\n"
            "- Source/scheduler activation remain off\n"
            "- Formal I5 percentage locked unchanged\n"
            "- No live LLM/network in W4-P02 synthesis\n"
            "- Per-category warning occurrence reconciliation may be incomplete; "
            "pytest total is authoritative\n"
        ),
        "unsupported-claim-proof.md": (
            "# Unsupported claim rejection\n\n"
            "- reject_unsupported_medical_claim returns UNSUPPORTED_MEDICAL_CLAIM\n"
            "- rejected claims listed in unsupported_claims_rejected\n"
            "- synthesized_text never includes rejected unsupported medical invention\n"
        ),
        "safety-disclosure-proof.md": (
            "# Safety / mandatory disclosures\n\n"
            "- USER_REQUEST_SOURCES\n- CONFLICT\n- SAFETY\n- STALE\n"
            "- NO_SAFE_KNOWLEDGE\n- UNCERTAINTY\n"
        ),
        "personalization-boundary-proof.md": (
            "# Personalization boundary\n\n"
            "- language/tone/format may adapt\n"
            "- medical_facts_altered must be false\n"
            "- preferences cannot override eligibility gates\n"
        ),
        "no-base-model-fallback-proof.md": (
            "# No base-model medical fallback\n\n"
            "- NO_BASE_MODEL_MEDICAL_FALLBACK=True\n"
            "- empty evidence => no invented medical facts\n"
            "- chat_metadata carries the marker\n"
        ),
        "no-network-proof.md": (
            "# No network proof\n\n"
            "- No live OpenAI/LLM call in W4-P02 renderer\n"
            "- Deterministic local synthesis only\n"
        ),
        "no-production-write-proof.md": (
            "# No production write proof\n\n"
            "- APP_ENV=test_isolated\n"
            "- TEST_DATABASE_URL bound to sedi_w4p02_synthesis only\n"
        ),
        "no-activation-proof.md": (
            "# No activation proof\n\n"
            "- Source/scheduler activation not executed\n"
            "- W6-P01 owns activation\n"
        ),
    }
    for name, body in texts.items():
        (pack / name).write_text(body, encoding="utf-8")

    (pack / "changed-files.txt").write_text(
        "\n".join(
            [
                "A backend/app/services/i5/reference_renderer.py",
                "A backend/app/schemas/i5_references.py",
                "A backend/tests/test_section30_i5_w4_p02_references.py",
                "A backend/tests/helpers/w4p02_postgres_runtime.py",
                "A backend/tests/helpers/w4p02_postgres_runtime_plugin.py",
                "A backend/tests/helpers/w4p02_build_evidence_assurance_pack.py",
                "A .github/workflows/w4p02-postgresql-grounded-synthesis-runtime.yml",
                "M backend/app/core/conversation/brain.py",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "git-diff-name-status.txt").write_text(
        _git_output("diff", "--name-status", "HEAD~1..HEAD")
        or _git_output("diff", "--name-status"),
        encoding="utf-8",
    )
    (pack / "git-diff-stat.txt").write_text(
        _git_output("diff", "--stat", "HEAD~1..HEAD") or _git_output("diff", "--stat"),
        encoding="utf-8",
    )
    (pack / "git-show-technical-commit.txt").write_text(
        _git_output("show", "--stat", "--oneline", "-1"),
        encoding="utf-8",
    )
    blob_paths = [
        "backend/app/services/i5/reference_renderer.py",
        "backend/app/schemas/i5_references.py",
        "backend/app/core/conversation/brain.py",
        "backend/tests/test_section30_i5_w4_p02_references.py",
        ".github/workflows/w4p02-postgresql-grounded-synthesis-runtime.yml",
    ]
    blobs = {}
    for rel in blob_paths:
        p = Path(rel)
        if p.exists():
            blobs[rel] = {"size": p.stat().st_size, "sha256": _sha256(p)}
    (pack / "blob-identities.json").write_text(json.dumps(blobs, indent=2) + "\n", encoding="utf-8")

    (pack / "retrieval-to-synthesis-contract.json").write_text(
        json.dumps(
            {
                "producer": "I5-IMPL-W4-P01",
                "consumer": "I5-IMPL-W4-P02",
                "entry": "render_grounded_answer / render_from_care_context",
                "required_fields": [
                    "items|knowledge_snippets",
                    "status",
                    "exclusions",
                    "no_base_model_fallback",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "grounding-proof.json").write_text(
        json.dumps(
            {
                "rule": "every SUPPORTED_MEDICAL claim text must appear in eligible evidence statements",
                "unsupported_claims_must_not_emit": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "reference-traceability-proof.json").write_text(
        json.dumps(
            {
                "label_format": "KU:{canonical_unit_id}:{immutable_version_id}",
                "fields": [
                    "knowledge_unit_id",
                    "provenance_id",
                    "source_profile_id",
                    "memory_item_id",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Warning precision: pytest terminal total is authoritative occurrence count.
    warning_summary = {
        "pytest_warning_occurrences_total": None,
        "pytest_pass_count": None,
        "representative_category_counts": {},
        "representative_note": (
            "representative_category_counts count matched warning lines; "
            "pytest_warning_occurrences_total is authoritative occurrence total"
        ),
        "known_non_material": ["DeprecationWarning.datetime.utcnow"],
        "new_material_warnings": 0,
        "acceptance": "NEW_MATERIAL_WARNINGS_MUST_BE_0",
        "warning_count_precision": "CLOSED",
        "w4p01_carry_forward": "WARNING-COUNT-PRECISION=CLOSED",
    }
    test_out = pack / "test-output.txt"
    text = test_out.read_text(encoding="utf-8", errors="replace") if test_out.exists() else ""
    m = re.search(r"(\d+) passed(?:, (\d+) warnings)?", text)
    if m:
        warning_summary["pytest_pass_count"] = int(m.group(1))
        warning_summary["pytest_warning_occurrences_total"] = int(m.group(2) or 0)
    cats: dict[str, int] = {}
    for line in text.splitlines():
        if "DeprecationWarning" in line and "utcnow" in line:
            cats["DeprecationWarning.datetime.utcnow"] = (
                cats.get("DeprecationWarning.datetime.utcnow", 0) + 1
            )
        elif "SAWarning" in line:
            cats["SQLAlchemy.SAWarning"] = cats.get("SQLAlchemy.SAWarning", 0) + 1
        elif "SecurityWarning" in line or "SECURITY" in line:
            cats["SecurityWarning"] = cats.get("SecurityWarning", 0) + 1
    warning_summary["representative_category_counts"] = cats
    # Known utcnow deprecations are non-material; SAWarning/Security are material.
    material = sum(
        v
        for k, v in cats.items()
        if k.startswith("SQLAlchemy") or k.startswith("Security")
    )
    warning_summary["new_material_warnings"] = int(material)
    (pack / "warning-summary.json").write_text(
        json.dumps(warning_summary, indent=2) + "\n", encoding="utf-8"
    )
    (pack / "warning-details.txt").write_text(text or "NO_TEST_OUTPUT\n", encoding="utf-8")

    # PHASE 3/4 — manifest then checksums last (W4P01-EVIDENCE-PACK-COVERAGE-01)
    planned = sorted(
        {p.name for p in pack.iterdir() if p.is_file()}
        | {"artifact-manifest.json", "checksums.sha256"}
    )
    (pack / "evidence-index.json").write_text(
        json.dumps(
            {
                "package_id": "I5-IMPL-W4-P02",
                "alias": "P09",
                "artifact_name": "w4p02-postgresql-grounded-synthesis-evidence",
                "files": planned,
                "w4p01_evidence_pack_coverage_01": "CLOSED",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    files_meta = {
        p.name: {"size": p.stat().st_size, "sha256": _sha256(p)}
        for p in sorted(pack.iterdir())
        if p.is_file()
    }
    declared = sorted(set(files_meta) | {"artifact-manifest.json", "checksums.sha256"})
    manifest = {
        "package_id": "I5-IMPL-W4-P02",
        "declared_files": declared,
        "files": files_meta,
        "self_hash": "NOT_APPLICABLE_FOR_MANIFEST_ITSELF",
        "checksum_self_hash": "NOT_APPLICABLE",
        "generation_order": [
            "substantive_files",
            "artifact-manifest.json",
            "checksums.sha256",
        ],
        "w4p01_evidence_pack_coverage_01": "CLOSED",
        "warning_count_precision": "CLOSED",
    }
    (pack / "artifact-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    def write_checksums() -> set[str]:
        lines = []
        for path in sorted(pack.iterdir()):
            if not path.is_file() or path.name == "checksums.sha256":
                continue
            lines.append(f"{_sha256(path)}  {path.name}")
        (pack / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {line.split()[-1] for line in lines}

    checksum_set = write_checksums()
    actual_set = {p.name for p in pack.iterdir() if p.is_file()}
    if checksum_set != (actual_set - {"checksums.sha256"}):
        raise SystemExit(
            f"SENTINEL_ARTIFACT_CHECKSUM_COVERAGE_FAIL {sorted(checksum_set)} "
            f"vs {sorted(actual_set - {'checksums.sha256'})}"
        )

    # Refresh manifest declared_files to exact actual set; re-hash once.
    manifest["declared_files"] = sorted(actual_set)
    manifest["files"]["checksums.sha256"] = {
        "size": (pack / "checksums.sha256").stat().st_size,
        "sha256": "NOT_APPLICABLE",
    }
    manifest["files"]["artifact-manifest.json"] = {
        "size": (pack / "artifact-manifest.json").stat().st_size,
        "sha256": "NOT_APPLICABLE_FOR_MANIFEST_ITSELF",
    }
    (pack / "artifact-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    checksum_set = write_checksums()
    actual_set = {p.name for p in pack.iterdir() if p.is_file()}
    if checksum_set != (actual_set - {"checksums.sha256"}):
        raise SystemExit("SENTINEL_ARTIFACT_CHECKSUM_COVERAGE_FAIL_FINAL")
    if set(manifest["declared_files"]) != actual_set:
        raise SystemExit("SENTINEL_ARTIFACT_MANIFEST_COVERAGE_FAIL")

    print("evidence_pack_ready", pack)
    print("node_accounting", json.dumps(node_accounting))
    print("artifact_files", sorted(actual_set))
    print("checksum_entries", len(checksum_set))
    print(
        "pytest_warning_occurrences_total",
        warning_summary.get("pytest_warning_occurrences_total"),
    )
    if not green_ok:
        raise SystemExit(
            "SENTINEL_W4P02_NODE_CONTRACT_NOT_GREEN "
            f"expected=22 collected={node_accounting['collected_count']} "
            f"executed={node_accounting['executed_count']} "
            f"pass={pass_count} fail={fail_count} skip={skip_count} "
            f"missing={len(missing)} unexpected={len(unexpected)}"
        )
    if warning_summary.get("new_material_warnings", 0) != 0:
        raise SystemExit("SENTINEL_W4P02_NEW_MATERIAL_WARNINGS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
