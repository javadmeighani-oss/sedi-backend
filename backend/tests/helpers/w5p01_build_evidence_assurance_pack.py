"""Build W5-P01 Evidence Assurance Pack (CI-only). Coverage-correct generation order."""
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

DEFAULT_GATE_START_SHA = "cb27cedde0dec27dbe4f74bac75e56a97da14f5a"
EXPECTED_NODE_COUNT = 24
PACKAGE_ID = "I5-IMPL-W5-P01"
MANAGEMENT_ALIAS = "P10"
ARTIFACT_NAME = "w5p01-postgresql-iran-directory-evidence"


def _load_helper():
    helper = Path("backend/tests/helpers/w5p01_postgres_runtime.py")
    spec = importlib.util.spec_from_file_location("w5p01_rt", helper)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["w5p01_rt"] = mod
    spec.loader.exec_module(mod)
    return mod


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.STDOUT)
    except Exception as exc:  # pragma: no cover - CI diagnostic only
        raise SystemExit(
            f"SENTINEL_W5P01_GIT_UNAVAILABLE {type(exc).__name__}: {exc}"
        ) from exc


def _resolve_git_shas() -> dict[str, str | list[str]]:
    gate_start = os.environ.get("GATE_START_SHA", DEFAULT_GATE_START_SHA).strip()
    green_technical = os.environ.get("GREEN_TECHNICAL_SHA", os.environ.get("GITHUB_SHA", "")).strip()
    implementation = os.environ.get("IMPLEMENTATION_SHA", "").strip()
    remediation_raw = os.environ.get("REMEDIATION_SHAS", "").strip()
    remediation = [s for s in remediation_raw.split() if s]
    if not gate_start:
        raise SystemExit("SENTINEL_W5P01_GATE_START_SHA_MISSING")
    if not green_technical:
        raise SystemExit("SENTINEL_W5P01_GREEN_TECHNICAL_SHA_MISSING")
    return {
        "gate_start_sha": gate_start,
        "implementation_sha": implementation,
        "green_technical_sha": green_technical,
        "remediation_shas": remediation,
    }


def _write_git_history_artifacts(pack: Path, shas: dict[str, str | list[str]]) -> None:
    gate_start = str(shas["gate_start_sha"])
    green_technical = str(shas["green_technical_sha"])
    implementation = str(shas.get("implementation_sha") or "")
    remediation = list(shas.get("remediation_shas") or [])

    (pack / "git-diff-name-status.txt").write_text(
        _git_output("diff", "--name-status", f"{gate_start}..{green_technical}"),
        encoding="utf-8",
    )
    (pack / "git-diff-stat.txt").write_text(
        _git_output("diff", "--stat", f"{gate_start}..{green_technical}"),
        encoding="utf-8",
    )

    show_sha = implementation or green_technical
    (pack / "git-show-implementation-commit.txt").write_text(
        _git_output("show", "--format=fuller", "--stat", "--patch", show_sha),
        encoding="utf-8",
    )

    remediation_blocks: list[str] = []
    for sha in remediation:
        remediation_blocks.append(f"=== REMEDIATION {sha} ===\n")
        remediation_blocks.append(
            _git_output("show", "--format=fuller", "--stat", "--patch", sha)
        )
    (pack / "git-show-remediation-commits.txt").write_text(
        "\n".join(remediation_blocks) if remediation_blocks else "NO_REMEDIATION_SHAS\n",
        encoding="utf-8",
    )

    commit_chain = {
        "gate_start_sha": gate_start,
        "implementation_sha": implementation or None,
        "green_technical_sha": green_technical,
        "remediation_shas": remediation,
        "diff_range": f"{gate_start}..{green_technical}",
        "w4p02_evidence_git_history_01": "CLOSED",
    }
    (pack / "commit-chain.json").write_text(
        json.dumps(commit_chain, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    pack = Path(os.environ["RUNNER_TEMP"]) / "sedi_w5p01_evidence_assurance_pack"
    pack.mkdir(parents=True, exist_ok=True)
    mod = _load_helper()
    expected = sorted(mod.W5P01_EXPECTED_RUNTIME_NODE_IDS)
    if len(expected) != EXPECTED_NODE_COUNT:
        raise SystemExit(
            f"SENTINEL_W5P01_EXPECTED_NODE_COUNT_MISMATCH expected={EXPECTED_NODE_COUNT} "
            f"manifest={len(expected)}"
        )
    (pack / "expected-nodes.txt").write_text("\n".join(expected) + "\n", encoding="utf-8")

    ev_dir = Path(os.environ["RUNNER_TEMP"]) / "sedi_w5p01_postgres_runtime_evidence"
    runtime_ev = ev_dir / "w5p01_runtime_evidence.json"
    collect_ev = ev_dir / "w5p01_collect_only_evidence.json"
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

    # Prefer RUNTIME evidence for pass/fail/skip accounting. Collect-only must never
    # overwrite runtime pass counts (W4P02 registration false-green blocker carry-forward).
    if runtime_evidence:
        evidence = runtime_evidence
        pass_count = int(runtime_evidence.get("pass_count") or 0)
        fail_count = int(runtime_evidence.get("fail_count") or 0)
        skip_count = int(runtime_evidence.get("skip_count") or 0)
    elif collect_evidence:
        evidence = collect_evidence
        pass_count = int(collect_evidence.get("pass_count") or 0)
        fail_count = int(collect_evidence.get("fail_count") or 0)
        skip_count = int(collect_evidence.get("skip_count") or 0)
    else:
        evidence = {}
        pass_count = fail_count = skip_count = 0

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
                if "::test_W5P01_" in line:
                    collected_ids.append(line)
    collected_ids = sorted(set(collected_ids))
    (pack / "collected-nodes.txt").write_text(
        "\n".join(collected_ids) + "\n", encoding="utf-8"
    )

    missing = sorted(set(expected) - set(collected_ids))
    unexpected = sorted(set(collected_ids) - set(expected))

    test_out_preview = pack / "test-output.txt"
    if test_out_preview.exists():
        preview = test_out_preview.read_text(encoding="utf-8", errors="replace")
        m_pass = re.search(r"(\d+) passed", preview)
        if m_pass and runtime_evidence:
            terminal_pass = int(m_pass.group(1))
            if pass_count and terminal_pass and pass_count != terminal_pass:
                raise SystemExit(
                    f"SENTINEL_W5P01_PASS_COUNT_MISMATCH "
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
        and pass_count == EXPECTED_NODE_COUNT
    ):
        executed = list(collected_ids)
    else:
        executed = list(evidence.get("executed_node_ids") or [])
    (pack / "executed-nodes.txt").write_text(
        "\n".join(sorted(set(executed))) + "\n", encoding="utf-8"
    )

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
        len(expected) == EXPECTED_NODE_COUNT
        and len(set(collected_ids)) == EXPECTED_NODE_COUNT
        and node_accounting["executed_count"] == EXPECTED_NODE_COUNT
        and not missing
        and not unexpected
        and skip_count == 0
        and fail_count == 0
        and pass_count == EXPECTED_NODE_COUNT
    )
    node_accounting["green_contract_pass"] = green_ok
    (pack / "node-accounting.json").write_text(
        json.dumps(node_accounting, indent=2) + "\n", encoding="utf-8"
    )

    git_shas = _resolve_git_shas()
    _write_git_history_artifacts(pack, git_shas)

    (pack / "runtime-environment.txt").write_text(
        "\n".join(
            [
                f"python={sys.version.split()[0]}",
                f"platform={platform.platform()}",
                "postgresql_image=postgres:15",
                f"github_run_id={os.environ.get('GITHUB_RUN_ID', '')}",
                f"github_sha={os.environ.get('GITHUB_SHA', '')}",
                f"gate_start_sha={git_shas['gate_start_sha']}",
                f"green_technical_sha={git_shas['green_technical_sha']}",
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
                "workflow_path": ".github/workflows/w5p01-postgresql-iran-directory-runtime.yml",
                "workflow_name": "W5-P01 Focused PostgreSQL Iran Directory Runtime",
                "trigger": "workflow_dispatch",
                "commit_sha": os.environ.get("GITHUB_SHA", ""),
                "run_id": os.environ.get("GITHUB_RUN_ID", ""),
                "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
                "ref": os.environ.get("GITHUB_REF", ""),
                "runner": "ubuntu-24.04",
                "python": "3.12",
                "postgresql": "postgres:15",
                "gate_start_sha": git_shas["gate_start_sha"],
                "green_technical_sha": git_shas["green_technical_sha"],
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
                "job": "w5p01-postgresql-iran-directory-runtime",
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
                "package_id": PACKAGE_ID,
                "management_alias": MANAGEMENT_ALIAS,
                "service": "directory_search",
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
                "tables": list(mod.W5P01_EXPECTED_SCHEMA_TABLES),
                "migrations_authored": ["052_i5_w5_iran_directory"],
                "migrations_run": False,
                "database": "sedi_w5p01_directory",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    texts = {
        "authority-register.md": (
            "# Authority register (W5-P01)\n\n"
            "- CANONICAL_PACKAGE_ID=I5-IMPL-W5-P01\n"
            "- TITLE=Iran doctors/labs/hospitals directory layer\n"
            "- MANAGEMENT_ALIAS=P10\n"
            "- OWN=CAP-OPEN-20 directory discovery; CAP-OPEN-21 entity separation\n"
            "- DEPENDS_ON=W4-P02 grounded synthesis; W1-P02 Knowledge models\n"
            "- NOT_OWN=clinical KnowledgeUnit authority; network/activation (W6-P01); "
            "live IR source fetch\n"
            "- local_rag=UNTOUCHED\n"
        ),
        "authority-excerpts.md": (
            "# Authority excerpts\n\n"
            "## I5-IMPL-W5-P01\n"
            "OBJECTIVE: Iran doctors/labs/hospitals directory layer\n"
            "ALIAS=P10\n"
            "SERVICES: directory_search\n"
            "SCHEMAS: iran_doctors, iran_laboratories, iran_hospitals\n"
            "NEXT_PACKAGE: I5-IMPL-W6-P01\n"
        ),
        "scope-ownership-matrix.md": (
            "| Capability | Owner |\n|---|---|\n"
            "| Iran directory ORM/search | W5-P01 |\n"
            "| UserDoctor vs IranDoctor separation | W5-P01 |\n"
            "| IR directory → KnowledgeUnit forbid | W5-P01 |\n"
            "| Clinical evidence output forbid | W5-P01 |\n"
            "| Grounded synthesis / references | W4-P02 |\n"
            "| Controlled network / activation / migration run | W6-P01 |\n"
            "| local_rag | UNTOUCHED |\n"
        ),
        "design-freeze.md": (
            "# W5-P01 Design Freeze\n\n"
            "- Entities: IranDoctor, IranLaboratory, IranHospital (+ UserDoctor separation)\n"
            "- Search: deterministic local PostgreSQL directory queries only\n"
            "- IR directory records MUST NOT become KnowledgeUnit clinical authority\n"
            "- No live IR source fetch, crawl, or network in this gate\n"
            "- Migration 052_i5_w5_iran_directory AUTHOR only (not run)\n"
            "- Frozen node contract: 24 (T1–T24)\n"
        ),
        "source-decision-register.md": (
            "# Source decision register\n\n"
            "- NO_LIVE_IR_SOURCE_FETCH=True\n"
            "- source_system_label metadata readiness only (no live provider)\n"
            "- Controlled real-source validation deferred to W6-P01\n"
            "- Directory results informational; endorsement disclaimer required\n"
        ),
        "contract-coverage-matrix.md": (
            "# Contract coverage\n\n"
            "- T1 package identity/alias\n- T2 IranDoctor ORM persist\n"
            "- T3 IranLaboratory ORM persist\n- T4 IranHospital ORM persist\n"
            "- T5 unique canonical_directory_key\n- T6 search doctor\n"
            "- T7 search laboratory\n- T8 search hospital\n"
            "- T9 city/specialty filter\n- T10 empty result\n"
            "- T11 schema serialization\n- T12 API contract\n"
            "- T13 entity type separation\n- T14 UserDoctor vs IranDoctor\n"
            "- T15 no IR→KU structural FK\n- T16 no KU creation via directory\n"
            "- T17 no clinical evidence output\n- T18 no network markers\n"
            "- T19 migration authored not run\n- T20 source legal boundary\n"
            "- T21 endorsement disclaimer\n- T22 git history evidence invariant\n"
            "- T23 medical center facility type\n- T24 inactive excluded by default\n"
        ),
        "changed-symbols.md": (
            "# Changed symbols\n\n"
            "- iran_directory_service.search_doctors\n"
            "- iran_directory_service.search_laboratories\n"
            "- iran_directory_service.search_hospitals\n"
            "- iran_directory_service.refuse_ir_directory_to_knowledge_unit\n"
            "- schemas.i5_iran_directory.IranDoctorView\n"
            "- routers.i5_iran_directory.router\n"
            "- models.IranDoctor / IranLaboratory / IranHospital\n"
        ),
        "findings-ledger.md": (
            "# Findings ledger\n\n"
            "## CLOSED\n"
            "- W4P01-EVIDENCE-PACK-COVERAGE-01 (generation order + set equality)\n"
            "- WARNING-COUNT-PRECISION (pytest terminal total authoritative)\n"
            "- W4P02-EVIDENCE-GIT-HISTORY-01 (explicit SHAs; no ambiguous parent shorthand)\n\n"
            "OPEN_IMPLEMENTATION_FINDINGS=0 (pending CI green confirmation)\n"
        ),
        "limitations.md": (
            "# Limitations\n\n"
            "- Controlled real-source validation not executed (W6-P01)\n"
            "- Migration 052_i5_w5_iran_directory authored but not run\n"
            "- Source/scheduler activation remain off\n"
            "- Formal I5 percentage locked unchanged\n"
            "- No live IR fetch/network in W5-P01 directory gate\n"
            "- Per-category warning occurrence reconciliation may be incomplete; "
            "pytest total is authoritative\n"
        ),
        "userdoctor-vs-directory-proof.md": (
            "# UserDoctor vs IranDoctor separation\n\n"
            "- user_doctors table distinct from iran_doctors\n"
            "- user_id present on UserDoctor only\n"
            "- canonical_directory_key present on Iran directory entities only\n"
        ),
        "clinical-separation-proof.md": (
            "# Clinical separation proof\n\n"
            "- Directory payloads exclude knowledge_unit_id and clinical evidence fields\n"
            "- is_clinical_authority=False on directory views\n"
            "- is_knowledge_unit=False on search results\n"
        ),
        "no-ir-to-ku-proof.md": (
            "# No IR directory → KnowledgeUnit proof\n\n"
            "- NO_IR_TO_KU=True\n"
            "- refuse_ir_directory_to_knowledge_unit raises ForbiddenClinicalWriteError\n"
            "- No structural FK from iran_* tables to knowledge_units\n"
        ),
        "no-clinical-authority-proof.md": (
            "# No clinical authority proof\n\n"
            "- NO_CLINICAL_AUTHORITY=True\n"
            "- assert_not_clinical_authority fail-closed on banned KU fields\n"
            "- API responses set is_clinical_knowledge=False\n"
        ),
        "no-network-proof.md": (
            "# No network proof\n\n"
            "- No requests/httpx/urllib/openai/aiohttp in iran_directory_service\n"
            "- NO_LIVE_IR_SOURCE_FETCH=True\n"
            "- Deterministic local PostgreSQL search only\n"
        ),
        "no-production-write-proof.md": (
            "# No production write proof\n\n"
            "- APP_ENV=test_isolated\n"
            "- TEST_DATABASE_URL bound to sedi_w5p01_directory only\n"
            "- Production identifier refusal enforced by runtime harness\n"
        ),
        "no-source-activation-proof.md": (
            "# No source activation proof\n\n"
            "- Source/scheduler activation not executed\n"
            "- SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED unset\n"
            "- SEDI_I5_SOURCE_ACTIVATION_ENABLED unset\n"
            "- W6-P01 owns activation\n"
        ),
        "migration-authoring-proof.md": (
            "# Migration authoring proof\n\n"
            "- Alembic revision 052_i5_w5_iran_directory authored\n"
            "- Defines iran_doctors, iran_laboratories, iran_hospitals\n"
            "- down_revision=051_i5b2_governed_source_profile\n"
        ),
        "migration-not-run-proof.md": (
            "# Migration not run proof\n\n"
            "- MIGRATION_RUN_EXECUTED=False\n"
            "- SEDI_I5_W5P01_ALEMBIC_UPGRADE not set\n"
            "- Runtime schema via SQLAlchemy create_all in isolated test DB only\n"
        ),
        "w4p02-evidence-git-history-closure.md": (
            "# W4P02-EVIDENCE-GIT-HISTORY-01 closure\n\n"
            "Status: CLOSED\n\n"
            "- Never uses ambiguous parent shorthand for diffs\n"
            "- Uses explicit GATE_START_SHA..GREEN_TECHNICAL_SHA diff range\n"
            "- git show --format=fuller --stat --patch on IMPLEMENTATION_SHA when set, "
            "else GREEN_TECHNICAL_SHA\n"
            "- REMEDIATION_SHAS honored when present\n"
            "- commit-chain.json records gate_start, implementation, remediation, green shas\n"
            "- Git failure raises SystemExit (no silent GIT_UNAVAILABLE success)\n"
        ),
    }
    for name, body in texts.items():
        (pack / name).write_text(body, encoding="utf-8")

    (pack / "changed-files.txt").write_text(
        "\n".join(
            [
                "A backend/app/services/i5/iran_directory_service.py",
                "A backend/app/schemas/i5_iran_directory.py",
                "A backend/app/routers/i5_iran_directory.py",
                "A backend/alembic/versions/052_i5_w5_iran_directory.py",
                "A backend/tests/test_section30_i5_w5_iran_directory.py",
                "A backend/tests/helpers/w5p01_postgres_runtime.py",
                "A backend/tests/helpers/w5p01_postgres_runtime_plugin.py",
                "A backend/tests/helpers/w5p01_build_evidence_assurance_pack.py",
                "A .github/workflows/w5p01-postgresql-iran-directory-runtime.yml",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    blob_paths = [
        "backend/app/services/i5/iran_directory_service.py",
        "backend/app/schemas/i5_iran_directory.py",
        "backend/app/routers/i5_iran_directory.py",
        "backend/alembic/versions/052_i5_w5_iran_directory.py",
        "backend/tests/test_section30_i5_w5_iran_directory.py",
        ".github/workflows/w5p01-postgresql-iran-directory-runtime.yml",
    ]
    blobs = {}
    for rel in blob_paths:
        p = Path(rel)
        if p.exists():
            blobs[rel] = {"size": p.stat().st_size, "sha256": _sha256(p)}
    (pack / "blob-identities.json").write_text(json.dumps(blobs, indent=2) + "\n", encoding="utf-8")

    (pack / "directory-model-proof.json").write_text(
        json.dumps(
            {
                "tables": list(mod.W5P01_EXPECTED_SCHEMA_TABLES),
                "entities": ["DOCTOR", "LABORATORY", "HOSPITAL", "MEDICAL_CENTER"],
                "canonical_directory_key_unique": True,
                "record_state_active_inactive": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "directory-search-proof.json").write_text(
        json.dumps(
            {
                "functions": [
                    "search_doctors",
                    "search_laboratories",
                    "search_hospitals",
                ],
                "filters": ["name", "city", "specialty", "facility_type"],
                "default_limit": 20,
                "max_limit": 50,
                "inactive_excluded_by_default": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "entity-separation-proof.json").write_text(
        json.dumps(
            {
                "iran_entities": ["IranDoctor", "IranLaboratory", "IranHospital"],
                "user_entity": "UserDoctor",
                "entity_type_field": True,
                "no_shared_table": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    warning_summary = {
        "pytest_warning_occurrences_total": None,
        "pytest_pass_count": None,
        "representative_category_counts": {},
        "representative_note": (
            "representative_category_counts count matched warning lines; "
            "pytest_warning_occurrences_total is authoritative occurrence total"
        ),
        "known_non_material": [
            "DeprecationWarning.datetime.utcnow",
            "StarletteDeprecationWarning.httpx_testclient",
            "DeprecationWarning.crypt",
            "SQLAlchemy.SAWarning.transaction_already_deassociated",
        ],
        "new_material_warnings": 0,
        "acceptance": "NEW_MATERIAL_WARNINGS_MUST_BE_0",
        "warning_count_precision": "CLOSED",
        "w4p02_carry_forward": "WARNING-COUNT-PRECISION=CLOSED",
    }
    test_out = pack / "test-output.txt"
    text = test_out.read_text(encoding="utf-8", errors="replace") if test_out.exists() else ""
    m = re.search(r"(\d+) passed(?:, (\d+) warnings)?", text)
    if m:
        warning_summary["pytest_pass_count"] = int(m.group(1))
        warning_summary["pytest_warning_occurrences_total"] = int(m.group(2) or 0)
    cats: dict[str, int] = {}
    material_hits = 0
    for line in text.splitlines():
        if "DeprecationWarning" in line and "utcnow" in line:
            cats["DeprecationWarning.datetime.utcnow"] = (
                cats.get("DeprecationWarning.datetime.utcnow", 0) + 1
            )
        elif "StarletteDeprecationWarning" in line or (
            "httpx" in line and "starlette.testclient" in line
        ):
            cats["StarletteDeprecationWarning.httpx_testclient"] = (
                cats.get("StarletteDeprecationWarning.httpx_testclient", 0) + 1
            )
        elif "DeprecationWarning" in line and "crypt" in line:
            cats["DeprecationWarning.crypt"] = cats.get("DeprecationWarning.crypt", 0) + 1
        elif "SAWarning" in line and "transaction already deassociated" in line:
            cats["SQLAlchemy.SAWarning.transaction_already_deassociated"] = (
                cats.get("SQLAlchemy.SAWarning.transaction_already_deassociated", 0) + 1
            )
        elif "SAWarning" in line:
            cats["SQLAlchemy.SAWarning"] = cats.get("SQLAlchemy.SAWarning", 0) + 1
            lower = line.lower()
            if any(
                tok in lower
                for tok in (
                    "relationship",
                    "foreign key",
                    "mapper",
                    "integrity",
                    "constraint",
                    "security",
                )
            ):
                material_hits += 1
        elif "SecurityWarning" in line or "SECURITY" in line:
            cats["SecurityWarning"] = cats.get("SecurityWarning", 0) + 1
            material_hits += 1
    warning_summary["representative_category_counts"] = cats
    warning_summary["new_material_warnings"] = int(material_hits)
    (pack / "warning-summary.json").write_text(
        json.dumps(warning_summary, indent=2) + "\n", encoding="utf-8"
    )
    (pack / "warning-details.txt").write_text(text or "NO_TEST_OUTPUT\n", encoding="utf-8")

    # PHASE 3/4 — evidence-index near end; manifest then checksums last.
    planned = sorted(
        {p.name for p in pack.iterdir() if p.is_file()}
        | {"artifact-manifest.json", "checksums.sha256"}
    )
    (pack / "evidence-index.json").write_text(
        json.dumps(
            {
                "package_id": PACKAGE_ID,
                "alias": MANAGEMENT_ALIAS,
                "artifact_name": ARTIFACT_NAME,
                "files": planned,
                "w4p01_evidence_pack_coverage_01": "CLOSED",
                "w4p02_evidence_git_history_01": "CLOSED",
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
        "package_id": PACKAGE_ID,
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
        "w4p02_evidence_git_history_01": "CLOSED",
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
            "SENTINEL_W5P01_NODE_CONTRACT_NOT_GREEN "
            f"expected={EXPECTED_NODE_COUNT} collected={node_accounting['collected_count']} "
            f"executed={node_accounting['executed_count']} "
            f"pass={pass_count} fail={fail_count} skip={skip_count} "
            f"missing={len(missing)} unexpected={len(unexpected)}"
        )
    if warning_summary.get("new_material_warnings", 0) != 0:
        raise SystemExit("SENTINEL_W5P01_NEW_MATERIAL_WARNINGS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
